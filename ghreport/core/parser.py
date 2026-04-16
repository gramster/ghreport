"""Parsing, filtering, and data transformation for ghreport."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Generator, Iterable

import pytz

from .models import Event, Issue, PullRequest
from .fetcher import get_raw_issues, get_raw_pull_requests


utc = pytz.UTC

# Module-level timezone; set by the caller before use.
localtz = pytz.timezone('America/Los_Angeles')


def set_timezone(tz_name: str):
    global localtz
    localtz = pytz.timezone(tz_name)


def utc_to_local(utc_dt: datetime) -> datetime:
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=localtz)


def date_diff(end: datetime, start: datetime) -> timedelta:
    return end - start


def get_who(obj, prop: str, fallback: str | None = None) -> str:
    if prop in obj:
        v = obj[prop]
        if v:
            return v['login']
    if fallback:
        return fallback
    raise Exception(f'No {prop} in {obj}')


def parse_date(datestr: str) -> datetime:
    return utc_to_local(datetime.strptime(datestr, '%Y-%m-%dT%H:%M:%SZ'))


def format_date(d: datetime) -> str:
    return f'{d.year}-{d.month:02d}-{d.day:02d}'


def median(numbers: list[int]) -> int:
    sorted_numbers = sorted(numbers)
    n = len(sorted_numbers)
    return sorted_numbers[n // 2]


def parse_raw_pull_request(pull_request: dict) -> PullRequest | None:
    try:
        number: int = pull_request['number']
        title: str = pull_request['title']
        created_at: datetime = parse_date(pull_request['createdAt'])
        created_by: str = get_who(pull_request, 'author', 'UNKNOWN')
        merged_at: datetime | None = parse_date(pull_request['mergedAt']) if pull_request['mergedAt'] else None
        closed_at: datetime | None = parse_date(pull_request['closedAt']) if pull_request.get('closedAt') else None
        closed_by: str | None = get_who(pull_request, 'mergedBy', None) if pull_request.get('mergedBy') else None
        additions: int = pull_request['additions']
        deletions: int = pull_request['deletions']
        changed_files: int = pull_request['changedFiles']
        files: list[str] = [f['path'] for f in pull_request['files']['nodes']]

        # Extract unique reviewers (excluding PR author)
        reviewers: list[str] = []
        if 'reviews' in pull_request:
            seen: set[str] = set()
            for node in pull_request['reviews'].get('nodes', []):
                if node and node.get('author'):
                    login = node['author'].get('login', '')
                    if login and login != created_by and login not in seen:
                        seen.add(login)
                        reviewers.append(login)

        # Collaborators = all commit authors/co-authors, excluding PR author
        seen_collab: set[str] = set()
        collaborators: list[str] = []
        if 'commits' in pull_request:
            for node in pull_request['commits'].get('nodes', []):
                commit = node.get('commit', {}) if node else {}
                # Use authors (plural) which includes co-authors from trailers
                authors_data = commit.get('authors', {}) or {}
                author_nodes = authors_data.get('nodes', [])
                # Fallback to singular author for old cached data
                if not author_nodes:
                    single = commit.get('author')
                    if single:
                        author_nodes = [single]
                for author in author_nodes:
                    if not author:
                        continue
                    user = author.get('user') or {}
                    login = user.get('login', '')
                    # For bots/apps, user is null — derive login from name
                    if not login:
                        name = author.get('name', '')
                        if name and name.endswith('[bot]'):
                            login = f"app/{name[:-5]}"
                    if login and login != created_by and login not in seen_collab:
                        seen_collab.add(login)
                        collaborators.append(login)
    except Exception as e:
        print(f'Failed to parse pull_request\n{pull_request}: {e}')
        return None

    return PullRequest(number, title, created_at, created_by, merged_at, closed_at, closed_by,
                       additions + deletions, changed_files, files,
                       reviewers=reviewers, collaborators=collaborators)


def get_active_labels(events: list[Event], at: datetime | None = None) -> set[str]:
    labels = set()
    for e in events:
        if at and e.when > at:
            break
        if e.event == 'labeled':
            labels.add(e.arg)
        elif e.event == 'unlabeled' and e.arg in labels:
            labels.remove(e.arg)
    return labels


def parse_raw_issue(issue: dict, members: set[str]) -> Issue | None:
    try:
        number = issue['number']
        title = issue['title']
        created_by: str = get_who(issue, 'author', 'UNKNOWN')
        closed_by: str | None = None
        created_at: datetime = parse_date(issue['createdAt'])
        closed_at: datetime | None = parse_date(issue['closedAt']) if issue['closedAt'] else None
        events = []

        response_at = created_at if created_by in members else None
        first_team_response_at = response_at
        last_team_response_at = response_at
        last_op_response_at = response_at
        last_response_at = response_at

        for event in issue['timelineItems']['nodes']:
            typename = event['__typename']
            eventtime = parse_date(event['createdAt'])
            if typename == 'ClosedEvent':
                closed_by = get_who(event, 'actor', 'UNKNOWN')
                continue
            elif typename == 'LabeledEvent':
                lbl = event['label']['name']
                who = get_who(event, 'actor', 'UNKNOWN')
                e = Event(eventtime, who, 'labeled', lbl)
            elif typename == 'UnlabeledEvent':
                lbl = event['label']['name']
                who = get_who(event, 'actor', 'UNKNOWN')
                e = Event(eventtime, who, 'unlabeled', lbl)
            elif typename == 'AssignedEvent':
                who = get_who(event, 'assignee', 'UNKNOWN')
                e = Event(eventtime, who, 'assigned', '')
            elif typename == 'UnassignedEvent':
                who = get_who(event, 'assignee', 'UNKNOWN')
                e = Event(eventtime, who, 'unassigned', '')
            elif typename == 'IssueComment':
                l = event['lastEditedAt']
                if l:
                    eventtime = parse_date(event['lastEditedAt'])
                who = get_who(event, 'author', 'UNKNOWN')
                if who in members:
                    last_team_response_at = eventtime
                    if first_team_response_at is None:
                        first_team_response_at = eventtime
                if who == created_by:
                    last_op_response_at = eventtime
                last_response_at = eventtime
                e = Event(eventtime, who, 'comment', '')
            else:
                print(f'Unknown event type {typename}')
                continue
            events.append(e)
    except Exception as e:
        print(f'Failed to parse issue\n{issue}: {e}')
        return None

    return Issue(number, title, created_by, closed_by, created_at, closed_at,
                 first_team_response_at, last_team_response_at,
                 last_op_response_at, last_response_at, events)


def get_pull_requests(owner: str, repo: str, token: str, state: str = 'open',
                      chunk: int = 100, raw_pull_requests: list[dict[str, str]] | None = None,
                      since: datetime | None = None, verbose: bool = False) -> list[PullRequest]:
    if raw_pull_requests is None:
        try:
            raw_pull_requests = asyncio.run(get_raw_pull_requests(owner, repo, token,
                                                                  state=state, chunk=chunk,
                                                                  since=since,
                                                                  verbose=verbose))
        except Exception as e:
            print(f"Error getting pull requests for {owner}/{repo}: {e}")
            raw_pull_requests = []

    pull_requests = []
    for issue in raw_pull_requests:
        parsed_pull_request = parse_raw_pull_request(issue)
        if parsed_pull_request:
            pull_requests.append(parsed_pull_request)

    return pull_requests


def get_issues(owner: str, repo: str, token: str, members: set[str], state: str = 'open',
               chunk: int = 25, raw_issues: list[dict[str, str]] | None = None,
               include_comments: bool = True, since: datetime | None = None,
               verbose: bool = False) -> dict[str, Issue]:
    if raw_issues is None:
        raw_issues = asyncio.run(get_raw_issues(owner, repo, token,
                                                state=state, chunk=chunk,
                                                include_comments=include_comments,
                                                since=since,
                                                verbose=verbose))
    issues = {}
    for issue in raw_issues:
        parsed_issue = parse_raw_issue(issue, members)
        if parsed_issue:
            issues[issue['number']] = parsed_issue
    return issues


def filter_issues(issues: Iterable[Issue],
                  must_include_labels: list[str] | None = None,
                  must_exclude_labels: list[str] | None = None,
                  must_be_created_by: set[str] | None = None,
                  must_not_be_created_by: set[str] | None = None,
                  must_be_open_at: datetime | None = None) -> Generator[Issue, None, None]:
    """Get issues that were open at the given time and have (or don't have) the given labels."""
    for i in issues:
        if must_be_created_by and i.created_by not in must_be_created_by:
            continue
        if must_not_be_created_by and i.created_by in must_not_be_created_by:
            continue
        if must_be_open_at:
            created_at = utc_to_local(i.created_at)
            if created_at > must_be_open_at:
                continue
            if i.closed_at is not None:
                closed_at = utc_to_local(i.closed_at)
                if closed_at < must_be_open_at:
                    continue

        if must_include_labels or must_exclude_labels:
            labels = get_active_labels(i.events, at=must_be_open_at)
            match = True
            if must_include_labels:
                if not labels:
                    match = False
                else:
                    for l in must_include_labels:
                        if l not in labels:
                            match = False
                            break
            if must_exclude_labels and labels:
                for l in must_exclude_labels:
                    if l in labels:
                        match = False
                        break
            if not match:
                continue

        yield i


def filter_prs_by_time(pull_requests: list[PullRequest],
                       created_after: datetime | None = None,
                       created_before: datetime | None = None,
                       closed_after: datetime | None = None,
                       closed_before: datetime | None = None,
                       must_be_open: bool = False,
                       must_be_closed: bool = False,
                       must_be_merged: bool = False) -> list[PullRequest]:
    """Filter pull requests by time criteria."""
    result = []
    for pr in pull_requests:
        if created_after and pr.created_at < created_after:
            continue
        if created_before and pr.created_at > created_before:
            continue
        if closed_after and (not pr.closed_at or pr.closed_at < closed_after):
            continue
        if closed_before and pr.closed_at and pr.closed_at > closed_before:
            continue
        if must_be_open and pr.closed_at is not None:
            continue
        if must_be_closed and pr.closed_at is None:
            continue
        if must_be_merged and pr.merged_at is None:
            continue
        result.append(pr)
    return result
