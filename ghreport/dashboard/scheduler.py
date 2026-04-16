"""Background sync scheduler."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .cache import sync_repo
from .config import Settings
from .db import Database
from ..core.fetcher import get_active_retries, get_rate_limit_until, GitHubRateLimitError

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
        self._active_syncs: set[str] = set()
        self._recent_errors: list[dict] = []  # last N sync errors
        self._MAX_ERRORS = 20

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
            # Check global rate-limit cooldown before each repo
            cooldown = get_rate_limit_until()
            if cooldown:
                remaining = (cooldown - datetime.utcnow()).total_seconds()
                if remaining > 0:
                    logger.warning(
                        "Skipping remaining repos — rate-limited for %.0fs",
                        remaining,
                    )
                    break

            owner, name = r["owner"], r["name"]
            team = _team_for(self.settings, owner, name)
            key = f"{owner}/{name}"
            self._active_syncs.add(key)
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
            except GitHubRateLimitError as exc:
                logger.warning("Rate-limited syncing %s/%s, aborting remaining repos", owner, name)
                self._record_error(owner, name, exc)
                self._active_syncs.discard(key)
                break
            except Exception as exc:
                logger.exception("Failed to sync %s/%s", owner, name)
                self._record_error(owner, name, exc)
            finally:
                self._active_syncs.discard(key)

    async def sync_one(self, owner: str, repo: str):
        """Sync a single repo in the background."""
        team = _team_for(self.settings, owner, repo)
        key = f"{owner}/{repo}"
        self._active_syncs.add(key)
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
        except Exception as exc:
            logger.exception("Failed initial sync %s/%s", owner, repo)
            self._record_error(owner, repo, exc)
        finally:
            self._active_syncs.discard(key)

    async def force_sync_one(self, owner: str, repo: str):
        """Force a full re-sync for a single repo (no incremental)."""
        team = _team_for(self.settings, owner, repo)
        key = f"{owner}/{repo}"
        self._active_syncs.add(key)
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
        except Exception as exc:
            logger.exception("Failed force re-sync %s/%s", owner, repo)
            self._record_error(owner, repo, exc)
        finally:
            self._active_syncs.discard(key)

    async def backfill(self, owner: str, repo: str, since: datetime):
        """Fetch older data for a repo to cover a requested date range."""
        key = f"{owner}/{repo}"
        if key in self._active_backfills:
            return  # already running
        self._active_backfills.add(key)
        self._active_syncs.add(key)
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
        except Exception as exc:
            logger.exception("Failed backfill %s/%s", owner, repo)
            self._record_error(owner, repo, exc)
        finally:
            self._active_backfills.discard(key)
            self._active_syncs.discard(key)

    def is_backfilling(self, owner: str, repo: str) -> bool:
        return f"{owner}/{repo}" in self._active_backfills

    def is_syncing(self, owner: str, repo: str) -> bool:
        return f"{owner}/{repo}" in self._active_syncs

    @property
    def active_syncs(self) -> list[str]:
        return sorted(self._active_syncs)

    @property
    def active_retries(self) -> dict[str, dict]:
        return get_active_retries()

    @property
    def rate_limited_until(self) -> str | None:
        rl = get_rate_limit_until()
        return rl.isoformat() + "Z" if rl else None

    @property
    def recent_errors(self) -> list[dict]:
        return list(self._recent_errors)

    def _record_error(self, owner: str, repo: str, exc: Exception):
        from datetime import datetime as dt
        self._recent_errors.append({
            "repo": f"{owner}/{repo}",
            "error": f"{type(exc).__name__}: {exc}",
            "when": dt.utcnow().isoformat() + "Z",
        })
        # Keep only the most recent errors
        if len(self._recent_errors) > self._MAX_ERRORS:
            self._recent_errors = self._recent_errors[-self._MAX_ERRORS:]

    def clear_errors(self):
        self._recent_errors.clear()

    def stop(self):
        self.scheduler.shutdown(wait=False)
