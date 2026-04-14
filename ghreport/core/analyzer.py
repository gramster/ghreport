"""Analysis functions for ghreport.

Each report type has two layers:
  - A data function (*_data) that returns structured dicts/lists — no formatter dependency.
    These are used by the dashboard API.
  - A formatted function that calls the data function and renders via a formatter.
    These are used by the CLI.
"""

from datetime import datetime, timedelta
from typing import Any, Callable, Generator

from .models import Event, Issue, PullRequest
from .parser import (
    date_diff, filter_issues, filter_prs_by_time, format_date,
    get_active_labels, median, utc_to_local,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_subset(issues: list[Issue], members: set[str], bug_flag: bool,
               bug_label: str = 'bug') -> Generator[Issue, None, None]:
    return filter_issues(issues, must_include_labels=[bug_label], must_not_be_created_by=members) if bug_flag \
        else filter_issues(issues, must_exclude_labels=[bug_label], must_not_be_created_by=members)


def calculate_ranges(data: list[PullRequest] | list[Issue],
                     get_start_date: Callable[[Any], datetime],
                     get_metric: Callable[[Any], int],
                     since: datetime | None = None) -> dict[str, list[int]]:
    if since is not None:
        since = utc_to_local(since)
    months: dict[str, list[int]] = {}
    for item in data:
        start = get_start_date(item)
        if since is not None and start < since:
            continue
        try:
            metric = get_metric(item)
            month = f'{start.year}-{start.month:02}'[2:]
            if month not in months:
                months[month] = []
            months[month].append(metric)
        except:
            pass
    return months


def calculate_medians(data: list[PullRequest] | list[Issue],
                      get_start_date: Callable[[Any], datetime],
                      get_metric: Callable[[Any], int],
                      since: datetime | None = None) -> dict[str, int]:
    months = calculate_ranges(data, get_start_date, get_metric, since)
    medians = {}
    for month, times in months.items():
        medians[month] = median(times)
    return medians


# ---------------------------------------------------------------------------
# Data functions — return structured data for the dashboard API
# ---------------------------------------------------------------------------

def revisits_data(now: datetime, owner: str, repo: str, issues: list[Issue],
                  members: set[str], bug_label: str = 'bug', days: int = 7,
                  stale: int = 30, show_all: bool = False) -> dict[str, Any]:
    """Return structured revisit data as a dict of categories.

    Returns dict with keys:
        "bugs" and "non_bugs", each containing:
            "needs_response": list of issue dicts
            "op_responded": list of issue dicts
            "third_party_responded": list of issue dicts
            "stale": list of issue dicts
    Each issue dict has: number, title, created_by, created_at, star, days_* fields.
    """
    now_local = utc_to_local(datetime.now())
    result: dict[str, Any] = {
        "owner": owner,
        "repo": repo,
        "generated_at": format_date(now),
        "stale_days": stale,
        "show_all": show_all,
        "window_days": days,
        "sections": {},
    }

    for bug_flag in [True, False]:
        section_key = "bugs" if bug_flag else "non_bugs"
        section: dict[str, list[dict]] = {
            "needs_response": [],
            "op_responded": [],
            "third_party_responded": [],
            "stale": [],
        }
        shown = set()

        # Needs team response
        for issue in get_subset(issues, members, bug_flag, bug_label):
            if not issue.closed_at and not issue.last_team_response_at:
                diff = date_diff(now_local, issue.created_at).days
                star = diff <= days
                if star or show_all:
                    shown.add(issue.number)
                    section["needs_response"].append({
                        "number": issue.number, "title": issue.title,
                        "created_by": issue.created_by,
                        "created_at": format_date(issue.created_at),
                        "star": star, "days_op": diff,
                    })

        # OP responded after team
        for issue in get_subset(issues, members, bug_flag, bug_label):
            if issue.closed_at or not issue.last_team_response_at or issue.number in shown:
                continue
            if issue.last_op_response_at and issue.last_op_response_at > issue.last_team_response_at:
                op_days = date_diff(now_local, issue.last_op_response_at).days
                team_days = date_diff(now_local, issue.last_team_response_at).days
                star = op_days <= days
                if star or show_all:
                    shown.add(issue.number)
                    section["op_responded"].append({
                        "number": issue.number, "title": issue.title,
                        "created_by": issue.created_by,
                        "created_at": format_date(issue.created_at),
                        "star": star, "days_op": op_days, "days_team": team_days,
                    })

        # 3rd party responded after team
        for issue in get_subset(issues, members, bug_flag, bug_label):
            if issue.closed_at or issue.number in shown:
                continue
            elif issue.last_response_at is not None and issue.last_team_response_at is not None and \
                    issue.last_response_at > issue.last_team_response_at:
                other_days = date_diff(now_local, issue.last_response_at).days
                team_days = date_diff(now_local, issue.last_team_response_at).days
                star = other_days <= days
                if star or show_all:
                    shown.add(issue.number)
                    section["third_party_responded"].append({
                        "number": issue.number, "title": issue.title,
                        "created_by": issue.created_by,
                        "created_at": format_date(issue.created_at),
                        "star": star, "days_third_party": other_days, "days_team": team_days,
                    })

        # Stale
        for issue in get_subset(issues, members, bug_flag, bug_label):
            if issue.closed_at or issue.number in shown:
                continue
            elif issue.last_team_response_at and issue.last_response_at == issue.last_team_response_at:
                diff = date_diff(now_local, issue.last_response_at).days
                if diff < stale:
                    continue
                star = diff < (stale + days)
                if star or show_all:
                    shown.add(issue.number)
                    section["stale"].append({
                        "number": issue.number, "title": issue.title,
                        "created_by": issue.created_by,
                        "created_at": format_date(issue.created_at),
                        "star": star, "days_team": diff,
                    })

        result["sections"][section_key] = section

    return result


def pr_activity_data(now: datetime, owner: str, repo: str,
                     open_prs: list[PullRequest], closed_prs: list[PullRequest],
                     days: int = 1, show_all: bool = False) -> dict[str, Any]:
    """Return structured PR activity data."""
    cutoff = now - timedelta(days=days)
    week_ago = now - timedelta(days=7)

    newly_opened = filter_prs_by_time(open_prs + closed_prs, created_after=cutoff)
    newly_merged = filter_prs_by_time(closed_prs, closed_after=cutoff, must_be_merged=True)
    newly_closed = [pr for pr in filter_prs_by_time(closed_prs, closed_after=cutoff, must_be_closed=True)
                    if pr.merged_at is None]
    stale_open = filter_prs_by_time(open_prs, created_before=week_ago, must_be_open=True) \
        if days >= 7 else []

    def pr_to_dict(pr: PullRequest, ref_date: datetime | None = None) -> dict:
        actual_closed_at = pr.merged_at or pr.closed_at
        if actual_closed_at:
            days_open = date_diff(actual_closed_at, pr.created_at).days
        else:
            days_open = date_diff(now, pr.created_at).days
        return {
            "number": pr.number, "title": pr.title,
            "created_by": pr.created_by,
            "created_at": format_date(pr.created_at),
            "merged_at": format_date(pr.merged_at) if pr.merged_at else None,
            "closed_at": format_date(pr.closed_at) if pr.closed_at else None,
            "closed_by": pr.closed_by,
            "days_open": days_open,
            "lines_changed": pr.lines_changed,
            "files_changed": pr.files_changed,
        }

    return {
        "owner": owner, "repo": repo,
        "window_days": days,
        "newly_opened": [pr_to_dict(pr) for pr in sorted(newly_opened, key=lambda x: x.created_at, reverse=True)],
        "newly_merged": [pr_to_dict(pr) for pr in sorted(newly_merged, key=lambda x: x.merged_at or x.closed_at, reverse=True)],
        "newly_closed": [pr_to_dict(pr) for pr in sorted(newly_closed, key=lambda x: x.closed_at, reverse=True)],
        "stale_open": [pr_to_dict(pr) for pr in sorted(stale_open, key=lambda x: x.created_at)],
    }


def closed_issues_data(now: datetime, owner: str, repo: str,
                       closed_issues: list[Issue], days: int = 1) -> dict[str, Any]:
    """Return structured closed issues data."""
    cutoff = now - timedelta(days=days)
    recently_closed = [i for i in closed_issues if i.closed_at and i.closed_at >= cutoff]
    return {
        "owner": owner, "repo": repo,
        "window_days": days,
        "issues": [{
            "number": i.number, "title": i.title,
            "created_by": i.created_by,
            "created_at": format_date(i.created_at),
            "closed_at": format_date(i.closed_at) if i.closed_at else None,
            "closed_by": i.closed_by,
            "days_open": date_diff(i.closed_at, i.created_at).days if i.closed_at else 0,
        } for i in sorted(recently_closed, key=lambda x: x.closed_at or x.created_at, reverse=True)],
    }


# ---------------------------------------------------------------------------
# Chart data functions — return JSON-serializable data for frontend charts
# ---------------------------------------------------------------------------

def open_issue_counts_data(start: datetime, end: datetime, issues: list[Issue],
                           bug_labels: list[str], interval: int = 7) -> dict[str, Any]:
    """Return time-series data for open issue counts."""
    points = []
    t = start
    while t < end:
        t_local = utc_to_local(t)
        bugs = len(list(filter_issues(issues, must_include_labels=bug_labels, must_be_open_at=t_local)))
        all_issues = len(list(filter_issues(issues, must_be_open_at=t_local)))
        points.append({
            "date": format_date(t),
            "all_issues": all_issues,
            "bugs": bugs,
        })
        t += timedelta(days=interval)
    return {"points": points}


def time_to_merge_data(pull_requests: list[PullRequest]) -> dict[str, Any]:
    """Return month-bucketed time-to-merge data for box plots."""
    ranges = calculate_ranges(pull_requests, lambda x: x.created_at,
                              lambda x: date_diff(x.merged_at, x.created_at).days)
    return {"months": {k: sorted(v) for k, v in sorted(ranges.items())}}


def time_to_close_issues_data(issues: list[Issue]) -> dict[str, Any]:
    """Return month-bucketed time-to-close data for box plots."""
    ranges = calculate_ranges(issues, lambda x: x.created_at,
                              lambda x: date_diff(x.closed_at, x.created_at).days)
    return {"months": {k: sorted(v) for k, v in sorted(ranges.items())}}


def time_to_first_response_data(open_issues: list[Issue], closed_issues: list[Issue],
                                since: datetime) -> dict[str, Any]:
    """Return month-bucketed time-to-first-response data."""
    issues = list(open_issues) + list(closed_issues)
    ranges = calculate_ranges(issues, lambda x: x.created_at,
                              lambda x: date_diff(x.first_team_response_at, x.created_at).days,
                              since=since)
    return {"months": {k: sorted(v) for k, v in sorted(ranges.items())}}


def label_frequency_data(issues: list[Issue]) -> dict[str, Any]:
    """Return label frequency counts."""
    labelcounts: dict[str, int] = {}
    now = utc_to_local(datetime.now())
    for issue in issues:
        labels = get_active_labels(issue.events, at=now)
        for label in labels:
            labelcounts[label] = labelcounts.get(label, 0) + 1
    sorted_labels = sorted(labelcounts.items(), key=lambda item: item[1], reverse=True)
    return {"labels": [{"name": k, "count": v} for k, v in sorted_labels]}


def files_changed_data(prs: list[PullRequest]) -> dict[str, Any]:
    """Return month-bucketed files changed per PR data."""
    ranges = calculate_ranges(prs, lambda x: x.created_at, lambda x: x.files_changed)
    return {"months": {k: sorted(v) for k, v in sorted(ranges.items())}}


def lines_changed_data(prs: list[PullRequest]) -> dict[str, Any]:
    """Return month-bucketed lines changed per PR data."""
    ranges = calculate_ranges(prs, lambda x: x.created_at, lambda x: x.lines_changed)
    return {"months": {k: sorted(v) for k, v in sorted(ranges.items())}}


def top_terms_data(issues: list[Issue], min_count: int = 5) -> dict[str, Any]:
    """Return term frequency data from issue titles."""
    stopwords = ['a', 'an', 'the', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'from',
                 'as', 'is', 'are', 'be', 'it', 'this', 'that', 'these', 'those', 'there', 'here', 'where',
                 'when', 'how', 'why', 'what', 'which', 'who', 'whom', 'whose', 'i', 'you', 'he', 'she',
                 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'mine', 'your', 'yours',
                 'his', 'her', 'hers', 'its', 'our', 'ours', 'their', 'theirs', 'myself', 'yourself',
                 'himself', 'herself', 'itself', 'ourselves', 'yourselves', 'themselves', 'all',
                 'cannot', 'without', 'name', 'vs', 'pylance', 'python', 'show', 'add', 'support',
                 'not', 'after', 'does', 'no', 'working', 'doesn\'t', 'can\'t', 'won\'t', 'shouldn\'t',
                 'unable', 'visual', 'studio', 'up', 'if', 'only', 'microsoft', 'using', '-',
                 'work', 'should', 'vscode', 'don\'t', 'offer', 'over', 'incorrect', 'inside',
                 'being', 'could', 'go', 'showing', 'have', 'shown', 'even', 'has', 'instead',
                 'recognized', 'issue', 'new', 'allow', 'fails', 'out', 'long', 'available',
                 'problem', 'get', 'until', 'can', 'like', 'debugpy']
    issues_with_term: dict[str, list[int]] = {}
    for issue in issues:
        title = issue.title.lower()
        for word in title.split():
            if word in stopwords:
                continue
            if word not in issues_with_term:
                issues_with_term[word] = []
            if issue.number not in issues_with_term[word]:
                issues_with_term[word].append(issue.number)

    sorted_terms = sorted(issues_with_term.items(), key=lambda x: len(x[1]), reverse=True)
    return {
        "terms": [{"term": k, "count": len(v), "issue_numbers": v}
                  for k, v in sorted_terms if len(v) >= min_count],
    }


def top_files_data(pull_requests: list[PullRequest], min_count: int = 5) -> dict[str, Any]:
    """Return file change frequency data from PRs."""
    files: dict[str, int] = {}
    for pr in pull_requests:
        for file in pr.files:
            files[file] = files.get(file, 0) + 1
    sorted_files = sorted(files.items(), key=lambda x: x[1], reverse=True)
    return {
        "files": [{"path": k, "count": v} for k, v in sorted_files if v >= min_count],
    }
