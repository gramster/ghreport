"""Repository management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/repos", tags=["repos"])


@router.get("")
async def list_repos(request: Request):
    """List all configured repositories with sync status."""
    db = request.app.state.db
    repos = await db.get_all_repos()
    results = []
    for r in repos:
        # Get issue/PR counts
        ic = await db.db.execute(
            "SELECT state, COUNT(*) as cnt FROM issues WHERE repo_id = ? GROUP BY state",
            (r["id"],),
        )
        issue_counts = {row["state"]: row["cnt"] for row in await ic.fetchall()}

        pc = await db.db.execute(
            "SELECT state, COUNT(*) as cnt FROM pull_requests WHERE repo_id = ? GROUP BY state",
            (r["id"],),
        )
        pr_counts = {row["state"]: row["cnt"] for row in await pc.fetchall()}

        results.append({
            "owner": r["owner"],
            "name": r["name"],
            "last_synced_at": r["last_synced_at"],
            "issues": issue_counts,
            "pull_requests": pr_counts,
        })
    return results


@router.get("/{owner}/{repo}")
async def get_repo(request: Request, owner: str, repo: str):
    """Get summary for a single repository."""
    db = request.app.state.db
    repo_id = await db.get_repo_id(owner, repo)
    if not repo_id:
        raise HTTPException(404, f"Repository {owner}/{repo} not found")

    ic = await db.db.execute(
        "SELECT state, COUNT(*) as cnt FROM issues WHERE repo_id = ? GROUP BY state",
        (repo_id,),
    )
    issue_counts = {row["state"]: row["cnt"] for row in await ic.fetchall()}

    pc = await db.db.execute(
        "SELECT state, COUNT(*) as cnt FROM pull_requests WHERE repo_id = ? GROUP BY state",
        (repo_id,),
    )
    pr_counts = {row["state"]: row["cnt"] for row in await pc.fetchall()}

    repo_row = await (await db.db.execute(
        "SELECT * FROM repos WHERE id = ?", (repo_id,)
    )).fetchone()

    return {
        "owner": owner,
        "name": repo,
        "last_synced_at": repo_row["last_synced_at"] if repo_row else None,
        "issues": issue_counts,
        "pull_requests": pr_counts,
    }
