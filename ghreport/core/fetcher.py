"""Async GitHub data fetching via GraphQL."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
import httpx
import gidgethub
import gidgethub.httpx
import pytz

logger = logging.getLogger(__name__)

# Retry settings for transient GitHub errors (rate limits, HTML responses)
_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 10  # seconds

# Live retry state keyed by "owner/repo" — read by scheduler for UI feedback
_active_retries: dict[str, dict] = {}

# Global cooldown: set when rate limiting detected, checked before new requests
_rate_limit_until: datetime | None = None
_RATE_LIMIT_COOLDOWN = 300  # fallback seconds when reset time unavailable


class GitHubRateLimitError(Exception):
    """Raised when all retries exhausted due to rate limiting."""
    pass


def get_active_retries() -> dict[str, dict]:
    """Return a snapshot of current retry states."""
    return dict(_active_retries)


def get_rate_limit_until() -> datetime | None:
    """Return the cooldown deadline, or None if not rate-limited."""
    if _rate_limit_until and datetime.now(timezone.utc) < _rate_limit_until:
        return _rate_limit_until
    return None


def _is_rate_limit_error(exc: Exception) -> bool:
    """Check if the exception looks like a rate limit / abuse detection."""
    if isinstance(exc, (gidgethub.RateLimitExceeded,
                        gidgethub.GraphQLResponseTypeError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (403, 429)
    return False


def _get_rate_limit_reset(exc: Exception) -> datetime | None:
    """Extract the rate-limit reset datetime from the exception.

    Returns a timezone-aware UTC datetime, or None if unavailable."""
    # gidgethub.RateLimitExceeded carries the parsed RateLimit
    if isinstance(exc, gidgethub.RateLimitExceeded):
        rl = getattr(exc, "rate_limit", None)
        if rl and hasattr(rl, "reset_datetime"):
            return rl.reset_datetime
    # httpx 403/429 may carry Retry-After or x-ratelimit-reset
    if isinstance(exc, httpx.HTTPStatusError):
        headers = exc.response.headers
        # Retry-After: seconds until retry
        retry_after = headers.get("retry-after")
        if retry_after:
            try:
                return datetime.now(timezone.utc) + timedelta(
                    seconds=int(retry_after))
            except ValueError:
                pass
        # x-ratelimit-reset: Unix epoch
        reset_epoch = headers.get("x-ratelimit-reset")
        if reset_epoch:
            try:
                return datetime.fromtimestamp(
                    float(reset_epoch), tz=timezone.utc)
            except (ValueError, OSError):
                pass
    return None


def _set_rate_limit_cooldown(exc: Exception) -> None:
    """Set the global cooldown based on the exception's reset info."""
    global _rate_limit_until
    reset = _get_rate_limit_reset(exc)
    if reset:
        # Add a small buffer so we don't hit the boundary
        _rate_limit_until = reset + timedelta(seconds=5)
        logger.warning(
            "Rate limit detected — cooldown until %s "
            "(from server reset header)",
            _rate_limit_until.isoformat(),
        )
    else:
        _rate_limit_until = (
            datetime.now(timezone.utc)
            + timedelta(seconds=_RATE_LIMIT_COOLDOWN)
        )
        logger.warning(
            "Rate limit detected — fallback %ds cooldown until %s",
            _RATE_LIMIT_COOLDOWN, _rate_limit_until.isoformat(),
        )


async def _graphql_with_retry(gh, query, *, cursor=None, chunk=100, repo_key=None):
    """Call gh.graphql with exponential-backoff retry on transient errors."""
    global _rate_limit_until

    # If we're in a global cooldown, raise immediately so the scheduler
    # can skip this repo (and all remaining repos) without waiting.
    cooldown = get_rate_limit_until()
    if cooldown:
        wait = (cooldown - datetime.now(timezone.utc)).total_seconds()
        if wait > 0:
            raise GitHubRateLimitError(
                f"Global rate-limit cooldown active ({int(wait)}s remaining)"
            )

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            result = await gh.graphql(query, cursor=cursor, chunk=chunk)
            # Success — clear any retry/cooldown state
            if repo_key and repo_key in _active_retries:
                del _active_retries[repo_key]
            _rate_limit_until = None
            return result
        except (
            gidgethub.GraphQLResponseTypeError,
            gidgethub.RateLimitExceeded,
            httpx.HTTPStatusError,
            httpx.RemoteProtocolError,
            httpx.ReadError,
        ) as exc:
            last_exc = exc
            is_rate_limit = _is_rate_limit_error(exc)

            if attempt == _MAX_RETRIES - 1:
                if repo_key and repo_key in _active_retries:
                    del _active_retries[repo_key]
                if is_rate_limit:
                    _set_rate_limit_cooldown(exc)
                    raise GitHubRateLimitError(str(exc)) from exc
                raise

            # On FIRST rate-limit hit, set global cooldown and abort fast
            # so we stop hammering the API across all repos
            if is_rate_limit:
                if repo_key and repo_key in _active_retries:
                    del _active_retries[repo_key]
                _set_rate_limit_cooldown(exc)
                raise GitHubRateLimitError(str(exc)) from exc

            # Non-rate-limit transient error: retry with backoff
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            if hasattr(exc, 'retry_after') and exc.retry_after:
                delay = max(delay, int(exc.retry_after))
            if repo_key:
                _active_retries[repo_key] = {
                    "attempt": attempt + 1,
                    "max_attempts": _MAX_RETRIES,
                    "delay": delay,
                    "error": str(exc),
                }
            logger.warning(
                "GitHub API error (attempt %d/%d), retrying in %ds: %s",
                attempt + 1, _MAX_RETRIES, delay, exc,
            )
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")


issues_with_comments_query = """
query ($cursor: String, $chunk: Int) {{
  search(query: "repo:{owner}/{repo} type:issue state:{state} {since_filter}", type:ISSUE, first: $chunk, after: $cursor) {{
    issueCount
    pageInfo {{
      endCursor
      hasNextPage
    }}    
    edges {{
      node {{
        ... on Issue {{
          number
          title
          createdAt
          closedAt        
          author {{
            login
          }}
          editor {{
            login
          }}
          timelineItems(
            first: 100
            itemTypes: [CLOSED_EVENT, LABELED_EVENT, UNLABELED_EVENT, ISSUE_COMMENT]
          ) {{
            nodes {{
              __typename
              ... on ClosedEvent {{
                actor {{
                  login
                }}
                createdAt
              }}
              ... on LabeledEvent {{
                label {{
                  name
                }}
                actor {{
                  login
                }}
                createdAt
              }}
              ... on UnlabeledEvent {{
                label {{
                  name
                }}
                actor {{
                  login
                }}
                createdAt
              }}
              ... on IssueComment {{
                author {{
                  login
                }}
                createdAt
                lastEditedAt
              }}
              ... on AssignedEvent {{
                assignee {{
                  ... on User {{
                    login
                  }}
                }}
                createdAt              
              }}
              ... on UnassignedEvent {{
                assignee {{
                  ... on User {{
                    login
                  }}
                }}
                createdAt               
              }}
            }}
          }}
        }}
      }}
    }}
  }}
}}
"""

issues_without_comments_query = """
query ($cursor: String, $chunk: Int) {{
  search(query: "repo:{owner}/{repo} type:issue state:{state} {since_filter}", type:ISSUE first: $chunk, after: $cursor) {{
    issueCount
    pageInfo {{
      endCursor
      hasNextPage
    }}    
    edges {{
      node {{
        ... on Issue {{
          number
          title
          createdAt
          closedAt        
          author {{
            login
          }}
          editor {{
            login
          }}
          timelineItems(
            first: 100
            itemTypes: [CLOSED_EVENT, LABELED_EVENT, UNLABELED_EVENT]
          ) {{
            nodes {{
              __typename
              ... on ClosedEvent {{
                actor {{
                  login
                }}
                createdAt
              }}
              ... on LabeledEvent {{
                label {{
                  name
                }}
                actor {{
                  login
                }}
                createdAt
              }}
              ... on UnlabeledEvent {{
                label {{
                  name
                }}
                actor {{
                  login
                }}
                createdAt
              }}
              ... on AssignedEvent {{
                assignee {{
                  ... on User {{
                    login
                  }}
                }}
                createdAt              
              }}
              ... on UnassignedEvent {{
                assignee {{
                  ... on User {{
                    login
                  }}
                }}
                createdAt               
              }}
            }}
          }}
        }}
      }}
    }}
  }}
}}
"""

pull_requests_query = """
query ($cursor: String, $chunk: Int) {{
  search(query: "repo:{owner}/{repo} is:pr state:{state} {since_filter}", type:ISSUE, first: $chunk, after: $cursor) {{
    issueCount
    pageInfo {{
      endCursor
      hasNextPage
    }}    
    edges {{
      node {{
        ... on PullRequest {{
          number
          title
          createdAt
          author {{
            login
          }}
          mergedAt
          mergedBy {{
            login
          }}
          closedAt
          closed
          mergedAt
          additions
          deletions
          changedFiles    
          files(first: 50) {{
            nodes {{
              path
              additions
              deletions
              changeType
            }}
          }}
          reviews(first: 50) {{
            nodes {{
              author {{
                login
              }}
            }}
          }}
          commits(first: 100) {{
            nodes {{
              commit {{
                authors(first: 10) {{
                  nodes {{
                    name
                    user {{
                      login
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
  }}
}}
"""

merged_pull_requests_query = """
query ($cursor: String, $chunk: Int) {{
  search(query: "repo:{owner}/{repo} is:pr merged:>={since} merged:<={until}", type:ISSUE, first: $chunk, after: $cursor) {{
    issueCount
    pageInfo {{
      endCursor
      hasNextPage
    }}    
    edges {{
      node {{
        ... on PullRequest {{
          number
          title
          createdAt
          author {{
            login
          }}
          mergedAt
          mergedBy {{
            login
          }}
          closedAt
          closed
          mergedAt  
          additions
          deletions
          changedFiles   
          files(first: 50) {{
            nodes {{
              path
              additions
              deletions
              changeType
            }}
          }}
          reviews(first: 50) {{
            nodes {{
              author {{
                login
              }}
            }}
          }}
          commits(first: 100) {{
            nodes {{
              commit {{
                authors(first: 10) {{
                  nodes {{
                    name
                    user {{
                      login
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
  }}
}}
"""


async def get_raw_pull_requests(owner: str, repo: str, token: str, state: str = 'open',
                                chunk: int = 50, since: datetime | None = None,
                                use_updated: bool = False,
                                verbose: bool = False, debug_log_list: list[str] | None = None,
                                repo_key: str | None = None) -> list[dict]:
    cursor = None
    pull_requests = []
    count = 0
    total_cost = 0
    total_requests = 0
    remaining = 0

    if since is None:
        since = datetime.now() - timedelta(days=365 * 10)

    since_str = since.astimezone(pytz.utc).strftime('%Y-%m-%d')
    until_str = datetime.now().astimezone(pytz.utc).strftime('%Y-%m-%d')

    async with httpx.AsyncClient(timeout=60) as client:
        gh = gidgethub.httpx.GitHubAPI(client, owner, oauth_token=token)
        if state == 'merged':
            query = merged_pull_requests_query.format(owner=owner, repo=repo,
                                                      since=since_str, until=until_str)
        else:
            since_filter = f'updated:>={since_str}' if (state == 'closed' or use_updated) else f'created:>={since_str}'
            query = pull_requests_query.format(owner=owner, repo=repo, state=state,
                                               since_filter=since_filter)

        while True:
            result = await _graphql_with_retry(gh, query, cursor=cursor, chunk=chunk,
                                               repo_key=repo_key)
            if debug_log_list is not None:
                debug_log_list.append(f'Query: {query}\n\nResponse: {result}\n\n')

            total_requests += 1
            data = result['search']
            if 'edges' in data:
                for pull_request in data['edges']:
                    pull_requests.append(pull_request['node'])

            if data['pageInfo']['hasNextPage']:
                cursor = data['pageInfo']['endCursor']
            else:
                break

    if verbose:
        print(f'GitHub API stats for {repo}:')
        print(f'  Total requests: {total_requests}')
        print(f'  Total cost: {total_cost}')
        print(f'  Average cost per request: {total_cost / total_requests}')
        print(f'  Remaining: {remaining}')
    return pull_requests


async def get_raw_issues(owner: str, repo: str, token: str, state: str = 'open',
                         chunk: int = 100, include_comments: bool = True,
                         since: datetime | None = None, use_updated: bool = False,
                         verbose: bool = False,
                         debug_log_list: list[str] | None = None,
                         repo_key: str | None = None) -> list[dict]:
    cursor = None
    issues = []
    count = 0
    total_cost = 0
    total_requests = 0
    remaining = 0

    if since is None:
        since = datetime.now() - timedelta(days=365 * 10)

    since_str = since.astimezone(pytz.utc).strftime('%Y-%m-%d')
    filter_key = 'updated' if use_updated else 'created'
    since_filter = f'{filter_key}:>={since_str}'

    async with httpx.AsyncClient(timeout=60) as client:
        gh = gidgethub.httpx.GitHubAPI(client, owner, oauth_token=token)
        reset_at = None

        if include_comments:
            query = issues_with_comments_query.format(owner=owner, repo=repo, state=state, since_filter=since_filter)
        else:
            query = issues_without_comments_query.format(owner=owner, repo=repo, state=state, since_filter=since_filter)

        while True:
            result = await _graphql_with_retry(gh, query, cursor=cursor, chunk=chunk,
                                               repo_key=repo_key)

            if debug_log_list is not None:
                debug_log_list.append(f'Query: {query}\n\nResponse: {result}\n\n')

            total_requests += 1
            data = result['search']
            if 'edges' in data:
                for issue in data['edges']:
                    issues.append(issue['node'])

            if data['pageInfo']['hasNextPage']:
                cursor = data['pageInfo']['endCursor']
            else:
                break

    if verbose:
        print(f'GitHub API stats for {repo}:')
        print(f'  Total requests: {total_requests}')
        print(f'  Total cost: {total_cost}')
        print(f'  Average cost per request: {total_cost / total_requests}')
        print(f'  Remaining: {remaining}')
    return issues
