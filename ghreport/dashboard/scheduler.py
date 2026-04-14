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
        logger.info("Starting scheduled sync for %d repos", len(self.settings.repos))
        for repo_cfg in self.settings.repos:
            try:
                result = await sync_repo(
                    self.db, repo_cfg.owner, repo_cfg.name,
                    self.settings.github_token, team=repo_cfg.team,
                )
                logger.info(
                    "Synced %s/%s: %d issues, %d PRs",
                    repo_cfg.owner, repo_cfg.name,
                    result["issues_fetched"], result["prs_fetched"],
                )
            except Exception:
                logger.exception("Failed to sync %s/%s", repo_cfg.owner, repo_cfg.name)

    def stop(self):
        self.scheduler.shutdown(wait=False)
