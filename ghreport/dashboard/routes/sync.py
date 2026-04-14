"""Sync control routes — trigger and monitor data synchronization."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request

from ..cache import get_sync_status, sync_repo

router = APIRouter(tags=["sync"])


@router.post("/api/repos/{owner}/{repo}/sync")
async def trigger_repo_sync(request: Request, owner: str, repo: str):
    """Trigger manual sync for one repository."""
    db = request.app.state.db
    settings = request.app.state.settings
    repo_id = await db.get_repo_id(owner, repo)
    if not repo_id:
        raise HTTPException(404, f"Repository {owner}/{repo} not found")

    # Find repo config for team info
    team = None
    for rc in settings.repos:
        if rc.owner == owner and rc.name == repo:
            team = rc.team
            break

    result = await sync_repo(db, owner, repo, settings.github_token, team=team)
    return {"status": "completed", **result}


@router.post("/api/sync")
async def trigger_full_sync(request: Request):
    """Trigger sync for all configured repos."""
    db = request.app.state.db
    settings = request.app.state.settings
    results = []
    for rc in settings.repos:
        result = await sync_repo(db, rc.owner, rc.name,
                                 settings.github_token, team=rc.team)
        results.append({"owner": rc.owner, "name": rc.name, **result})
    return {"status": "completed", "repos": results}


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
