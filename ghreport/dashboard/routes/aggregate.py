"""Aggregate routes — cross-repo summary and chart data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
from ..cache import (
    enrich_team_response,
    filter_active_issues,
    filter_active_prs,
    get_cached_issues,
    get_cached_prs,
    get_cached_team_members,
    parse_date_param,
)

router = APIRouter(prefix="/api/aggregate", tags=["aggregate"])


async def _collect_all_issues(request: Request, state: str | None = None,
                              since_dt=None, until_dt=None,
                              enrich_response: bool = False):
    """Collect issues across all repos, optionally filtered by date."""
    db = request.app.state.db
    repos = await db.get_all_repos()
    all_issues = []
    for r in repos:
        issues = await get_cached_issues(db, r["id"], state=state)
        issues = filter_active_issues(issues, since_dt, until_dt)
        if enrich_response:
            members = await get_cached_team_members(db, r["id"])
            enrich_team_response(issues, members)
        all_issues.extend(issues)
    return all_issues


async def _collect_all_prs(request: Request, state: str | None = None,
                           since_dt=None, until_dt=None):
    """Collect PRs across all repos, optionally filtered by date."""
    db = request.app.state.db
    repos = await db.get_all_repos()
    all_prs = []
    for r in repos:
        prs = await get_cached_prs(db, r["id"], state=state)
        prs = filter_active_prs(prs, since_dt, until_dt)
        all_prs.extend(prs)
    return all_prs


@router.get("/summary")
async def aggregate_summary(
    request: Request,
    since: str | None = Query(None),
    until: str | None = Query(None),
):
    """Combined issue/PR counts across all repos."""
    db = request.app.state.db
    repos = await db.get_all_repos()
    since_dt = parse_date_param(since)
    until_dt = parse_date_param(until, end_of_day=True)

    total_open_issues = 0
    total_closed_issues = 0
    total_open_prs = 0
    total_merged_prs = 0
    total_closed_prs = 0
    repo_summaries = []

    for r in repos:
        rid = r["id"]
        open_i = len(filter_active_issues(await get_cached_issues(db, rid, state="open"), since_dt, until_dt))
        closed_i = len(filter_active_issues(await get_cached_issues(db, rid, state="closed"), since_dt, until_dt))
        open_p = len(filter_active_prs(await get_cached_prs(db, rid, state="open"), since_dt, until_dt))
        merged_p = len(filter_active_prs(await get_cached_prs(db, rid, state="merged"), since_dt, until_dt))
        closed_p = len(filter_active_prs(await get_cached_prs(db, rid, state="closed"), since_dt, until_dt))

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
    since: str | None = Query(None),
    until: str | None = Query(None),
):
    """Cross-repo chart data (merged from all repos)."""
    since_dt = parse_date_param(since)
    until_dt = parse_date_param(until, end_of_day=True)

    if chart_type == "open-issues":
        issues = await _collect_all_issues(request, since_dt=since_dt, until_dt=until_dt)
        end = until_dt or datetime.now(tz=timezone.utc)
        start = since_dt or (end - timedelta(days=months * 30))
        return open_issue_counts_data(start, end, issues, bug_labels=["bug"])
    elif chart_type == "time-to-merge":
        prs = await _collect_all_prs(request, state="merged", since_dt=since_dt, until_dt=until_dt)
        return time_to_merge_data(prs)
    elif chart_type == "time-to-close":
        issues = await _collect_all_issues(request, state="closed", since_dt=since_dt, until_dt=until_dt)
        return time_to_close_issues_data(issues)
    elif chart_type == "time-to-response":
        open_issues = await _collect_all_issues(request, state="open", since_dt=since_dt, until_dt=until_dt,
                                                enrich_response=True)
        closed_issues = await _collect_all_issues(request, state="closed", since_dt=since_dt, until_dt=until_dt,
                                                  enrich_response=True)
        resp_since = since_dt or (datetime.now(tz=timezone.utc) - timedelta(days=months * 30))
        return time_to_first_response_data(open_issues, closed_issues, since=resp_since)
    elif chart_type == "label-frequency":
        issues = await _collect_all_issues(request, state="open", since_dt=since_dt, until_dt=until_dt)
        return label_frequency_data(issues)
    elif chart_type == "files-changed":
        prs = await _collect_all_prs(request, since_dt=since_dt, until_dt=until_dt)
        return files_changed_data(prs)
    elif chart_type == "lines-changed":
        prs = await _collect_all_prs(request, since_dt=since_dt, until_dt=until_dt)
        return lines_changed_data(prs)
    elif chart_type == "top-terms":
        issues = await _collect_all_issues(request, since_dt=since_dt, until_dt=until_dt)
        return top_terms_data(issues, min_count=min_count)
    elif chart_type == "top-files":
        prs = await _collect_all_prs(request, since_dt=since_dt, until_dt=until_dt)
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
    since: str | None = Query(None),
    until: str | None = Query(None),
):
    """Cross-repo report data."""
    db = request.app.state.db
    repos = await db.get_all_repos()
    since_dt = parse_date_param(since)
    until_dt = parse_date_param(until, end_of_day=True)
    now = until_dt or datetime.now(tz=timezone.utc)
    if since_dt:
        days = max(1, (now - since_dt).days)

    if report_type == "revisits":
        results = []
        for r in repos:
            issues = await get_cached_issues(db, r["id"], state="open")
            issues = filter_active_issues(issues, since_dt, until_dt)
            members = await get_cached_team_members(db, r["id"])
            enrich_team_response(issues, members)
            result = revisits_data(now, r["owner"], r["name"], issues, members,
                                   bug_label=bug_label, days=days, stale=stale,
                                   show_all=show_all)
            results.append(result)
        return {"repos": results}
    elif report_type == "pr-activity":
        results = []
        for r in repos:
            open_prs = filter_active_prs(await get_cached_prs(db, r["id"], state="open"), since_dt, until_dt)
            closed_prs = filter_active_prs(await get_cached_prs(db, r["id"], state="closed"), since_dt, until_dt)
            merged_prs = filter_active_prs(await get_cached_prs(db, r["id"], state="merged"), since_dt, until_dt)
            result = pr_activity_data(now, r["owner"], r["name"],
                                      open_prs, closed_prs + merged_prs,
                                      days=days, show_all=show_all)
            results.append(result)
        return {"repos": results}
    elif report_type == "closed-issues":
        results = []
        for r in repos:
            closed = await get_cached_issues(db, r["id"], state="closed")
            closed = filter_active_issues(closed, since_dt, until_dt)
            result = closed_issues_data(now, r["owner"], r["name"], closed, days=days)
            results.append(result)
        return {"repos": results}
    else:
        from fastapi import HTTPException
        raise HTTPException(400, f"Unknown report type: {report_type}")
