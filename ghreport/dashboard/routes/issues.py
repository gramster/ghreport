"""Issue listing routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

from ..cache import get_cached_issues

router = APIRouter(prefix="/api/repos/{owner}/{repo}/issues", tags=["issues"])


@router.get("")
async def list_issues(
    request: Request,
    owner: str,
    repo: str,
    state: str | None = Query(None, pattern="^(open|closed)$"),
    label: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Paginated issue listing with optional filters."""
    db = request.app.state.db
    repo_id = await db.get_repo_id(owner, repo)
    if not repo_id:
        raise HTTPException(404, f"Repository {owner}/{repo} not found")

    issues = await get_cached_issues(db, repo_id, state=state)

    # Filter by label if requested
    if label:
        from ...core.parser import get_active_labels
        now = datetime.now()
        issues = [i for i in issues if label in get_active_labels(i.events, at=now)]

    # Sort by created_at descending
    issues.sort(key=lambda i: i.created_at or datetime.min, reverse=True)

    total = len(issues)
    start = (page - 1) * per_page
    page_issues = issues[start : start + per_page]

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "issues": [
            {
                "number": i.number,
                "title": i.title,
                "state": "closed" if i.closed_at else "open",
                "created_by": i.created_by,
                "closed_by": i.closed_by,
                "created_at": i.created_at.isoformat() if i.created_at else None,
                "closed_at": i.closed_at.isoformat() if i.closed_at else None,
                "first_team_response_at": i.first_team_response_at.isoformat() if i.first_team_response_at else None,
                "last_team_response_at": i.last_team_response_at.isoformat() if i.last_team_response_at else None,
                "event_count": len(i.events),
            }
            for i in page_issues
        ],
    }
