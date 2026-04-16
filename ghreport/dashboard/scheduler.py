"""Background sync scheduler."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .cache import sync_repo
from .config import Settings
from .db import Database

logger = logging.getLogger(__name__)


def _team_for(settings: Settings, owner: str, repo: str) -> str | None:
    """Look up team config for a repo."""
    for rc in settings.repos:
        if rc.owner == owner and rc.name == repo:
            return rc.team
    return None


class SyncScheduler:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        self.scheduler = AsyncIOScheduler()
        self._active_backfills: set[str] = set()

    def start(self):
        self.scheduler.add_job(
            self._sync_all,
            "interval",
            minutes=self.settings.sync_interval_minutes,
            id="sync_all_repos",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("Scheduler started (interval=%d min)", self.settings.sync_interval_minutes)

    async def _sync_all(self):
        """Sync all repos in the database (not just config-file repos)."""
        repos = await self.db.get_all_repos()
        logger.info("Starting scheduled sync for %d repos", len(repos))
        for r in repos:
            owner, name = r["owner"], r["name"]
            team = _team_for(self.settings, owner, name)
            try:
                result = await sync_repo(
                    self.db, owner, name,
                    self.settings.github_token, team=team,
                )
                logger.info(
                    "Synced %s/%s: %d issues, %d PRs",
                    owner, name,
                    result["issues_fetched"], result["prs_fetched"],
                )
            except Exception:
                logger.exception("Failed to sync %s/%s", owner, name)

    async def sync_one(self, owner: str, repo: str):
        """Sync a single repo in the background."""
        team = _team_for(self.settings, owner, repo)
        try:
            result = await sync_repo(
                self.db, owner, repo,
                self.settings.github_token, team=team,
            )
            logger.info(
                "Initial sync %s/%s: %d issues, %d PRs",
                owner, repo,
                result["issues_fetched"], result["prs_fetched"],
            )
        except Exception:
            logger.exception("Failed initial sync %s/%s", owner, repo)

    async def force_sync_one(self, owner: str, repo: str):
        """Force a full re-sync for a single repo (no incremental)."""
        team = _team_for(self.settings, owner, repo)
        try:
            result = await sync_repo(
                self.db, owner, repo,
                self.settings.github_token, team=team, force=True,
            )
            logger.info(
                "Force re-sync %s/%s: %d issues, %d PRs",
                owner, repo,
                result["issues_fetched"], result["prs_fetched"],
            )
        except Exception:
            logger.exception("Failed force re-sync %s/%s", owner, repo)

    async def backfill(self, owner: str, repo: str, since: datetime):
        """Fetch older data for a repo to cover a requested date range."""
        key = f"{owner}/{repo}"
        if key in self._active_backfills:
            return  # already running
        self._active_backfills.add(key)
        team = _team_for(self.settings, owner, repo)
        try:
            result = await sync_repo(
                self.db, owner, repo,
                self.settings.github_token, team=team,
                backfill_since=since,
            )
            logger.info(
                "Backfill %s/%s since %s: %d issues, %d PRs",
                owner, repo, since.isoformat(),
                result["issues_fetched"], result["prs_fetched"],
            )
        except Exception:
            logger.exception("Failed backfill %s/%s", owner, repo)
        finally:
            self._active_backfills.discard(key)

    def is_backfilling(self, owner: str, repo: str) -> bool:
        return f"{owner}/{repo}" in self._active_backfills

    def stop(self):
        self.scheduler.shutdown(wait=False)
