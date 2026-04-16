"""Chart data routes — JSON data for frontend Chart.js rendering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from ...core.analyzer import (
    files_changed_data,
    label_frequency_data,
    lines_changed_data,
    open_issue_counts_data,
    time_to_close_issues_data,
    time_to_first_response_data,
    time_to_merge_data,
    top_files_data,
    top_terms_data,
)
from ..cache import (
    enrich_team_response,
    filter_active_issues,
    filter_active_prs,
    get_cached_issues,
    get_cached_prs,
    get_cached_team_members,
    parse_date_param,
)

router = APIRouter(prefix="/api/repos/{owner}/{repo}/charts", tags=["charts"])


async def _get_repo_id_or_404(request: Request, owner: str, repo: str) -> int:
    repo_id = await request.app.state.db.get_repo_id(owner, repo)
    if not repo_id:
        raise HTTPException(404, f"Repository {owner}/{repo} not found")
    return repo_id


@router.get("/open-issues")
async def chart_open_issues(
    request: Request,
    owner: str,
    repo: str,
    months: int = Query(12, ge=1, le=60),
    interval: int = Query(7, ge=1),
    since: str | None = Query(None),
    until: str | None = Query(None),
):
    """Time-series: open issue counts over time."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)
    since_dt = parse_date_param(since)
    until_dt = parse_date_param(until, end_of_day=True)

    issues = await get_cached_issues(db, repo_id)
    issues = filter_active_issues(issues, since_dt, until_dt)
    end = until_dt or datetime.now(tz=timezone.utc)
    start = since_dt or (end - timedelta(days=months * 30))

    return open_issue_counts_data(start, end, issues, bug_labels=["bug"],
                                  interval=interval)


@router.get("/time-to-merge")
async def chart_time_to_merge(
    request: Request,
    owner: str,
    repo: str,
    since: str | None = Query(None),
    until: str | None = Query(None),
):
    """Month-bucketed time-to-merge box-plot data."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)
    since_dt = parse_date_param(since)
    until_dt = parse_date_param(until, end_of_day=True)

    prs = await get_cached_prs(db, repo_id, state="merged")
    prs = filter_active_prs(prs, since_dt, until_dt)
    return time_to_merge_data(prs)


@router.get("/time-to-close")
async def chart_time_to_close(
    request: Request,
    owner: str,
    repo: str,
    since: str | None = Query(None),
    until: str | None = Query(None),
):
    """Month-bucketed time-to-close-issues box-plot data."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)
    since_dt = parse_date_param(since)
    until_dt = parse_date_param(until, end_of_day=True)

    issues = await get_cached_issues(db, repo_id, state="closed")
    issues = filter_active_issues(issues, since_dt, until_dt)
    return time_to_close_issues_data(issues)


@router.get("/time-to-response")
async def chart_time_to_response(
    request: Request,
    owner: str,
    repo: str,
    months: int = Query(12, ge=1, le=60),
    since: str | None = Query(None),
    until: str | None = Query(None),
):
    """Month-bucketed time-to-first-response box-plot data."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)
    since_dt = parse_date_param(since)
    until_dt = parse_date_param(until, end_of_day=True)

    open_issues = await get_cached_issues(db, repo_id, state="open")
    closed_issues = await get_cached_issues(db, repo_id, state="closed")
    open_issues = filter_active_issues(open_issues, since_dt, until_dt)
    closed_issues = filter_active_issues(closed_issues, since_dt, until_dt)
    resp_since = since_dt or (datetime.now(tz=timezone.utc) - timedelta(days=months * 30))

    # Re-compute first_team_response_at from events + current team members
    members = await get_cached_team_members(db, repo_id)
    enrich_team_response(open_issues, members)
    enrich_team_response(closed_issues, members)

    return time_to_first_response_data(open_issues, closed_issues, since=resp_since)


@router.get("/label-frequency")
async def chart_label_frequency(
    request: Request,
    owner: str,
    repo: str,
    since: str | None = Query(None),
    until: str | None = Query(None),
):
    """Label frequency bar chart data."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)
    since_dt = parse_date_param(since)
    until_dt = parse_date_param(until, end_of_day=True)

    issues = await get_cached_issues(db, repo_id, state="open")
    issues = filter_active_issues(issues, since_dt, until_dt)
    return label_frequency_data(issues)


@router.get("/files-changed")
async def chart_files_changed(
    request: Request,
    owner: str,
    repo: str,
    since: str | None = Query(None),
    until: str | None = Query(None),
):
    """Month-bucketed files changed per PR data."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)
    since_dt = parse_date_param(since)
    until_dt = parse_date_param(until, end_of_day=True)

    prs = await get_cached_prs(db, repo_id)
    prs = filter_active_prs(prs, since_dt, until_dt)
    return files_changed_data(prs)


@router.get("/lines-changed")
async def chart_lines_changed(
    request: Request,
    owner: str,
    repo: str,
    since: str | None = Query(None),
    until: str | None = Query(None),
):
    """Month-bucketed lines changed per PR data."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)
    since_dt = parse_date_param(since)
    until_dt = parse_date_param(until, end_of_day=True)

    prs = await get_cached_prs(db, repo_id)
    prs = filter_active_prs(prs, since_dt, until_dt)
    return lines_changed_data(prs)


@router.get("/top-terms")
async def chart_top_terms(
    request: Request,
    owner: str,
    repo: str,
    min_count: int = Query(5, ge=1),
    since: str | None = Query(None),
    until: str | None = Query(None),
):
    """Term frequency data from issue titles (for word cloud)."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)
    since_dt = parse_date_param(since)
    until_dt = parse_date_param(until, end_of_day=True)

    issues = await get_cached_issues(db, repo_id)
    issues = filter_active_issues(issues, since_dt, until_dt)
    return top_terms_data(issues, min_count=min_count)


@router.get("/top-files")
async def chart_top_files(
    request: Request,
    owner: str,
    repo: str,
    min_count: int = Query(5, ge=1),
    since: str | None = Query(None),
    until: str | None = Query(None),
):
    """File change frequency data from PRs."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)
    since_dt = parse_date_param(since)
    until_dt = parse_date_param(until, end_of_day=True)

    prs = await get_cached_prs(db, repo_id)
    prs = filter_active_prs(prs, since_dt, until_dt)
    return top_files_data(prs, min_count=min_count)
