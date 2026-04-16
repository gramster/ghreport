"""Per-member report routes — issues commented on, PRs created by a member."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from ..cache import get_cached_issues, get_cached_prs

router = APIRouter(prefix="/api/members/{login}", tags=["members"])


@router.get("/issues")
async def member_issues(
    request: Request,
    login: str,
    owner: str | None = Query(None),
    repo: str | None = Query(None),
    since: str | None = Query(None, description="ISO date, e.g. 2025-01-01"),
    until: str | None = Query(None, description="ISO date, e.g. 2025-12-31"),
    state: str | None = Query(None),
):
    """Issues where the member commented or is the author."""
    db = request.app.state.db
    repos = await _get_repos(db, owner, repo)

    since_dt = _parse_date(since) if since else None
    until_dt = _parse_date(until) if until else None

    results = []
    for r in repos:
        issues = await get_cached_issues(db, r["id"], state=state)
        for issue in issues:
            # Match: created by member, or member appears in events
            is_author = issue.created_by == login
            commented = any(
                e.actor == login and e.event == "comment"
                for e in issue.events
            )
            if not is_author and not commented:
                continue
            if since_dt and issue.created_at < since_dt:
                if not issue.events or all(e.when < since_dt for e in issue.events):
                    continue
            if until_dt and issue.created_at > until_dt:
                continue
            results.append({
                "owner": r["owner"], "repo": r["name"],
                "number": issue.number, "title": issue.title,
                "created_by": issue.created_by,
                "created_at": _fmt(issue.created_at),
                "closed_at": _fmt(issue.closed_at),
                "state": "closed" if issue.closed_at else "open",
                "is_author": is_author,
                "commented": commented,
            })

    results.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return {"login": login, "issues": results, "total": len(results)}


@router.get("/prs")
async def member_prs(
    request: Request,
    login: str,
    owner: str | None = Query(None),
    repo: str | None = Query(None),
    since: str | None = Query(None, description="ISO date, e.g. 2025-01-01"),
    until: str | None = Query(None, description="ISO date, e.g. 2025-12-31"),
    state: str | None = Query(None),
    role: str | None = Query(None, description="Filter by role: opened, reviewed, collaborated"),
):
    """PRs where the member is author, reviewer, or collaborator."""
    db = request.app.state.db
    repos = await _get_repos(db, owner, repo)

    since_dt = _parse_date(since) if since else None
    until_dt = _parse_date(until) if until else None

    results = []
    for r in repos:
        prs = await get_cached_prs(db, r["id"], state=state)
        for pr in prs:
            is_author = pr.created_by == login
            is_reviewer = login in (pr.reviewers or [])
            is_collaborator = login in (pr.collaborators or [])

            if not is_author and not is_reviewer and not is_collaborator:
                continue

            # Apply role filter
            if role == "opened" and not is_author:
                continue
            if role == "reviewed" and not is_reviewer:
                continue
            if role == "collaborated" and not is_collaborator:
                continue

            if since_dt and pr.created_at < since_dt:
                continue
            if until_dt and pr.created_at > until_dt:
                continue

            if pr.merged_at:
                days_open = (pr.merged_at - pr.created_at).days
                pr_state = "merged"
            elif pr.closed_at:
                days_open = (pr.closed_at - pr.created_at).days
                pr_state = "closed"
            else:
                days_open = (datetime.now(tz=timezone.utc) - pr.created_at).days
                pr_state = "open"

            results.append({
                "owner": r["owner"], "repo": r["name"],
                "number": pr.number, "title": pr.title,
                "created_by": pr.created_by,
                "created_at": _fmt(pr.created_at),
                "merged_at": _fmt(pr.merged_at),
                "closed_at": _fmt(pr.closed_at),
                "state": pr_state,
                "days_open": days_open,
                "lines_changed": pr.lines_changed,
                "files_changed": pr.files_changed,
                "is_author": is_author,
                "is_reviewer": is_reviewer,
                "is_collaborator": is_collaborator,
            })

    results.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return {"login": login, "prs": results, "total": len(results)}


@router.get("/summary")
async def member_summary(
    request: Request,
    login: str,
    since: str | None = Query(None),
    until: str | None = Query(None),
):
    """Summary stats for a member across all repos."""
    db = request.app.state.db
    repos = await db.get_all_repos()

    since_dt = _parse_date(since) if since else None
    until_dt = _parse_date(until) if until else None

    issues_created = 0
    issues_commented = 0
    prs_created = 0
    prs_merged = 0
    prs_reviewed = 0
    prs_collaborated = 0
    total_lines = 0

    for r in repos:
        issues = await get_cached_issues(db, r["id"])
        for issue in issues:
            if since_dt and issue.created_at < since_dt:
                continue
            if until_dt and issue.created_at > until_dt:
                continue
            if issue.created_by == login:
                issues_created += 1
            if any(e.actor == login and e.event == "comment" for e in issue.events):
                issues_commented += 1

        prs = await get_cached_prs(db, r["id"])
        for pr in prs:
            if since_dt and pr.created_at < since_dt:
                continue
            if until_dt and pr.created_at > until_dt:
                continue
            if pr.created_by == login:
                prs_created += 1
                if pr.merged_at:
                    prs_merged += 1
                total_lines += pr.lines_changed
            if login in (pr.reviewers or []):
                prs_reviewed += 1
            if login in (pr.collaborators or []):
                prs_collaborated += 1

    return {
        "login": login,
        "issues_created": issues_created,
        "issues_commented": issues_commented,
        "prs_created": prs_created,
        "prs_merged": prs_merged,
        "prs_reviewed": prs_reviewed,
        "prs_collaborated": prs_collaborated,
        "total_lines_changed": total_lines,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_repos(db, owner: str | None, repo: str | None) -> list[dict]:
    if owner and repo:
        repo_id = await db.get_repo_id(owner, repo)
        if not repo_id:
            raise HTTPException(404, f"Repository {owner}/{repo} not found")
        return [{"id": repo_id, "owner": owner, "name": repo}]
    return await db.get_all_repos()


def _parse_date(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _fmt(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return f"{dt.year}-{dt.month:02d}-{dt.day:02d}"
