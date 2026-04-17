"""Sync control routes — trigger and monitor data synchronization."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from ..cache import get_sync_status, parse_date_param

router = APIRouter(tags=["sync"])


@router.get("/api/sync/activity")
async def get_sync_activity(request: Request):
    """Return current sync activity and recent errors."""
    scheduler = request.app.state.scheduler
    return {
        "syncing": sorted(scheduler.active_syncs),
        "retries": scheduler.active_retries,
        "rate_limited_until": scheduler.rate_limited_until,
        "errors": scheduler.recent_errors,
    }


@router.delete("/api/sync/errors")
async def clear_sync_errors(request: Request):
    """Dismiss all recent sync errors."""
    scheduler = request.app.state.scheduler
    scheduler.clear_errors()
    return {"status": "cleared"}


@router.post("/api/repos/{owner}/{repo}/sync")
async def trigger_repo_sync(request: Request, owner: str, repo: str):
    """Trigger manual sync for one repository."""
    db = request.app.state.db
    scheduler = request.app.state.scheduler
    repo_id = await db.get_repo_id(owner, repo)
    if not repo_id:
        raise HTTPException(404, f"Repository {owner}/{repo} not found")

    scheduler.queue_sync(owner, repo, force=True)
    return {"status": "queued"}


@router.post("/api/sync")
async def trigger_full_sync(request: Request):
    """Trigger sync for all repos."""
    scheduler = request.app.state.scheduler
    db = request.app.state.db
    repos = await db.get_all_repos()
    for r in repos:
        scheduler.queue_sync(r["owner"], r["name"])
    return {"status": "queued"}


@router.get("/api/repos/{owner}/{repo}/sync/status")
async def get_repo_sync_status(request: Request, owner: str, repo: str):
    """Get last sync info for a repository."""
    db = request.app.state.db
    repo_id = await db.get_repo_id(owner, repo)
    if not repo_id:
        raise HTTPException(404, f"Repository {owner}/{repo} not found")

    status = await get_sync_status(db, repo_id)
    if not status:
        return {"status": "never_synced"}
    return status


@router.post("/api/coverage/check")
async def check_date_coverage(
    request: Request,
    since: str | None = Query(None),
):
    """Check if cached data covers the requested date range.

    If any repo's data starts later than the requested *since*, trigger a
    background backfill for those repos and return ``backfilling: true``.
    """
    if not since:
        return {"covered": True, "backfilling": False}

    since_dt = parse_date_param(since)
    if not since_dt:
        return {"covered": True, "backfilling": False}

    db = request.app.state.db
    settings = request.app.state.settings
    scheduler = request.app.state.scheduler
    repos = await db.get_all_repos()

    gaps: list[dict] = []
    for r in repos:
        owner, name = r["owner"], r["name"]

        # If a backfill is currently running, report it
        if scheduler.is_backfilling(owner, name):
            gaps.append({"owner": owner, "name": name, "reason": "backfilling"})
            continue

        data_since = await db.get_data_since(r["id"])
        if not data_since:
            # Never synced — the initial sync will cover it
            if not r["last_synced_at"]:
                gaps.append({"owner": owner, "name": name, "reason": "never_synced"})
            continue
        data_since_dt = datetime.fromisoformat(data_since)
        if data_since_dt.tzinfo is None:
            data_since_dt = data_since_dt.replace(tzinfo=timezone.utc)
        if since_dt < data_since_dt:
            gaps.append({
                "owner": owner, "name": name,
                "data_since": data_since,
                "requested_since": since,
            })
            # Trigger backfill in background
            asyncio.create_task(
                scheduler.backfill(r["owner"], r["name"], since_dt)
            )

    return {
        "covered": len(gaps) == 0,
        "backfilling": len(gaps) > 0,
        "gaps": gaps,
    }
