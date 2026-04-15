"""Dashboard configuration using Pydantic settings."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


class RepoConfig(BaseModel):
    owner: str
    name: str
    pr_repo: str | None = None
    bug_label: str = "bug"
    team: str | None = None
    stale_days: int = 30


class Settings(BaseSettings):
    github_token: str = ""
    repos: list[RepoConfig] = []
    db_path: str = "data/ghreport.db"
    sync_interval_minutes: int = 10
    timezone: str = "America/Los_Angeles"
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_prefix": "GHREPORT_"}


def load_settings(config_path: str | None = None) -> Settings:
    """Load settings from env vars and optional TOML config file."""
    overrides: dict = {}

    # Read token from GH_TOKEN if not set via GHREPORT_GITHUB_TOKEN
    if not os.environ.get("GHREPORT_GITHUB_TOKEN"):
        gh_token = os.environ.get("GH_TOKEN", "")
        if gh_token:
            overrides["github_token"] = gh_token

    if config_path and Path(config_path).exists():
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        if "repos" in data:
            overrides["repos"] = [RepoConfig(**r) for r in data["repos"]]
        for key in ("db_path", "sync_interval_minutes", "timezone", "host", "port", "github_token"):
            if key in data:
                overrides.setdefault(key, data[key])

    return Settings(**overrides)
