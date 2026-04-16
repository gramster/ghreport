"""Pull request listing routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

from ..cache import get_cached_prs

router = APIRouter(prefix="/api/repos/{owner}/{repo}/prs", tags=["prs"])


@router.get("")
async def list_prs(
    request: Request,
    owner: str,
    repo: str,
    state: str | None = Query(None, pattern="^(open|closed|merged)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Paginated PR listing with optional state filter."""
    db = request.app.state.db
    repo_id = await db.get_repo_id(owner, repo)
    if not repo_id:
        raise HTTPException(404, f"Repository {owner}/{repo} not found")

    prs = await get_cached_prs(db, repo_id, state=state)

    # Sort by created_at descending
    prs.sort(key=lambda p: p.created_at or datetime.min, reverse=True)

    total = len(prs)
    start = (page - 1) * per_page
    page_prs = prs[start : start + per_page]

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pull_requests": [
            {
                "number": p.number,
                "title": p.title,
                "state": "merged" if p.merged_at else ("closed" if p.closed_at else "open"),
                "created_by": p.created_by,
                "closed_by": p.closed_by,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "merged_at": p.merged_at.isoformat() if p.merged_at else None,
                "closed_at": p.closed_at.isoformat() if p.closed_at else None,
                "lines_changed": p.lines_changed,
                "files_changed": p.files_changed,
                "reviewers": p.reviewers or [],
                "collaborators": p.collaborators or [],
            }
            for p in page_prs
        ],
    }
