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


class SyncScheduler:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        self.scheduler = AsyncIOScheduler()

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
            # Look up team config if available
            team = None
            for rc in self.settings.repos:
                if rc.owner == owner and rc.name == name:
                    team = rc.team
                    break
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
        team = None
        for rc in self.settings.repos:
            if rc.owner == owner and rc.name == repo:
                team = rc.team
                break
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

    def stop(self):
        self.scheduler.shutdown(wait=False)
