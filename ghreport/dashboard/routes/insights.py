"""AI insights routes — digest, anomaly detection, issue clustering."""

from __future__ import annotations

import json
import logging
import statistics
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from ...core.analyzer import (
    closed_issues_data,
    open_issue_counts_data,
    pr_activity_data,
    revisits_data,
    time_to_close_issues_data,
    time_to_first_response_data,
    time_to_merge_data,
)
from ..ai import cluster_issues, detect_anomalies, generate_digest, generate_repo_activity_summary, sub_cluster_issues
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
_CLUSTER_TREE_CONFIG_KEY = "issue_cluster_tree"


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


def _collect_issue_numbers(clusters: list[dict]) -> set[int]:
    """Collect issue numbers from a cluster tree recursively."""
    numbers: set[int] = set()
    for cluster in clusters:
        for n in cluster.get("issues", []):
            if isinstance(n, int):
                numbers.add(n)
        subs = cluster.get("subclusters") or []
        if subs:
            numbers.update(_collect_issue_numbers(subs))
    return numbers


def _filter_cluster_tree(clusters: list[dict], valid_issues: set[int]) -> list[dict]:
    """Drop stale issue refs while preserving nested structure."""
    filtered: list[dict] = []
    for cluster in clusters:
        nums = [n for n in cluster.get("issues", []) if isinstance(n, int) and n in valid_issues]
        subs = _filter_cluster_tree(cluster.get("subclusters") or [], valid_issues)
        if not nums and not subs:
            continue
        filtered.append(
            {
                "name": str(cluster.get("name") or "Cluster"),
                "issues": nums,
                "summary": str(cluster.get("summary") or ""),
                **({"subclusters": subs} if subs else {}),
            }
        )
    return filtered


async def _load_repo_config(db, repo_id: int) -> dict:
    """Load repos.config_json as a dict (empty dict if missing/invalid)."""
    row = await (await db.db.execute(
        "SELECT config_json FROM repos WHERE id = ?", (repo_id,)
    )).fetchone()
    if not row or not row["config_json"]:
        return {}
    try:
        cfg = json.loads(row["config_json"])
        return cfg if isinstance(cfg, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


async def _load_cluster_tree_from_repo_config(db, repo_id: int) -> list[dict] | None:
    """Load persisted cluster tree from repos.config_json."""
    cfg = await _load_repo_config(db, repo_id)
    tree = cfg.get(_CLUSTER_TREE_CONFIG_KEY)
    return tree if isinstance(tree, list) else None


async def _save_cluster_tree_to_repo_config(
    db, repo_id: int, clusters: list[dict], *, record_full_recluster: bool = False
):
    """Persist full cluster tree in repos.config_json.

    If record_full_recluster=True, also stamps last_full_cluster_at
    with the current UTC time so callers can detect stale hierarchies.
    """
    cfg = await _load_repo_config(db, repo_id)
    cfg[_CLUSTER_TREE_CONFIG_KEY] = clusters
    if record_full_recluster:
        cfg["last_full_cluster_at"] = datetime.now(timezone.utc).isoformat()
    await db.db.execute(
        "UPDATE repos SET config_json = ? WHERE id = ?",
        (json.dumps(cfg), repo_id),
    )


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
            try:
                n = int(n)
            except (TypeError, ValueError):
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


def _has_fallback_subclusters(clusters: list[dict]) -> bool:
    """Return True if any cluster contains fallback partition nodes (Part N)."""
    import re
    _fallback_re = re.compile(r"^Part \d+$")
    for cluster in clusters:
        for sub in cluster.get("subclusters", []):
            if _fallback_re.match(sub.get("name", "")):
                return True
    return False


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
            logger.warning(
                "sub_cluster_issues returned degenerate split for %r (%d issues); "
                "raw subs=%r",
                cluster.get("name"),
                len(nums),
                subs[:2] if subs else subs,
            )
            cleaned = _fallback_partition(nums)
            if len(cleaned) <= 1:
                result.append(cluster)
                continue
        largest = max(len(s["issues"]) for s in cleaned)
        if largest >= len(nums):
            logger.warning(
                "sub_cluster_issues made no progress for %r (%d issues); falling back",
                cluster.get("name"),
                len(nums),
            )
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
    # "closed" for pr_activity_data means any non-open PR — must include
    # merged PRs (state="merged") as well as unmerged closes (state="closed").
    prs_closed = filter_active_prs(
        await get_cached_prs(db, repo_id, state="closed") +
        await get_cached_prs(db, repo_id, state="merged"),
        since_dt, until_dt)
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
    ensure_subclusters: bool = Query(False),
):
    """Cluster open issues by topic using AI analysis.

    Returns cached clusters when available. Only sends unclustered
    issues to the LLM. Use force=true to re-cluster everything.

    Auto-reclustering policy:
    - If the last full recluster was < 7 days ago, only newly-unclustered
      issues are categorised into the existing hierarchy.
    - If it was >= 7 days ago (or has never been run), a full recluster
      is performed automatically, rebuilding the hierarchy from scratch.
    - force=true always triggers a full recluster regardless of age.
    """
    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    # Determine whether we need a full recluster based on age of last run.
    cfg = await _load_repo_config(db, repo_id)
    last_full_str: str | None = cfg.get("last_full_cluster_at")
    last_full: datetime | None = None
    if last_full_str:
        try:
            last_full = datetime.fromisoformat(last_full_str)
            if last_full.tzinfo is None:
                last_full = last_full.replace(tzinfo=timezone.utc)
        except ValueError:
            last_full = None

    _RECLUSTER_INTERVAL = timedelta(days=7)
    now_utc = datetime.now(timezone.utc)
    needs_full = force or last_full is None or (now_utc - last_full) >= _RECLUSTER_INTERVAL

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
            "last_full_cluster_at": last_full_str,
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

        # When doing incremental, treat already-clustered issues as cached.
        if not needs_full and row["cluster"]:
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

    # If everything is cached and a full recluster is not needed, return from
    # cache without calling the LLM.
    if not unclustered and not needs_full:
        # Prefer persisted nested tree when available.
        persisted_tree = await _load_cluster_tree_from_repo_config(db, repo_id)
        valid_issues = set(title_map.keys())
        if persisted_tree and not _has_fallback_subclusters(persisted_tree):
            filtered_tree = _filter_cluster_tree(persisted_tree, valid_issues)
            if _collect_issue_numbers(filtered_tree) == valid_issues:
                return {
                    "clusters": filtered_tree,
                    "total_issues": len(rows),
                    "issue_titles": title_map,
                    "from_cache": True,
                    "last_full_cluster_at": last_full_str,
                }

        # Legacy cache compatibility: if we only have top-level issue tags,
        # optionally bootstrap/persist nested subclusters from those tags.
        if ensure_subclusters and cached:
            client = _get_ai_client(request)
            top_clusters = [
                {"name": name, "issues": nums, "summary": ""}
                for name, nums in sorted(cached.items())
            ]
            bootstrapped_tree = await _subdivide_clusters_recursive(
                client,
                owner,
                repo,
                top_clusters,
                issue_lookup,
            )
            await _save_cluster_tree_to_repo_config(db, repo_id, bootstrapped_tree)
            await db.db.commit()
            return {
                "clusters": bootstrapped_tree,
                "total_issues": len(rows),
                "issue_titles": title_map,
                "from_cache": False,
                "last_full_cluster_at": last_full_str,
            }

        clusters = [
            {"name": name, "issues": nums, "summary": ""}
            for name, nums in sorted(cached.items())
        ]
        return {
            "clusters": clusters,
            "total_issues": len(rows),
            "issue_titles": title_map,
            "from_cache": True,
            "last_full_cluster_at": last_full_str,
        }

    # Need AI client for clustering
    client = _get_ai_client(request)

    if needs_full:
        # Re-cluster all issues from scratch (forced or stale hierarchy).
        all_issues = [
            {"number": r["number"], "title": r["title"],
             "labels": _extract_labels(r["raw_json"])}
            for r in rows
        ]
        clusters = await cluster_issues(
            client, owner, repo, all_issues)
    else:
        # Cluster only new issues, providing existing cluster
        # names as context so the LLM can reuse them.
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

    # Persist full nested cluster tree; stamp timestamp if this was a full run.
    await _save_cluster_tree_to_repo_config(
        db, repo_id, clusters, record_full_recluster=needs_full
    )
    if needs_full:
        last_full_str = datetime.now(timezone.utc).isoformat()

    await db.db.commit()

    return {
        "clusters": clusters,
        "total_issues": len(rows),
        "issue_titles": title_map,
        "from_cache": False,
        "last_full_cluster_at": last_full_str,
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


def _cluster_tree_to_markdown(
    clusters: list[dict],
    issue_titles: dict[int, str],
    owner: str,
    repo: str,
    depth: int = 0,
) -> list[str]:
    lines: list[str] = []
    for cluster in clusters:
        indent = "  " * depth
        name = str(cluster.get("name") or "Cluster")
        issues = [n for n in cluster.get("issues", []) if isinstance(n, int)]
        summary = str(cluster.get("summary") or "").strip()

        lines.append(f"{indent}- **{name}** ({len(issues)} issues)")
        if summary:
            lines.append(f"{indent}  - {summary}")

        subclusters = cluster.get("subclusters") or []
        if subclusters:
            lines.extend(
                _cluster_tree_to_markdown(
                    subclusters,
                    issue_titles,
                    owner,
                    repo,
                    depth + 1,
                )
            )
            continue

        for num in issues:
            title = issue_titles.get(num, "")
            issue_url = f"https://github.com/{owner}/{repo}/issues/{num}"
            title_part = f" - {title}" if title else ""
            lines.append(f"{indent}  - [#{num}]({issue_url}){title_part}")

    return lines


@router.get("/clusters/markdown")
async def export_clusters_markdown(
    request: Request,
    owner: str,
    repo: str,
    force: bool = Query(False),
):
    """Export issue clusters as a downloadable Markdown file."""
    payload = await get_clusters(
        request,
        owner,
        repo,
        force,
        ensure_subclusters=True,
    )
    clusters = payload.get("clusters", [])
    issue_titles = payload.get("issue_titles", {})
    total_issues = payload.get("total_issues", 0)

    lines = [
        f"# Issue Clusters: {owner}/{repo}",
        "",
        f"- Generated: {datetime.now(tz=timezone.utc).isoformat()}",
        f"- Total open issues clustered: {total_issues}",
        "",
    ]

    if clusters:
        lines.extend(
            _cluster_tree_to_markdown(
                clusters,
                issue_titles,
                owner,
                repo,
            )
        )
    else:
        lines.append("No open issues to cluster.")

    content = "\n".join(lines).strip() + "\n"
    filename = f"{owner}-{repo}-issue-clusters.md"

    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/activity-summary")
async def get_activity_summary(
    request: Request,
    owner: str,
    repo: str,
):
    """Return a short AI-generated plain-text summary of recent activity.

    Tries windows of 14 → 30 → 90 days so there is always something to
    summarise as long as any data is synced.
    """
    client = request.app.state.ai_client

    db = request.app.state.db
    repo_id = await _get_repo_id_or_404(request, owner, repo)

    issues = await get_cached_issues(db, repo_id)
    prs = await get_cached_prs(db, repo_id)

    def _n(dt: datetime | None) -> datetime | None:
        """Normalise to naive UTC so tz-aware and naive datetimes compare cleanly."""
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    def _filter(days: int):
        since_naive = (datetime.now(tz=timezone.utc) - timedelta(days=days)).replace(tzinfo=None)
        opened = [i for i in issues if _n(i.created_at) and _n(i.created_at) >= since_naive]
        closed = [i for i in issues if _n(i.closed_at) and _n(i.closed_at) >= since_naive]
        pr_opened = [p for p in prs if _n(p.created_at) and _n(p.created_at) >= since_naive]
        pr_merged = [p for p in prs if _n(p.merged_at) and _n(p.merged_at) >= since_naive]
        return opened, closed, pr_opened, pr_merged

    # Try progressively wider windows until we find activity.
    period_days = 14
    recent_opened, recent_closed, recent_pr_opened, recent_pr_merged = _filter(period_days)
    for fallback_days in (30, 90):
        if recent_opened or recent_closed or recent_pr_opened or recent_pr_merged:
            break
        period_days = fallback_days
        recent_opened, recent_closed, recent_pr_opened, recent_pr_merged = _filter(period_days)

    logger.warning(
        "activity-summary %s/%s: window=%dd, %d opened, %d closed, "
        "%d pr_opened, %d pr_merged (ai_client=%s)",
        owner, repo, period_days,
        len(recent_opened), len(recent_closed),
        len(recent_pr_opened), len(recent_pr_merged), client is not None,
    )

    total_activity = (
        len(recent_opened) + len(recent_closed)
        + len(recent_pr_opened) + len(recent_pr_merged)
    )
    if client is None or total_activity == 0:
        return {"summary": None}

    data = {
        "period_days": period_days,
        "issues_opened": len(recent_opened),
        "issues_opened_titles": [i.title for i in recent_opened[:10]],
        "issues_closed": len(recent_closed),
        "prs_opened": len(recent_pr_opened),
        "prs_opened_titles": [p.title for p in recent_pr_opened[:10]],
        "prs_merged": len(recent_pr_merged),
        "open_issues_total": sum(1 for i in issues if not i.closed_at),
    }

    summary = await generate_repo_activity_summary(client, owner, repo, data)
    return {"summary": summary or None, "period_days": period_days}
