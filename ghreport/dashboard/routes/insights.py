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
from ..ai import cluster_issues, detect_anomalies, generate_digest, sub_cluster_issues
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

_SUBCLUSTER_THRESHOLD = 12
_MAX_SUBCLUSTER_DEPTH = 6


def _get_ai_client(request: Request):
    client = request.app.state.ai_client
    if client is None:
        raise HTTPException(503, "AI insights not available — Copilot SDK failed to initialize")
    return client


async def _get_repo_id_or_404(request: Request, owner: str, repo: str) -> int:
    repo_id = await request.app.state.db.get_repo_id(owner, repo)
    if not repo_id:
        raise HTTPException(404, f"Repository {owner}/{repo} not found")
    return repo_id


def _normalize_subclusters(
    subclusters: list[dict],
    parent_issues: list[int],
) -> list[dict]:
    """Sanitize LLM sub-cluster output to valid issue subsets."""
    parent_set = set(parent_issues)
    assigned: set[int] = set()
    cleaned: list[dict] = []

    for idx, sub in enumerate(subclusters):
        name = str(sub.get("name") or f"Subcluster {idx + 1}").strip()
        summary = str(sub.get("summary") or "").strip()
        raw_nums = sub.get("issues") or []
        nums: list[int] = []

        for n in raw_nums:
            if not isinstance(n, int):
                continue
            if n not in parent_set or n in assigned:
                continue
            nums.append(n)
            assigned.add(n)

        if nums:
            cleaned.append({"name": name, "issues": nums, "summary": summary})

    # Preserve any dropped parent issues in a catch-all node.
    missing = [n for n in parent_issues if n not in assigned]
    if missing:
        cleaned.append(
            {
                "name": "Other",
                "issues": missing,
                "summary": "Issues that did not fit a specific subcluster.",
            }
        )

    return cleaned


def _fallback_partition(parent_issues: list[int]) -> list[dict]:
    """Deterministically split a large group when LLM split is a no-op."""
    size = _SUBCLUSTER_THRESHOLD - 1
    parts: list[dict] = []
    for idx in range(0, len(parent_issues), size):
        chunk = parent_issues[idx:idx + size]
        if not chunk:
            continue
        part_no = (idx // size) + 1
        parts.append(
            {
                "name": f"Part {part_no}",
                "issues": chunk,
                "summary": "Fallback split for large cluster.",
            }
        )
    return parts


async def _subdivide_clusters_recursive(
    client,
    owner: str,
    repo: str,
    clusters: list[dict],
    issue_lookup: dict[int, dict],
    depth: int = 0,
) -> list[dict]:
    """Recursively sub-cluster groups while they remain large enough."""
    if depth >= _MAX_SUBCLUSTER_DEPTH:
        return clusters

    result: list[dict] = []
    for cluster in clusters:
        nums = [n for n in cluster.get("issues", []) if isinstance(n, int)]
        cluster["issues"] = nums

        if len(nums) < _SUBCLUSTER_THRESHOLD:
            result.append(cluster)
            continue

        issue_rows = [issue_lookup[n] for n in nums if n in issue_lookup]
        if len(issue_rows) < _SUBCLUSTER_THRESHOLD:
            result.append(cluster)
            continue

        subs = await sub_cluster_issues(
            client,
            owner,
            repo,
            cluster.get("name", "Cluster"),
            issue_rows,
        )
        cleaned = _normalize_subclusters(subs, nums)

        # Guard against no-op or degenerate splits.
        if len(cleaned) <= 1:
            # Force progress when model fails to split a large cluster.
            cleaned = _fallback_partition(nums)
            if len(cleaned) <= 1:
                result.append(cluster)
                continue
        largest = max(len(s["issues"]) for s in cleaned)
        if largest >= len(nums):
            cleaned = _fallback_partition(nums)
            largest = max(len(s["issues"]) for s in cleaned)
            if largest >= len(nums):
                result.append(cluster)
                continue

        cluster["subclusters"] = await _subdivide_clusters_recursive(
            client,
            owner,
            repo,
            cleaned,
            issue_lookup,
            depth + 1,
        )
        result.append(cluster)

    return result


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
    issues_closed = filter_active_issues(
        await get_cached_issues(db, repo_id, state="closed"), since_dt, until_dt)
    issues_all = issues_open + issues_closed
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
    resp_since = since_dt or (now - timedelta(days=180))
    ttr = time_to_first_response_data(issues_open, issues_closed, since=resp_since)

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
    client = _get_ai_client(request)
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)
    since_dt = parse_date_param(since)
    until_dt = parse_date_param(until, end_of_day=True)
    if since_dt:
        days = max(1, ((until_dt or datetime.now(tz=timezone.utc)) - since_dt).days)

    summary, revisits, pr_act, ttm, ttc, ttr = await _collect_metrics(
        db, repo_id, owner, repo, since_dt, until_dt, days)

    digest = await generate_digest(client, owner, repo, summary, revisits, pr_act, ttm, ttc, ttr)
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
    client = _get_ai_client(request)
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

    anomalies = await detect_anomalies(client, owner, repo, current, baseline)
    return {"anomalies": anomalies, "days": days}


# ---------------------------------------------------------------------------
# 3. Issue Clustering
# ---------------------------------------------------------------------------

@router.get("/clusters")
async def get_clusters(
    request: Request,
    owner: str,
    repo: str,
    force: bool = Query(False),
):
    """Cluster open issues by topic using AI analysis.

    Returns cached clusters when available. Only sends unclustered
    issues to the LLM. Use force=true to re-cluster everything.
    """
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    # Load all open issues with their cached cluster assignment
    cursor = await db.db.execute(
        "SELECT number, title, cluster, raw_json"
        " FROM issues WHERE repo_id = ? AND state = 'open'",
        (repo_id,),
    )
    rows = await cursor.fetchall()

    if not rows:
        return {
            "clusters": [], "total_issues": 0,
            "issue_titles": {}, "from_cache": True,
        }

    title_map: dict[int, str] = {}
    cached: dict[str, list[int]] = {}  # cluster_name -> [numbers]
    unclustered: list[dict] = []

    for row in rows:
        num = row["number"]
        title_map[num] = row["title"]
        labels = _extract_labels(row["raw_json"])
        issue_dict = {
            "number": num, "title": row["title"], "labels": labels,
        }

        if not force and row["cluster"]:
            cached.setdefault(row["cluster"], []).append(num)
        else:
            unclustered.append(issue_dict)

    # Build issue lookup for recursive sub-clustering
    issue_lookup: dict[int, dict] = {}
    for row in rows:
        issue_lookup[row["number"]] = {
            "number": row["number"],
            "title": row["title"],
            "labels": _extract_labels(row["raw_json"]),
        }

    # If everything is cached and we're not forcing, still recursively
    # subdivide large clusters so leaf groups stay below threshold.
    if not unclustered and not force:
        clusters = [
            {"name": name, "issues": nums, "summary": ""}
            for name, nums in sorted(cached.items())
        ]
        needs_subdivision = any(
            len(c.get("issues", [])) >= _SUBCLUSTER_THRESHOLD
            for c in clusters
        )
        if needs_subdivision:
            client = _get_ai_client(request)
            clusters = await _subdivide_clusters_recursive(
                client,
                owner,
                repo,
                clusters,
                issue_lookup,
            )
            return {
                "clusters": clusters,
                "total_issues": len(rows),
                "issue_titles": title_map,
                "from_cache": False,
            }
        return {
            "clusters": clusters,
            "total_issues": len(rows),
            "issue_titles": title_map,
            "from_cache": True,
        }

    # Need AI client for clustering
    client = _get_ai_client(request)

    if force:
        # Re-cluster all issues from scratch
        all_issues = [
            {"number": r["number"], "title": r["title"],
             "labels": _extract_labels(r["raw_json"])}
            for r in rows
        ]
        clusters = await cluster_issues(
            client, owner, repo, all_issues)
    else:
        # Cluster only new issues, providing existing cluster
        # names as context so the LLM can reuse them
        existing_names = list(cached.keys())
        clusters = await cluster_issues(
            client, owner, repo, unclustered,
            existing_clusters=existing_names)
        # Merge with cached clusters
        merged: dict[str, list[int]] = dict(cached)
        for c in clusters:
            name = c["name"]
            merged.setdefault(name, []).extend(c["issues"])
        clusters = [
            {"name": n, "issues": nums,
             "summary": next(
                 (c["summary"] for c in clusters
                  if c["name"] == n), "")}
            for n, nums in sorted(merged.items())
        ]

    # Recursively sub-cluster large groups
    clusters = await _subdivide_clusters_recursive(
        client,
        owner,
        repo,
        clusters,
        issue_lookup,
    )

    # Persist cluster assignments back to DB
    for c in clusters:
        for num in c["issues"]:
            await db.db.execute(
                "UPDATE issues SET cluster = ?"
                " WHERE repo_id = ? AND number = ?",
                (c["name"], repo_id, num),
            )
    await db.db.commit()

    return {
        "clusters": clusters,
        "total_issues": len(rows),
        "issue_titles": title_map,
        "from_cache": False,
    }


def _extract_labels(raw_json: str | None) -> list[str]:
    """Extract label names from raw issue JSON."""
    if not raw_json:
        return []
    try:
        raw = json.loads(raw_json)
        nodes = raw.get("labels", {}).get("nodes", [])
        return [n.get("name", "") for n in nodes
                if n.get("name")]
    except (json.JSONDecodeError, AttributeError):
        return []
