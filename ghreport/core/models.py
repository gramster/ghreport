"""Data models for ghreport."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Event:
    when: datetime
    actor: str
    event: str
    arg: str


@dataclass
class Issue:
    number: int
    title: str
    created_by: str
    closed_by: str | None
    created_at: datetime
    closed_at: datetime | None
    first_team_response_at: datetime | None  # first comment by team
    last_team_response_at: datetime | None  # last comment by team
    last_op_response_at: datetime | None  # last comment by OP
    last_response_at: datetime | None  # last comment by anyone
    events: list[Event]


@dataclass
class PullRequest:
    number: int
    title: str
    created_at: datetime
    created_by: str
    merged_at: datetime | None
    closed_at: datetime | None
    closed_by: str | None
    lines_changed: int
    files_changed: int
    files: list[str]
    reviewers: list[str] | None = None
    collaborators: list[str] | None = None
