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
from ..cache import get_cached_issues, get_cached_prs

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
):
    """Time-series: open issue counts over time."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    issues = await get_cached_issues(db, repo_id)
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=months * 30)

    return open_issue_counts_data(start, end, issues, bug_labels=["bug"],
                                  interval=interval)


@router.get("/time-to-merge")
async def chart_time_to_merge(
    request: Request,
    owner: str,
    repo: str,
):
    """Month-bucketed time-to-merge box-plot data."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    prs = await get_cached_prs(db, repo_id, state="merged")
    return time_to_merge_data(prs)


@router.get("/time-to-close")
async def chart_time_to_close(
    request: Request,
    owner: str,
    repo: str,
):
    """Month-bucketed time-to-close-issues box-plot data."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    issues = await get_cached_issues(db, repo_id, state="closed")
    return time_to_close_issues_data(issues)


@router.get("/time-to-response")
async def chart_time_to_response(
    request: Request,
    owner: str,
    repo: str,
    months: int = Query(12, ge=1, le=60),
):
    """Month-bucketed time-to-first-response box-plot data."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    open_issues = await get_cached_issues(db, repo_id, state="open")
    closed_issues = await get_cached_issues(db, repo_id, state="closed")
    since = datetime.now(tz=timezone.utc) - timedelta(days=months * 30)

    return time_to_first_response_data(open_issues, closed_issues, since=since)


@router.get("/label-frequency")
async def chart_label_frequency(
    request: Request,
    owner: str,
    repo: str,
):
    """Label frequency bar chart data."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    issues = await get_cached_issues(db, repo_id, state="open")
    return label_frequency_data(issues)


@router.get("/files-changed")
async def chart_files_changed(
    request: Request,
    owner: str,
    repo: str,
):
    """Month-bucketed files changed per PR data."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    prs = await get_cached_prs(db, repo_id)
    return files_changed_data(prs)


@router.get("/lines-changed")
async def chart_lines_changed(
    request: Request,
    owner: str,
    repo: str,
):
    """Month-bucketed lines changed per PR data."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    prs = await get_cached_prs(db, repo_id)
    return lines_changed_data(prs)


@router.get("/top-terms")
async def chart_top_terms(
    request: Request,
    owner: str,
    repo: str,
    min_count: int = Query(5, ge=1),
):
    """Term frequency data from issue titles (for word cloud)."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    issues = await get_cached_issues(db, repo_id)
    return top_terms_data(issues, min_count=min_count)


@router.get("/top-files")
async def chart_top_files(
    request: Request,
    owner: str,
    repo: str,
    min_count: int = Query(5, ge=1),
):
    """File change frequency data from PRs."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    prs = await get_cached_prs(db, repo_id)
    return top_files_data(prs, min_count=min_count)
