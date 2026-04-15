"""Async GitHub data fetching via GraphQL."""

import asyncio
import logging
from datetime import datetime, timedelta
import httpx
import gidgethub
import gidgethub.httpx
import pytz

logger = logging.getLogger(__name__)

# Retry settings for transient GitHub errors (rate limits, HTML responses)
_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 5  # seconds


async def _graphql_with_retry(gh, query, *, cursor=None, chunk=100):
    """Call gh.graphql with exponential-backoff retry on transient errors."""
    for attempt in range(_MAX_RETRIES):
        try:
            return await gh.graphql(query, cursor=cursor, chunk=chunk)
        except (gidgethub.GraphQLResponseTypeError, httpx.HTTPStatusError) as exc:
            if attempt == _MAX_RETRIES - 1:
                raise
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
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
        }}
      }}
    }}
  }}
}}
"""


async def get_raw_pull_requests(owner: str, repo: str, token: str, state: str = 'open',
                                chunk: int = 100, since: datetime | None = None,
                                verbose: bool = False, debug_log_list: list[str] | None = None) -> list[dict]:
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
            since_filter = f'updated:>={since_str}' if state == 'closed' else f'created:>={since_str}'
            query = pull_requests_query.format(owner=owner, repo=repo, state=state,
                                               since_filter=since_filter)

        while True:
            result = await _graphql_with_retry(gh, query, cursor=cursor, chunk=chunk)
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
                         debug_log_list: list[str] | None = None) -> list[dict]:
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
            result = await _graphql_with_retry(gh, query, cursor=cursor, chunk=chunk)

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
