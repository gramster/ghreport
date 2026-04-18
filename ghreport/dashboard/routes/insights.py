"""AI insights routes — digest, anomaly detection, issue clustering."""

from __future__ import annotations

import json
import logging
import statistics
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from ...core.analyzer import (
    closed_issues_data,
    open_issue_counts_data,
    pr_activity_data,
    revisits_data,
    time_to_close_issues_data,
    time_to_first_response_data,
    time_to_merge_data,
)
from ..ai import cluster_issues, detect_anomalies, generate_digest
from ..cache import (
    enrich_team_response,
    filter_active_issues,
    filter_active_prs,
    get_cached_issues,
    get_cached_prs,
    get_cached_team_members,
    parse_date_param,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/repos/{owner}/{repo}/insights", tags=["insights"])


def _get_token(request: Request) -> str:
    token = request.app.state.settings.github_token
    if not token:
        raise HTTPException(503, "No GitHub token configured — required for AI insights")
    return token


async def _get_repo_id_or_404(request: Request, owner: str, repo: str) -> int:
    repo_id = await request.app.state.db.get_repo_id(owner, repo)
    if not repo_id:
        raise HTTPException(404, f"Repository {owner}/{repo} not found")
    return repo_id


# ---------------------------------------------------------------------------
# Collect metrics helpers
# ---------------------------------------------------------------------------

async def _collect_summary(db, repo_id, since_dt, until_dt) -> dict:
    """Gather basic issue/PR counts."""
    open_i = len(filter_active_issues(
        await get_cached_issues(db, repo_id, state="open"), since_dt, until_dt))
    closed_i = len(filter_active_issues(
        await get_cached_issues(db, repo_id, state="closed"), since_dt, until_dt))
    open_p = len(filter_active_prs(
        await get_cached_prs(db, repo_id, state="open"), since_dt, until_dt))
    merged_p = len(filter_active_prs(
        await get_cached_prs(db, repo_id, state="merged"), since_dt, until_dt))
    closed_p = len(filter_active_prs(
        await get_cached_prs(db, repo_id, state="closed"), since_dt, until_dt))
    return {
        "open_issues": open_i,
        "closed_issues": closed_i,
        "open_prs": open_p,
        "merged_prs": merged_p,
        "closed_prs": closed_p,
    }


async def _collect_metrics(db, repo_id, owner, repo, since_dt, until_dt, days):
    """Collect all metrics needed for digest and anomaly endpoints."""
    now = until_dt or datetime.now(tz=timezone.utc)

    issues_open = filter_active_issues(
        await get_cached_issues(db, repo_id, state="open"), since_dt, until_dt)
    issues_all = filter_active_issues(
        await get_cached_issues(db, repo_id), since_dt, until_dt)
    prs_all = filter_active_prs(
        await get_cached_prs(db, repo_id), since_dt, until_dt)
    prs_open = filter_active_prs(
        await get_cached_prs(db, repo_id, state="open"), since_dt, until_dt)
    prs_closed = filter_active_prs(
        await get_cached_prs(db, repo_id, state="closed"), since_dt, until_dt)
    members = await get_cached_team_members(db, repo_id)
    enrich_team_response(issues_open, members)

    summary = await _collect_summary(db, repo_id, since_dt, until_dt)
    revisits = revisits_data(now, owner, repo, issues_open, members,
                             days=days, stale=30)
    pr_act = pr_activity_data(now, owner, repo, prs_open, prs_closed, days=days)
    ttm = time_to_merge_data(prs_all)
    ttc = time_to_close_issues_data(issues_all)
    ttr = time_to_first_response_data(issues_all, since_dt)

    return summary, revisits, pr_act, ttm, ttc, ttr


# ---------------------------------------------------------------------------
# 1. Activity Digest
# ---------------------------------------------------------------------------

@router.get("/digest")
async def get_digest(
    request: Request,
    owner: str,
    repo: str,
    days: int = Query(14, ge=1),
    since: str | None = Query(None),
    until: str | None = Query(None),
):
    """AI-generated narrative summary of repository activity."""
    token = _get_token(request)
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)
    since_dt = parse_date_param(since)
    until_dt = parse_date_param(until, end_of_day=True)
    if since_dt:
        days = max(1, ((until_dt or datetime.now(tz=timezone.utc)) - since_dt).days)

    summary, revisits, pr_act, ttm, ttc, ttr = await _collect_metrics(
        db, repo_id, owner, repo, since_dt, until_dt, days)

    digest = await generate_digest(token, owner, repo, summary, revisits, pr_act, ttm, ttc, ttr)
    return {"digest": digest, "days": days}


# ---------------------------------------------------------------------------
# 2. Anomaly Detection
# ---------------------------------------------------------------------------

def _period_stats(items: list, key_fn) -> dict:
    """Compute basic stats for a list of numeric values."""
    vals = [key_fn(i) for i in items if key_fn(i) is not None]
    if not vals:
        return {"count": 0}
    return {
        "count": len(vals),
        "mean": round(statistics.mean(vals), 1),
        "median": round(statistics.median(vals), 1),
    }


@router.get("/anomalies")
async def get_anomalies(
    request: Request,
    owner: str,
    repo: str,
    days: int = Query(14, ge=1),
    since: str | None = Query(None),
    until: str | None = Query(None),
):
    """Detect anomalies by comparing recent period vs historical baseline."""
    token = _get_token(request)
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)
    since_dt = parse_date_param(since)
    until_dt = parse_date_param(until, end_of_day=True)
    now = until_dt or datetime.now(tz=timezone.utc)
    if since_dt:
        days = max(1, (now - since_dt).days)

    # Current period
    current_since = since_dt or (now - timedelta(days=days))
    summary_current, _, pr_act_current, ttm_current, ttc_current, ttr_current = \
        await _collect_metrics(db, repo_id, owner, repo, current_since, until_dt, days)

    # Historical baseline: 3x the window right before the current period
    baseline_end = current_since
    baseline_start = baseline_end - timedelta(days=days * 3)
    summary_baseline, _, pr_act_baseline, ttm_baseline, ttc_baseline, ttr_baseline = \
        await _collect_metrics(db, repo_id, owner, repo, baseline_start, baseline_end, days * 3)

    def _flatten_monthly(monthly_data: dict) -> list[float]:
        vals = []
        for vs in monthly_data.get("months", {}).values():
            vals.extend(vs)
        return vals

    current = {
        "period_days": days,
        "summary": summary_current,
        "pr_activity": {
            "newly_opened": len(pr_act_current.get("newly_opened", [])),
            "newly_merged": len(pr_act_current.get("newly_merged", [])),
            "newly_closed": len(pr_act_current.get("newly_closed", [])),
            "stale_open": len(pr_act_current.get("stale_open", [])),
        },
        "merge_time_days": _period_stats(
            _flatten_monthly(ttm_current), lambda x: x),
        "close_time_days": _period_stats(
            _flatten_monthly(ttc_current), lambda x: x),
        "response_time_days": _period_stats(
            _flatten_monthly(ttr_current), lambda x: x),
    }

    baseline = {
        "period_days": days * 3,
        "summary": summary_baseline,
        "pr_activity": {
            "newly_opened": len(pr_act_baseline.get("newly_opened", [])),
            "newly_merged": len(pr_act_baseline.get("newly_merged", [])),
            "newly_closed": len(pr_act_baseline.get("newly_closed", [])),
            "stale_open": len(pr_act_baseline.get("stale_open", [])),
        },
        "merge_time_days": _period_stats(
            _flatten_monthly(ttm_baseline), lambda x: x),
        "close_time_days": _period_stats(
            _flatten_monthly(ttc_baseline), lambda x: x),
        "response_time_days": _period_stats(
            _flatten_monthly(ttr_baseline), lambda x: x),
    }

    anomalies = await detect_anomalies(token, owner, repo, current, baseline)
    return {"anomalies": anomalies, "days": days}


# ---------------------------------------------------------------------------
# 3. Issue Clustering
# ---------------------------------------------------------------------------

@router.get("/clusters")
async def get_clusters(
    request: Request,
    owner: str,
    repo: str,
):
    """Cluster open issues by topic using AI analysis."""
    token = _get_token(request)
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    # Get open issues with labels from raw_json
    cursor = await db.db.execute(
        "SELECT number, title, raw_json FROM issues WHERE repo_id = ? AND state = 'open'",
        (repo_id,),
    )
    rows = await cursor.fetchall()

    issues_for_clustering = []
    for row in rows:
        labels = []
        if row["raw_json"]:
            try:
                raw = json.loads(row["raw_json"])
                label_nodes = raw.get("labels", {}).get("nodes", [])
                labels = [n.get("name", "") for n in label_nodes if n.get("name")]
            except (json.JSONDecodeError, AttributeError):
                pass
        issues_for_clustering.append({
            "number": row["number"],
            "title": row["title"],
            "labels": labels,
        })

    if not issues_for_clustering:
        return {"clusters": [], "total_issues": 0}

    clusters = await cluster_issues(token, owner, repo, issues_for_clustering)
    return {"clusters": clusters, "total_issues": len(issues_for_clustering)}
