"""Aggregate routes — cross-repo summary and chart data."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Query, Request

from ...core.analyzer import (
    closed_issues_data,
    files_changed_data,
    label_frequency_data,
    lines_changed_data,
    open_issue_counts_data,
    pr_activity_data,
    revisits_data,
    time_to_close_issues_data,
    time_to_first_response_data,
    time_to_merge_data,
    top_files_data,
    top_terms_data,
)
from ..cache import get_cached_issues, get_cached_prs, get_cached_team_members

router = APIRouter(prefix="/api/aggregate", tags=["aggregate"])


async def _collect_all_issues(request: Request, state: str | None = None):
    """Collect issues across all repos."""
    db = request.app.state.db
    repos = await db.get_all_repos()
    all_issues = []
    for r in repos:
        issues = await get_cached_issues(db, r["id"], state=state)
        all_issues.extend(issues)
    return all_issues


async def _collect_all_prs(request: Request, state: str | None = None):
    """Collect PRs across all repos."""
    db = request.app.state.db
    repos = await db.get_all_repos()
    all_prs = []
    for r in repos:
        prs = await get_cached_prs(db, r["id"], state=state)
        all_prs.extend(prs)
    return all_prs


@router.get("/summary")
async def aggregate_summary(request: Request):
    """Combined issue/PR counts across all repos."""
    db = request.app.state.db
    repos = await db.get_all_repos()

    total_open_issues = 0
    total_closed_issues = 0
    total_open_prs = 0
    total_merged_prs = 0
    total_closed_prs = 0
    repo_summaries = []

    for r in repos:
        rid = r["id"]
        open_i = len(await get_cached_issues(db, rid, state="open"))
        closed_i = len(await get_cached_issues(db, rid, state="closed"))
        open_p = len(await get_cached_prs(db, rid, state="open"))
        merged_p = len(await get_cached_prs(db, rid, state="merged"))
        closed_p = len(await get_cached_prs(db, rid, state="closed"))

        total_open_issues += open_i
        total_closed_issues += closed_i
        total_open_prs += open_p
        total_merged_prs += merged_p
        total_closed_prs += closed_p

        repo_summaries.append({
            "owner": r["owner"], "name": r["name"],
            "open_issues": open_i, "closed_issues": closed_i,
            "open_prs": open_p, "merged_prs": merged_p, "closed_prs": closed_p,
        })

    return {
        "total_open_issues": total_open_issues,
        "total_closed_issues": total_closed_issues,
        "total_open_prs": total_open_prs,
        "total_merged_prs": total_merged_prs,
        "total_closed_prs": total_closed_prs,
        "repos": repo_summaries,
    }


@router.get("/charts/{chart_type}")
async def aggregate_chart(
    request: Request,
    chart_type: str,
    months: int = Query(12, ge=1, le=60),
    min_count: int = Query(5, ge=1),
):
    """Cross-repo chart data (merged from all repos)."""
    if chart_type == "open-issues":
        issues = await _collect_all_issues(request)
        end = datetime.now()
        start = end - timedelta(days=months * 30)
        return open_issue_counts_data(start, end, issues, bug_labels=["bug"])
    elif chart_type == "time-to-merge":
        prs = await _collect_all_prs(request, state="merged")
        return time_to_merge_data(prs)
    elif chart_type == "time-to-close":
        issues = await _collect_all_issues(request, state="closed")
        return time_to_close_issues_data(issues)
    elif chart_type == "time-to-response":
        open_issues = await _collect_all_issues(request, state="open")
        closed_issues = await _collect_all_issues(request, state="closed")
        since = datetime.now() - timedelta(days=months * 30)
        return time_to_first_response_data(open_issues, closed_issues, since=since)
    elif chart_type == "label-frequency":
        issues = await _collect_all_issues(request, state="open")
        return label_frequency_data(issues)
    elif chart_type == "files-changed":
        prs = await _collect_all_prs(request)
        return files_changed_data(prs)
    elif chart_type == "lines-changed":
        prs = await _collect_all_prs(request)
        return lines_changed_data(prs)
    elif chart_type == "top-terms":
        issues = await _collect_all_issues(request)
        return top_terms_data(issues, min_count=min_count)
    elif chart_type == "top-files":
        prs = await _collect_all_prs(request)
        return top_files_data(prs, min_count=min_count)
    else:
        from fastapi import HTTPException
        raise HTTPException(400, f"Unknown chart type: {chart_type}")


@router.get("/reports/{report_type}")
async def aggregate_report(
    request: Request,
    report_type: str,
    days: int = Query(7, ge=1),
    stale: int = Query(30, ge=1),
    bug_label: str = Query("bug"),
    show_all: bool = Query(False),
):
    """Cross-repo report data."""
    db = request.app.state.db
    repos = await db.get_all_repos()
    now = datetime.now()

    if report_type == "revisits":
        results = []
        for r in repos:
            issues = await get_cached_issues(db, r["id"], state="open")
            members = await get_cached_team_members(db, r["id"])
            result = revisits_data(now, r["owner"], r["name"], issues, members,
                                   bug_label=bug_label, days=days, stale=stale,
                                   show_all=show_all)
            results.append(result)
        return {"repos": results}
    elif report_type == "pr-activity":
        results = []
        for r in repos:
            open_prs = await get_cached_prs(db, r["id"], state="open")
            closed_prs = await get_cached_prs(db, r["id"], state="closed")
            merged_prs = await get_cached_prs(db, r["id"], state="merged")
            result = pr_activity_data(now, r["owner"], r["name"],
                                      open_prs, closed_prs + merged_prs,
                                      days=days, show_all=show_all)
            results.append(result)
        return {"repos": results}
    elif report_type == "closed-issues":
        results = []
        for r in repos:
            closed = await get_cached_issues(db, r["id"], state="closed")
            result = closed_issues_data(now, r["owner"], r["name"], closed, days=days)
            results.append(result)
        return {"repos": results}
    else:
        from fastapi import HTTPException
        raise HTTPException(400, f"Unknown report type: {report_type}")
