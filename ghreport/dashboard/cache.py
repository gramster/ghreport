"""Cache layer: sync GitHub data into SQLite and retrieve as core models."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from ..core.fetcher import get_raw_issues, get_raw_pull_requests
from ..core.models import Event, Issue, PullRequest
from ..core.parser import parse_raw_issue, parse_raw_pull_request, utc_to_local, format_date
from ..core.teams import get_members
from .db import Database

logger = logging.getLogger(__name__)


def _dt_str(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s)


def _collect_copilot_users(raw: dict, found: set[str]):
    """Scan a raw issue/PR for usernames containing 'copilot' (case-insensitive)."""
    for field in ('author', 'mergedBy', 'actor', 'assignee'):
        node = raw.get(field)
        if isinstance(node, dict):
            login = node.get('login', '')
            if login and 'copilot' in login.lower():
                found.add(login)
    # Also check timeline comments/events
    timeline = raw.get('timelineItems', {}).get('nodes', [])
    for event in timeline:
        if not isinstance(event, dict):
            continue
        for field in ('author', 'actor', 'assignee'):
            node = event.get(field)
            if isinstance(node, dict):
                login = node.get('login', '')
                if login and 'copilot' in login.lower():
                    found.add(login)


async def sync_repo(db: Database, owner: str, repo: str, token: str,
                    team: str | None = None, force: bool = False,
                    backfill_since: datetime | None = None) -> dict:
    """Fetch data from GitHub and upsert into SQLite.

    If *backfill_since* is given, only fetch data created/updated since that
    date — used when the user's date-range extends before the cached window.

    Returns a summary dict with counts.
    """
    repo_id = await db.ensure_repo(owner, repo)

    # Log sync start
    now_str = datetime.utcnow().isoformat()
    cursor = await db.db.execute(
        "INSERT INTO sync_log (repo_id, started_at, status) VALUES (?, ?, 'running')",
        (repo_id, now_str),
    )
    sync_id = cursor.lastrowid
    await db.db.commit()

    # Determine since date for incremental sync
    since = None
    if backfill_since:
        # Targeted backfill for a specific date range
        since = backfill_since
    elif not force:
        row = await (await db.db.execute(
            "SELECT last_synced_at FROM repos WHERE id = ?", (repo_id,)
        )).fetchone()
        if row and row[0]:
            since = datetime.fromisoformat(row[0]) - timedelta(days=1)

    # Track the effective search boundary for data_since
    effective_since = since or (datetime.now(tz=timezone.utc) - timedelta(days=365 * 10))

    # Fetch team members
    members = get_members(owner, repo, token)
    if team:
        if team.startswith('+'):
            members.update(team[1:].split(','))
        else:
            members = set(team.split(','))

    # Include common team members so response-time calculations are accurate
    common_cursor = await db.db.execute("SELECT login FROM common_team_members")
    common_rows = await common_cursor.fetchall()
    common_logins = {r["login"] for r in common_rows}

    # Store team members (without common members — those are separate)
    await db.db.execute("DELETE FROM team_members WHERE repo_id = ?", (repo_id,))
    for login in members:
        await db.db.execute(
            "INSERT OR IGNORE INTO team_members (repo_id, login) VALUES (?, ?)",
            (repo_id, login),
        )

    # Merge common members into the set used for parsing (not persisted above)
    members.update(common_logins)

    # Fetch and store issues
    # For incremental sync, use updated:>= for all states to catch
    # newly created, recently closed, commented, and relabeled issues
    # without re-fetching all unchanged open issues.
    issues_count = 0
    copilot_users: set[str] = set()
    incremental = since is not None
    for state in ('open', 'closed'):
        raw_issues = await get_raw_issues(
            owner, repo, token, state=state,
            since=since, use_updated=incremental,
        )
        for raw in raw_issues:
            _collect_copilot_users(raw, copilot_users)
            parsed = parse_raw_issue(raw, members)
            if not parsed:
                continue
            issues_count += 1
            await _upsert_issue(db, repo_id, parsed, raw, state)

    # Fetch and store PRs
    # For incremental sync, only fetch PRs updated since last sync.
    prs_count = 0
    for state in ('open', 'closed', 'merged'):
        s = since if (incremental or state != 'open') else None
        raw_prs = await get_raw_pull_requests(owner, repo, token, state=state, since=s,
                                              use_updated=incremental)
        for raw in raw_prs:
            _collect_copilot_users(raw, copilot_users)
            parsed = parse_raw_pull_request(raw)
            if not parsed:
                continue
            prs_count += 1
            pr_state = 'merged' if parsed.merged_at else ('closed' if parsed.closed_at else 'open')
            await _upsert_pr(db, repo_id, parsed, raw, pr_state)

    if copilot_users:
        print(
            f"[copilot] Users in {owner}/{repo}: {', '.join(sorted(copilot_users))}",
            flush=True,
        )

    # Update sync status
    completed_str = datetime.utcnow().isoformat()
    await db.db.execute(
        "UPDATE sync_log SET completed_at = ?, status = 'completed', "
        "issues_fetched = ?, prs_fetched = ? WHERE id = ?",
        (completed_str, issues_count, prs_count, sync_id),
    )
    await db.update_last_synced(repo_id, completed_str)
    await db.update_data_since(repo_id, effective_since.isoformat())
    await db.db.commit()

    return {"issues_fetched": issues_count, "prs_fetched": prs_count}


async def _upsert_issue(db: Database, repo_id: int, issue: Issue, raw: dict, state: str):
    """Insert or update an issue and its events."""
    # Check if exists
    cursor = await db.db.execute(
        "SELECT id FROM issues WHERE repo_id = ? AND number = ?", (repo_id, issue.number)
    )
    existing = await cursor.fetchone()

    if existing:
        issue_db_id = existing[0]
        await db.db.execute("""
            UPDATE issues SET title=?, created_by=?, closed_by=?, created_at=?, closed_at=?,
            first_team_response_at=?, last_team_response_at=?, last_op_response_at=?,
            last_response_at=?, state=?, raw_json=? WHERE id=?
        """, (issue.title, issue.created_by, issue.closed_by,
              _dt_str(issue.created_at), _dt_str(issue.closed_at),
              _dt_str(issue.first_team_response_at), _dt_str(issue.last_team_response_at),
              _dt_str(issue.last_op_response_at), _dt_str(issue.last_response_at),
              state, json.dumps(raw), issue_db_id))
        # Replace events
        await db.db.execute("DELETE FROM events WHERE issue_id = ?", (issue_db_id,))
    else:
        cursor = await db.db.execute("""
            INSERT INTO issues (repo_id, number, title, created_by, closed_by, created_at,
            closed_at, first_team_response_at, last_team_response_at, last_op_response_at,
            last_response_at, state, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (repo_id, issue.number, issue.title, issue.created_by, issue.closed_by,
              _dt_str(issue.created_at), _dt_str(issue.closed_at),
              _dt_str(issue.first_team_response_at), _dt_str(issue.last_team_response_at),
              _dt_str(issue.last_op_response_at), _dt_str(issue.last_response_at),
              state, json.dumps(raw)))
        issue_db_id = cursor.lastrowid

    # Insert events
    for evt in issue.events:
        await db.db.execute(
            "INSERT INTO events (issue_id, when_at, actor, event, arg) VALUES (?, ?, ?, ?, ?)",
            (issue_db_id, _dt_str(evt.when), evt.actor, evt.event, evt.arg),
        )


async def _upsert_pr(db: Database, repo_id: int, pr: PullRequest, raw: dict, state: str):
    """Insert or update a pull request and its files."""
    cursor = await db.db.execute(
        "SELECT id FROM pull_requests WHERE repo_id = ? AND number = ?", (repo_id, pr.number)
    )
    existing = await cursor.fetchone()

    if existing:
        pr_db_id = existing[0]
        await db.db.execute("""
            UPDATE pull_requests SET title=?, created_by=?, closed_by=?, created_at=?,
            merged_at=?, closed_at=?, lines_changed=?, files_changed=?, state=?, raw_json=?
            WHERE id=?
        """, (pr.title, pr.created_by, pr.closed_by,
              _dt_str(pr.created_at), _dt_str(pr.merged_at), _dt_str(pr.closed_at),
              pr.lines_changed, pr.files_changed, state, json.dumps(raw), pr_db_id))
        await db.db.execute("DELETE FROM pr_files WHERE pr_id = ?", (pr_db_id,))
        await db.db.execute("DELETE FROM pr_reviewers WHERE pr_id = ?", (pr_db_id,))
        await db.db.execute("DELETE FROM pr_collaborators WHERE pr_id = ?", (pr_db_id,))
    else:
        cursor = await db.db.execute("""
            INSERT INTO pull_requests (repo_id, number, title, created_by, closed_by,
            created_at, merged_at, closed_at, lines_changed, files_changed, state, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (repo_id, pr.number, pr.title, pr.created_by, pr.closed_by,
              _dt_str(pr.created_at), _dt_str(pr.merged_at), _dt_str(pr.closed_at),
              pr.lines_changed, pr.files_changed, state, json.dumps(raw)))
        pr_db_id = cursor.lastrowid

    for path in pr.files:
        await db.db.execute(
            "INSERT INTO pr_files (pr_id, path) VALUES (?, ?)", (pr_db_id, path)
        )

    for login in (pr.reviewers or []):
        await db.db.execute(
            "INSERT INTO pr_reviewers (pr_id, login) VALUES (?, ?)", (pr_db_id, login)
        )

    for login in (pr.collaborators or []):
        await db.db.execute(
            "INSERT INTO pr_collaborators (pr_id, login) VALUES (?, ?)", (pr_db_id, login)
        )


# ---------------------------------------------------------------------------
# Cache read functions — convert SQLite rows to core models
# ---------------------------------------------------------------------------

async def get_cached_issues(db: Database, repo_id: int,
                            state: str | None = None) -> list[Issue]:
    """Load issues from cache as core Issue models."""
    if state:
        cursor = await db.db.execute(
            "SELECT * FROM issues WHERE repo_id = ? AND state = ?", (repo_id, state)
        )
    else:
        cursor = await db.db.execute(
            "SELECT * FROM issues WHERE repo_id = ?", (repo_id,)
        )
    rows = await cursor.fetchall()

    issues = []
    for row in rows:
        row_dict = dict(row)
        # Load events
        evt_cursor = await db.db.execute(
            "SELECT when_at, actor, event, arg FROM events WHERE issue_id = ? ORDER BY when_at",
            (row_dict["id"],)
        )
        evt_rows = await evt_cursor.fetchall()
        events = [Event(
            when=_parse_dt(e["when_at"]),  # type: ignore
            actor=e["actor"] or "",
            event=e["event"] or "",
            arg=e["arg"] or "",
        ) for e in evt_rows]

        issues.append(Issue(
            number=row_dict["number"],
            title=row_dict["title"],
            created_by=row_dict["created_by"] or "",
            closed_by=row_dict["closed_by"],
            created_at=_parse_dt(row_dict["created_at"]),  # type: ignore
            closed_at=_parse_dt(row_dict["closed_at"]),
            first_team_response_at=_parse_dt(row_dict["first_team_response_at"]),
            last_team_response_at=_parse_dt(row_dict["last_team_response_at"]),
            last_op_response_at=_parse_dt(row_dict["last_op_response_at"]),
            last_response_at=_parse_dt(row_dict["last_response_at"]),
            events=events,
        ))
    return issues


async def get_cached_prs(db: Database, repo_id: int,
                         state: str | None = None) -> list[PullRequest]:
    """Load pull requests from cache as core PullRequest models."""
    if state:
        cursor = await db.db.execute(
            "SELECT * FROM pull_requests WHERE repo_id = ? AND state = ?", (repo_id, state)
        )
    else:
        cursor = await db.db.execute(
            "SELECT * FROM pull_requests WHERE repo_id = ?", (repo_id,)
        )
    rows = await cursor.fetchall()

    prs = []
    for row in rows:
        row_dict = dict(row)
        # Load files
        file_cursor = await db.db.execute(
            "SELECT path FROM pr_files WHERE pr_id = ?", (row_dict["id"],)
        )
        file_rows = await file_cursor.fetchall()
        files = [f["path"] for f in file_rows]

        # Load reviewers
        rev_cursor = await db.db.execute(
            "SELECT login FROM pr_reviewers WHERE pr_id = ?", (row_dict["id"],)
        )
        rev_rows = await rev_cursor.fetchall()
        reviewers = [r["login"] for r in rev_rows]

        # Load collaborators
        collab_cursor = await db.db.execute(
            "SELECT login FROM pr_collaborators WHERE pr_id = ?", (row_dict["id"],)
        )
        collab_rows = await collab_cursor.fetchall()
        collaborators = [r["login"] for r in collab_rows]

        prs.append(PullRequest(
            number=row_dict["number"],
            title=row_dict["title"],
            created_at=_parse_dt(row_dict["created_at"]),  # type: ignore
            created_by=row_dict["created_by"] or "",
            merged_at=_parse_dt(row_dict["merged_at"]),
            closed_at=_parse_dt(row_dict["closed_at"]),
            closed_by=row_dict["closed_by"],
            lines_changed=row_dict["lines_changed"] or 0,
            files_changed=row_dict["files_changed"] or 0,
            files=files,
            reviewers=reviewers,
            collaborators=collaborators,
        ))
    return prs


async def get_cached_team_members(db: Database, repo_id: int) -> set[str]:
    """Return combined common + repo-specific team members."""
    cursor = await db.db.execute(
        "SELECT login FROM team_members WHERE repo_id = ?", (repo_id,)
    )
    rows = await cursor.fetchall()
    members = {r["login"] for r in rows}

    # Merge common members
    cursor2 = await db.db.execute("SELECT login FROM common_team_members")
    rows2 = await cursor2.fetchall()
    members.update(r["login"] for r in rows2)

    return members


async def get_sync_status(db: Database, repo_id: int) -> dict | None:
    cursor = await db.db.execute(
        "SELECT * FROM sync_log WHERE repo_id = ? ORDER BY started_at DESC LIMIT 1",
        (repo_id,)
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def scan_copilot_users(db: Database) -> dict[str, set[str]]:
    """Scan cached raw_json in DB for usernames containing 'copilot'.

    Returns {repo_slug: {login, ...}}.
    """
    import re
    pattern = re.compile(r'"login"\s*:\s*"([^"]*copilot[^"]*)"', re.IGNORECASE)
    result: dict[str, set[str]] = {}

    repos = await db.get_all_repos()
    for r in repos:
        slug = f"{r['owner']}/{r['name']}"
        found: set[str] = set()

        for table in ('issues', 'pull_requests'):
            cursor = await db.db.execute(
                f"SELECT raw_json FROM {table} WHERE repo_id = ?", (r['id'],)
            )
            async for row in cursor:
                raw = row[0] or ''
                for m in pattern.finditer(raw):
                    found.add(m.group(1))

        if found:
            result[slug] = found
            print(
                f"[copilot] Cached users in {slug}: {', '.join(sorted(found))}",
                flush=True,
            )

    return result


# ---------------------------------------------------------------------------
# Date-range filtering helpers
# ---------------------------------------------------------------------------

def parse_date_param(s: str | None, end_of_day: bool = False) -> datetime | None:
    """Parse a date string (e.g. '2025-01-15') into a timezone-aware datetime."""
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if end_of_day and len(s) <= 10:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt


def filter_active_issues(
    issues: list[Issue],
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[Issue]:
    """Keep issues that were active (open at any point) during [since, until].

    An issue is active in the window if its lifetime overlaps:
    created_at <= until AND (closed_at is NULL OR closed_at >= since).
    """
    if not since and not until:
        return issues
    result = []
    for issue in issues:
        if until and issue.created_at and issue.created_at > until:
            continue
        if since and issue.closed_at and issue.closed_at < since:
            continue
        result.append(issue)
    return result


def filter_active_prs(
    prs: list[PullRequest],
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[PullRequest]:
    """Keep PRs that were active during [since, until]."""
    if not since and not until:
        return prs
    result = []
    for pr in prs:
        if until and pr.created_at and pr.created_at > until:
            continue
        end = pr.merged_at or pr.closed_at
        if since and end and end < since:
            continue
        result.append(pr)
    return result
