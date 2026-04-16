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


DEFAULT_CONFIG = """# ghreport dashboard configuration
# Add repos via the web UI or uncomment and edit below:
#
# [[repos]]
# owner = "microsoft"
# name = "pyright"
"""


def _find_or_create_config(config_path: str | None) -> str | None:
    """Locate a config file, creating a default one if none exists."""
    if config_path:
        p = Path(config_path)
        if p.exists():
            return config_path
        # User specified a path that doesn't exist — create it
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(DEFAULT_CONFIG)
        print(f"Created default config: {p}")
        return config_path

    # Auto-discover: look for config.toml in cwd
    default = Path("config.toml")
    if default.exists():
        return str(default)

    # First run — create it
    default.write_text(DEFAULT_CONFIG)
    print(f"Created default config: {default}")
    return str(default)


def load_settings(config_path: str | None = None) -> Settings:
    """Load settings from env vars and optional TOML config file."""
    overrides: dict = {}

    # Read token from GH_TOKEN if not set via GHREPORT_GITHUB_TOKEN
    if not os.environ.get("GHREPORT_GITHUB_TOKEN"):
        gh_token = os.environ.get("GH_TOKEN", "")
        if gh_token:
            overrides["github_token"] = gh_token

    resolved = _find_or_create_config(config_path)
    if resolved and Path(resolved).exists():
        with open(resolved, "rb") as f:
            data = tomllib.load(f)
        if "repos" in data:
            overrides["repos"] = [RepoConfig(**r) for r in data["repos"]]
        for key in ("db_path", "sync_interval_minutes", "timezone", "host", "port", "github_token"):
            if key in data:
                overrides.setdefault(key, data[key])

    return Settings(**overrides)
