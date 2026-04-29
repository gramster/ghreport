"""SQLite database schema and connection management."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    last_synced_at TEXT,
    data_since TEXT,
    sync_start_at TEXT,
    config_json TEXT,
    UNIQUE(owner, name)
);

CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL REFERENCES repos(id),
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    created_by TEXT,
    closed_by TEXT,
    created_at TEXT,
    closed_at TEXT,
    first_team_response_at TEXT,
    last_team_response_at TEXT,
    last_op_response_at TEXT,
    last_response_at TEXT,
    state TEXT NOT NULL DEFAULT 'open',
    reactions INTEGER DEFAULT 0,
    raw_json TEXT,
    UNIQUE(repo_id, number)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    when_at TEXT NOT NULL,
    actor TEXT,
    event TEXT,
    arg TEXT
);

CREATE TABLE IF NOT EXISTS pull_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL REFERENCES repos(id),
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    created_by TEXT,
    closed_by TEXT,
    created_at TEXT,
    merged_at TEXT,
    closed_at TEXT,
    lines_changed INTEGER DEFAULT 0,
    files_changed INTEGER DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'open',
    raw_json TEXT,
    UNIQUE(repo_id, number)
);

CREATE TABLE IF NOT EXISTS pr_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
    path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL REFERENCES repos(id),
    login TEXT NOT NULL,
    UNIQUE(repo_id, login)
);

CREATE TABLE IF NOT EXISTS common_team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL REFERENCES repos(id),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    issues_fetched INTEGER DEFAULT 0,
    prs_fetched INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS pr_reviewers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
    login TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pr_collaborators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
    login TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_issues_repo_state ON issues(repo_id, state);
CREATE INDEX IF NOT EXISTS idx_issues_repo_number ON issues(repo_id, number);
CREATE INDEX IF NOT EXISTS idx_prs_repo_state ON pull_requests(repo_id, state);
CREATE INDEX IF NOT EXISTS idx_prs_repo_number ON pull_requests(repo_id, number);
CREATE INDEX IF NOT EXISTS idx_events_issue ON events(issue_id);
CREATE INDEX IF NOT EXISTS idx_pr_files_pr ON pr_files(pr_id);
CREATE INDEX IF NOT EXISTS idx_pr_reviewers_pr ON pr_reviewers(pr_id);
CREATE INDEX IF NOT EXISTS idx_pr_reviewers_login ON pr_reviewers(login);
CREATE INDEX IF NOT EXISTS idx_pr_collaborators_pr ON pr_collaborators(pr_id);
CREATE INDEX IF NOT EXISTS idx_pr_collaborators_login ON pr_collaborators(login);
CREATE INDEX IF NOT EXISTS idx_team_members_repo ON team_members(repo_id);
CREATE INDEX IF NOT EXISTS idx_sync_log_repo ON sync_log(repo_id);
"""


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self):
        is_new = not os.path.exists(self.db_path)
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA)
        # Migrations — add columns if missing
        await self._migrate()
        # Clean up syncs that were left 'running' by a previous server instance.
        await self._db.execute(
            "UPDATE sync_log SET status = 'interrupted', completed_at = datetime('now')"
            " WHERE status = 'running'"
        )
        # Seed default common team members on first run
        if is_new:
            await self._seed_defaults()
        await self._db.commit()

    async def _migrate(self):
        """Run lightweight column migrations."""
        cursor = await self._db.execute("PRAGMA table_info(repos)")
        cols = {row[1] for row in await cursor.fetchall()}
        if "data_since" not in cols:
            await self._db.execute(
                "ALTER TABLE repos ADD COLUMN data_since TEXT"
            )
        if "sync_start_at" not in cols:
            await self._db.execute(
                "ALTER TABLE repos ADD COLUMN sync_start_at TEXT"
            )
        # Add error_message to sync_log
        cursor2 = await self._db.execute("PRAGMA table_info(sync_log)")
        sync_cols = {row[1] for row in await cursor2.fetchall()}
        if "error_message" not in sync_cols:
            await self._db.execute(
                "ALTER TABLE sync_log ADD COLUMN error_message TEXT"
            )
        # Add cluster column to issues
        cursor3 = await self._db.execute("PRAGMA table_info(issues)")
        issue_cols = {row[1] for row in await cursor3.fetchall()}
        if "cluster" not in issue_cols:
            await self._db.execute(
                "ALTER TABLE issues ADD COLUMN cluster TEXT"
            )
        if "reactions" not in issue_cols:
            await self._db.execute(
                "ALTER TABLE issues ADD COLUMN reactions INTEGER DEFAULT 0"
            )

    async def _seed_defaults(self):
        """Seed default common team members on first database creation."""
        defaults = ["dependabot", "app/copilot-swe-agent"]
        for login in defaults:
            await self._db.execute(
                "INSERT OR IGNORE INTO common_team_members (login) VALUES (?)",
                (login,),
            )

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Database not connected"
        return self._db

    async def ensure_repo(self, owner: str, name: str, config_json: str = "{}") -> int:
        """Get or create a repo row, returning its id."""
        cursor = await self.db.execute(
            "SELECT id FROM repos WHERE owner = ? AND name = ?", (owner, name)
        )
        row = await cursor.fetchone()
        if row:
            return row[0]
        cursor = await self.db.execute(
            "INSERT INTO repos (owner, name, config_json) VALUES (?, ?, ?)",
            (owner, name, config_json),
        )
        await self.db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def get_repo_id(self, owner: str, name: str) -> int | None:
        cursor = await self.db.execute(
            "SELECT id FROM repos WHERE owner = ? AND name = ?", (owner, name)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def get_all_repos(self) -> list[dict]:
        cursor = await self.db.execute(
            "SELECT id, owner, name, last_synced_at, config_json FROM repos"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def remove_repo(self, repo_id: int):
        """Delete a repo and all its associated data."""
        await self.db.execute("DELETE FROM sync_log WHERE repo_id = ?", (repo_id,))
        await self.db.execute("DELETE FROM team_members WHERE repo_id = ?", (repo_id,))
        # Delete events for this repo's issues
        await self.db.execute(
            "DELETE FROM events WHERE issue_id IN (SELECT id FROM issues WHERE repo_id = ?)",
            (repo_id,),
        )
        await self.db.execute("DELETE FROM issues WHERE repo_id = ?", (repo_id,))
        # Delete pr_files for this repo's PRs
        await self.db.execute(
            "DELETE FROM pr_files WHERE pr_id IN (SELECT id FROM pull_requests WHERE repo_id = ?)",
            (repo_id,),
        )
        await self.db.execute("DELETE FROM pull_requests WHERE repo_id = ?", (repo_id,))
        await self.db.execute("DELETE FROM repos WHERE id = ?", (repo_id,))
        await self.db.commit()

    async def update_last_synced(self, repo_id: int, when: str):
        await self.db.execute(
            "UPDATE repos SET last_synced_at = ? WHERE id = ?", (when, repo_id)
        )

    async def update_sync_start(self, repo_id: int, sync_start_iso: str):
        """Persist the start timestamp of a completed sync as covered_until."""
        await self.db.execute(
            "UPDATE repos SET sync_start_at = ? WHERE id = ?",
            (sync_start_iso, repo_id),
        )

    async def update_data_since(self, repo_id: int, since_iso: str):
        """Update data_since only if the new value is earlier."""
        row = await (await self.db.execute(
            "SELECT data_since FROM repos WHERE id = ?", (repo_id,)
        )).fetchone()
        if not row or not row[0] or since_iso < row[0]:
            await self.db.execute(
                "UPDATE repos SET data_since = ? WHERE id = ?",
                (since_iso, repo_id),
            )

    async def get_data_since(self, repo_id: int) -> str | None:
        row = await (await self.db.execute(
            "SELECT data_since FROM repos WHERE id = ?", (repo_id,)
        )).fetchone()
        return row[0] if row else None
        await self.db.commit()

    async def count_prs(self, repo_id: int, state: str | None = None) -> int:
        """Return PR count for a repo, optionally filtered by state."""
        if state:
            row = await (await self.db.execute(
                "SELECT COUNT(*) FROM pull_requests WHERE repo_id = ? AND state = ?",
                (repo_id, state),
            )).fetchone()
        else:
            row = await (await self.db.execute(
                "SELECT COUNT(*) FROM pull_requests WHERE repo_id = ?",
                (repo_id,),
            )).fetchone()
        return row[0] if row else 0
