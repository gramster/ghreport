"""Report routes — structured JSON versions of CLI reports."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

from ...core.analyzer import closed_issues_data, pr_activity_data, revisits_data
from ..cache import get_cached_issues, get_cached_prs, get_cached_team_members

router = APIRouter(prefix="/api/repos/{owner}/{repo}/reports", tags=["reports"])


async def _get_repo_id_or_404(request: Request, owner: str, repo: str) -> int:
    repo_id = await request.app.state.db.get_repo_id(owner, repo)
    if not repo_id:
        raise HTTPException(404, f"Repository {owner}/{repo} not found")
    return repo_id


@router.get("/revisits")
async def report_revisits(
    request: Request,
    owner: str,
    repo: str,
    days: int = Query(7, ge=1),
    stale: int = Query(30, ge=1),
    bug_label: str = Query("bug"),
    show_all: bool = Query(False),
):
    """Issue revisit report — which issues need team attention."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    issues = await get_cached_issues(db, repo_id, state="open")
    members = await get_cached_team_members(db, repo_id)
    now = datetime.now()

    return revisits_data(now, owner, repo, issues, members,
                         bug_label=bug_label, days=days, stale=stale,
                         show_all=show_all)


@router.get("/pr-activity")
async def report_pr_activity(
    request: Request,
    owner: str,
    repo: str,
    days: int = Query(1, ge=1),
    show_all: bool = Query(False),
):
    """PR activity report — newly opened, merged, closed PRs."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    open_prs = await get_cached_prs(db, repo_id, state="open")
    closed_prs = await get_cached_prs(db, repo_id, state="closed")
    merged_prs = await get_cached_prs(db, repo_id, state="merged")
    now = datetime.now()

    return pr_activity_data(now, owner, repo, open_prs,
                            closed_prs + merged_prs, days=days,
                            show_all=show_all)


@router.get("/closed-issues")
async def report_closed_issues(
    request: Request,
    owner: str,
    repo: str,
    days: int = Query(1, ge=1),
):
    """Recently closed issues report."""
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    closed_issues = await get_cached_issues(db, repo_id, state="closed")
    now = datetime.now()

    return closed_issues_data(now, owner, repo, closed_issues, days=days)
