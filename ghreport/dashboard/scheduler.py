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
        # Serialize all GitHub API access — only one repo syncs at a time
        self._sync_lock = asyncio.Lock()
        # Priority queue: repos needing immediate sync (e.g. newly added)
        self._priority_queue: list[tuple[str, str, bool]] = []  # (owner, repo, force)

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

    def _check_rate_limit(self) -> bool:
        """Return True if rate-limited (should skip)."""
        cooldown = get_rate_limit_until()
        if cooldown:
            remaining = (cooldown - datetime.now()).total_seconds()
            if remaining > 0:
                logger.warning("Rate-limited for %.0fs, skipping", remaining)
                return True
        return False

    async def _sync_one_repo(self, owner: str, repo: str, *,
                              force: bool = False,
                              backfill_since: datetime | None = None) -> bool:
        """Sync a single repo while holding the lock. Returns True on success."""
        if self._check_rate_limit():
            return False

        team = _team_for(self.settings, owner, repo)
        key = f"{owner}/{repo}"
        is_backfill = backfill_since is not None

        self._active_syncs.add(key)
        if is_backfill:
            self._active_backfills.add(key)
        try:
            result = await sync_repo(
                self.db, owner, repo,
                self.settings.github_token, team=team,
                force=force, backfill_since=backfill_since,
            )
            logger.info(
                "Synced %s/%s: %d issues, %d PRs",
                owner, repo,
                result["issues_fetched"], result["prs_fetched"],
            )
            return True
        except GitHubRateLimitError as exc:
            logger.warning("Rate-limited syncing %s/%s", owner, repo)
            self._record_error(owner, repo, exc)
            return False
        except Exception as exc:
            logger.exception("Failed to sync %s/%s", owner, repo)
            self._record_error(owner, repo, exc)
            return True  # non-rate-limit error — OK to continue with other repos
        finally:
            self._active_syncs.discard(key)
            if is_backfill:
                self._active_backfills.discard(key)

    async def _sync_all(self):
        """Sync all repos in the database, one at a time."""
        # Drain priority queue first (newly added repos, etc.)
        while self._priority_queue:
            owner, repo, force = self._priority_queue.pop(0)
            async with self._sync_lock:
                ok = await self._sync_one_repo(owner, repo, force=force)
            if not ok:
                break  # rate-limited, stop entirely

        # Then sync all repos in DB
        repos = await self.db.get_all_repos()
        logger.info("Starting scheduled sync for %d repos", len(repos))
        for r in repos:
            # Drain any priority items that arrived between repos
            while self._priority_queue:
                p_owner, p_repo, p_force = self._priority_queue.pop(0)
                async with self._sync_lock:
                    ok = await self._sync_one_repo(p_owner, p_repo, force=p_force)
                if not ok:
                    return  # rate-limited

            async with self._sync_lock:
                ok = await self._sync_one_repo(r["owner"], r["name"])
            if not ok:
                break  # rate-limited, stop

    async def sync_one(self, owner: str, repo: str):
        """Sync a single repo in the background."""
        async with self._sync_lock:
            await self._sync_one_repo(owner, repo)

    async def force_sync_one(self, owner: str, repo: str):
        """Force a full re-sync for a single repo (no incremental)."""
        async with self._sync_lock:
            await self._sync_one_repo(owner, repo, force=True)

    def queue_sync(self, owner: str, repo: str, force: bool = False):
        """Add a repo to the priority queue for next sync cycle.

        If a sync cycle is already running, the repo will be picked up
        between the current and next repo in the batch.
        """
        key = (owner, repo, force)
        if key not in self._priority_queue:
            self._priority_queue.append(key)
            logger.info("Queued %s/%s for priority sync (force=%s)", owner, repo, force)

    async def backfill(self, owner: str, repo: str, since: datetime):
        """Fetch older data for a repo to cover a requested date range."""
        key = f"{owner}/{repo}"
        if key in self._active_backfills:
            return  # already running
        async with self._sync_lock:
            await self._sync_one_repo(owner, repo, backfill_since=since)

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
