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

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL REFERENCES repos(id),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    issues_fetched INTEGER DEFAULT 0,
    prs_fetched INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_issues_repo_state ON issues(repo_id, state);
CREATE INDEX IF NOT EXISTS idx_issues_repo_number ON issues(repo_id, number);
CREATE INDEX IF NOT EXISTS idx_prs_repo_state ON pull_requests(repo_id, state);
CREATE INDEX IF NOT EXISTS idx_prs_repo_number ON pull_requests(repo_id, number);
CREATE INDEX IF NOT EXISTS idx_events_issue ON events(issue_id);
CREATE INDEX IF NOT EXISTS idx_pr_files_pr ON pr_files(pr_id);
CREATE INDEX IF NOT EXISTS idx_team_members_repo ON team_members(repo_id);
CREATE INDEX IF NOT EXISTS idx_sync_log_repo ON sync_log(repo_id);
"""


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA)
        await self._db.commit()

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

    async def update_last_synced(self, repo_id: int, when: str):
        await self.db.execute(
            "UPDATE repos SET last_synced_at = ? WHERE id = ?", (when, repo_id)
        )
        await self.db.commit()
