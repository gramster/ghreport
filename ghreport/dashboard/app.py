"""FastAPI application factory for the ghreport dashboard."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import logging

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, load_settings
from .db import Database
from .scheduler import SyncScheduler
from .cache import scan_copilot_users
from .routes import repos, issues, prs, reports, charts, aggregate, sync, team, members

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    settings: Settings = app.state.settings
    db = Database(settings.db_path)
    await db.connect()
    app.state.db = db

    # Ensure configured repos exist in DB
    for rc in settings.repos:
        await db.ensure_repo(rc.owner, rc.name)

    # Start background scheduler
    scheduler = SyncScheduler(db, settings)
    scheduler.start()
    app.state.scheduler = scheduler

    # Scan cached data for copilot users
    await scan_copilot_users(db)

    # Check if reviewer/collaborator data needs to be populated
    # (e.g. after schema change adding those tables)
    await _maybe_resync_for_roles(db, scheduler)

    yield

    # Shutdown
    scheduler.stop()
    await db.close()


async def _maybe_resync_for_roles(db: Database, scheduler: SyncScheduler):
    """Trigger a full re-sync if reviewer/collaborator data is missing.

    Detects PRs whose raw_json doesn't contain 'reviews' — meaning they
    were fetched before the GraphQL queries were updated to include
    review/commit data.
    """
    stale = (await (await db.db.execute(
        "SELECT COUNT(*) FROM pull_requests WHERE raw_json NOT LIKE '%\"reviews\"%'"
    )).fetchone())[0]
    if stale == 0:
        return

    total = (await (await db.db.execute(
        "SELECT COUNT(*) FROM pull_requests"
    )).fetchone())[0]

    logger.info(
        "Detected %d/%d PRs with stale data (missing reviews field) — "
        "scheduling full re-sync to populate role data", stale, total,
    )
    repos_list = await db.get_all_repos()
    import asyncio
    for r in repos_list:
        asyncio.create_task(scheduler.force_sync_one(r["owner"], r["name"]))


def create_app(config_path: str | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = load_settings(config_path)

    app = FastAPI(
        title="ghreport Dashboard",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = settings

    # Include API routers
    app.include_router(repos.router)
    app.include_router(issues.router)
    app.include_router(prs.router)
    app.include_router(reports.router)
    app.include_router(charts.router)
    app.include_router(aggregate.router)
    app.include_router(sync.router)
    app.include_router(team.router)
    app.include_router(members.router)

    # Mount Vue frontend static files (if built)
    frontend_dist = Path(__file__).parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        index_html = frontend_dist / "index.html"

        # Serve static assets (js, css, images) from dist
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")),
                  name="assets")

        # SPA fallback: any non-API route serves index.html for Vue Router
        @app.get("/{full_path:path}")
        async def spa_fallback(request: Request, full_path: str):
            return FileResponse(str(index_html))

    return app


def main():
    """Entry point for running the dashboard server."""
    import uvicorn

    config_path = os.environ.get("GHREPORT_CONFIG")
    app = create_app(config_path)
    settings = app.state.settings
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
