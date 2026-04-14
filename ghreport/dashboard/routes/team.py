"""Team member management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/team", tags=["team"])


class MemberRequest(BaseModel):
    login: str


# ---------------------------------------------------------------------------
# Common (cross-repo) team members
# ---------------------------------------------------------------------------

@router.get("/common")
async def list_common_members(request: Request):
    """List common team members shared across all repos."""
    db = request.app.state.db
    cursor = await db.db.execute("SELECT login FROM common_team_members ORDER BY login")
    rows = await cursor.fetchall()
    return {"members": [r["login"] for r in rows]}


@router.post("/common")
async def add_common_member(request: Request, body: MemberRequest):
    """Add a common team member."""
    db = request.app.state.db
    try:
        await db.db.execute(
            "INSERT INTO common_team_members (login) VALUES (?)", (body.login,)
        )
        await db.db.commit()
    except Exception:
        raise HTTPException(409, f"Member {body.login} already exists")
    return {"login": body.login}


@router.delete("/common/{login}")
async def remove_common_member(request: Request, login: str):
    """Remove a common team member."""
    db = request.app.state.db
    cursor = await db.db.execute(
        "DELETE FROM common_team_members WHERE login = ?", (login,)
    )
    await db.db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(404, f"Member {login} not found")
    return {"status": "deleted", "login": login}


# ---------------------------------------------------------------------------
# Per-repo supplemental team members
# ---------------------------------------------------------------------------

@router.get("/repos/{owner}/{repo}")
async def list_repo_members(request: Request, owner: str, repo: str):
    """List supplemental team members for a specific repo."""
    db = request.app.state.db
    repo_id = await db.get_repo_id(owner, repo)
    if not repo_id:
        raise HTTPException(404, f"Repository {owner}/{repo} not found")

    cursor = await db.db.execute(
        "SELECT login FROM team_members WHERE repo_id = ? ORDER BY login", (repo_id,)
    )
    rows = await cursor.fetchall()

    # Also return common members for display
    cursor2 = await db.db.execute("SELECT login FROM common_team_members ORDER BY login")
    common = await cursor2.fetchall()

    return {
        "repo_members": [r["login"] for r in rows],
        "common_members": [r["login"] for r in common],
    }


@router.post("/repos/{owner}/{repo}")
async def add_repo_member(request: Request, owner: str, repo: str, body: MemberRequest):
    """Add a supplemental team member for a repo."""
    db = request.app.state.db
    repo_id = await db.get_repo_id(owner, repo)
    if not repo_id:
        raise HTTPException(404, f"Repository {owner}/{repo} not found")
    try:
        await db.db.execute(
            "INSERT INTO team_members (repo_id, login) VALUES (?, ?)",
            (repo_id, body.login),
        )
        await db.db.commit()
    except Exception:
        raise HTTPException(409, f"Member {body.login} already exists for this repo")
    return {"login": body.login}


@router.delete("/repos/{owner}/{repo}/{login}")
async def remove_repo_member(request: Request, owner: str, repo: str, login: str):
    """Remove a supplemental team member from a repo."""
    db = request.app.state.db
    repo_id = await db.get_repo_id(owner, repo)
    if not repo_id:
        raise HTTPException(404, f"Repository {owner}/{repo} not found")
    cursor = await db.db.execute(
        "DELETE FROM team_members WHERE repo_id = ? AND login = ?",
        (repo_id, login),
    )
    await db.db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(404, f"Member {login} not found for this repo")
    return {"status": "deleted", "login": login}


# ---------------------------------------------------------------------------
# All unique members (for member selector dropdowns)
# ---------------------------------------------------------------------------

@router.get("/all")
async def list_all_members(request: Request):
    """List all unique team members (common + all per-repo)."""
    db = request.app.state.db
    cursor = await db.db.execute(
        "SELECT DISTINCT login FROM ("
        "  SELECT login FROM common_team_members"
        "  UNION"
        "  SELECT login FROM team_members"
        ") ORDER BY login"
    )
    rows = await cursor.fetchall()
    return {"members": [r["login"] for r in rows]}
