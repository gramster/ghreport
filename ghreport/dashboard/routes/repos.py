"""Repository management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/repos", tags=["repos"])

_DATE_RANGE_THRESHOLD = 1000


async def _get_date_ranges(db, repo_id: int, issue_counts: dict, pr_counts: dict) -> dict:
    """Return min/max created_at for categories at or near the GitHub search cap."""
    ranges = {}
    for state, cnt in issue_counts.items():
        if cnt >= _DATE_RANGE_THRESHOLD:
            row = await (await db.db.execute(
                "SELECT MIN(created_at) as earliest, MAX(created_at) as latest "
                "FROM issues WHERE repo_id = ? AND state = ?", (repo_id, state)
            )).fetchone()
            if row:
                ranges[f"issues_{state}"] = {"earliest": row["earliest"], "latest": row["latest"]}
    for state, cnt in pr_counts.items():
        if cnt >= _DATE_RANGE_THRESHOLD:
            row = await (await db.db.execute(
                "SELECT MIN(created_at) as earliest, MAX(created_at) as latest "
                "FROM pull_requests WHERE repo_id = ? AND state = ?", (repo_id, state)
            )).fetchone()
            if row:
                ranges[f"prs_{state}"] = {"earliest": row["earliest"], "latest": row["latest"]}
    return ranges


class AddRepoRequest(BaseModel):
    owner: str
    repo: str


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

        # Add date ranges when counts are high (GitHub search caps at 1000)
        date_ranges = await _get_date_ranges(db, r["id"], issue_counts, pr_counts)

        results.append({
            "owner": r["owner"],
            "name": r["name"],
            "last_synced_at": r["last_synced_at"],
            "issues": issue_counts,
            "pull_requests": pr_counts,
            "date_ranges": date_ranges,
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

    date_ranges = await _get_date_ranges(db, repo_id, issue_counts, pr_counts)

    return {
        "owner": owner,
        "name": repo,
        "last_synced_at": repo_row["last_synced_at"] if repo_row else None,
        "issues": issue_counts,
        "pull_requests": pr_counts,
        "date_ranges": date_ranges,
    }


@router.post("")
async def add_repo(request: Request, body: AddRepoRequest):
    """Add a new repository to track."""
    db = request.app.state.db
    existing = await db.get_repo_id(body.owner, body.repo)
    if existing:
        raise HTTPException(409, f"Repository {body.owner}/{body.repo} already exists")
    repo_id = await db.ensure_repo(body.owner, body.repo)
    return {"owner": body.owner, "name": body.repo, "id": repo_id}


@router.delete("/{owner}/{repo}")
async def remove_repo(request: Request, owner: str, repo: str):
    """Remove a repository and all its cached data."""
    db = request.app.state.db
    repo_id = await db.get_repo_id(owner, repo)
    if not repo_id:
        raise HTTPException(404, f"Repository {owner}/{repo} not found")
    await db.remove_repo(repo_id)
    return {"status": "deleted", "owner": owner, "name": repo}
