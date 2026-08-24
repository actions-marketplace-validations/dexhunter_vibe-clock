"""The public wire contract between `vibe-clock push` and `vibe-clock render`.

`AgentStats` is the internal aggregate: every field has a default, so loading a
payload into it can never fail. That is exactly wrong for data crossing a
version boundary — a producer that never sent `active_days` and a user who was
genuinely idle both come out as 0, and the card prints "Active Days: 0" with no
way to tell which happened.

`PublicPayload` is the opposite by construction:

* Fields that every producer always emits are **required**. A missing one is a
  version skew and raises instead of defaulting.
* Fields the user chooses to share are ``| None``. Absent means "not shared",
  which is a different thing from zero, and charts that need them refuse to
  render rather than drawing an empty picture.
* ``extra="forbid"``, so a key this reader does not understand is an error
  rather than silent data loss.

SCHEMA_VERSION must be bumped on **any** change to the emitted key set.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, ValidationError

from . import __version__
from .models import (
    AgentStats,
    DailyActivity,
    ModelBreakdown,
    ProjectBreakdown,
    TokenUsage,
)

# Bump whenever the emitted key set changes.
SCHEMA_VERSION = 3
# The oldest payload this reader understands.
MIN_READABLE_SCHEMA = 3

_UPGRADE_PRODUCER = (
    "Upgrade the machine that runs `vibe-clock push` "
    "(`uv tool upgrade vibe-clock`, or `pip install -U vibe-clock`) and push again."
)
_UPGRADE_READER = (
    "Upgrade the reader: bump the `dexhunter/vibe-clock@vX.Y.Z` pin in your "
    "workflow, or `pip install -U vibe-clock` locally."
)


class PayloadError(Exception):
    """A public payload could not be read, with an actionable explanation."""


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    session_count: int
    message_count: int | None = None
    tokens: TokenUsage | None = None


class PublicDaily(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    session_count: int
    message_count: int | None = None
    tokens: TokenUsage | None = None


class PublicProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str
    agent: str
    session_count: int
    tokens: TokenUsage | None = None


class PublicPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # --- Always emitted. No defaults: a missing one is a producer bug. ---
    schema_version: int
    producer_version: str
    generated_at: datetime
    days_covered: int
    active_days: int
    total_sessions: int
    total_minutes: float
    active_agents: list[str]
    favorite_model: str
    models: list[PublicModel]

    # --- Privacy-gated. None means "not shared", never "zero". ---
    daily: list[PublicDaily] | None = None
    hourly: list[int] | None = None
    peak_hour: int | None = None
    total_messages: int | None = None
    total_tokens: TokenUsage | None = None
    projects: list[PublicProject] | None = None


@dataclass(frozen=True)
class Requirement:
    """Data a chart cannot be drawn without, and the flag that shares it."""

    key: str
    label: str
    flag: str

    def satisfied_by(self, payload: PublicPayload) -> bool:
        if self.key == "model_tokens":
            # Models are always shared; their token counts are not. An all-None
            # token list would otherwise render as a chart of zero-width bars.
            return not payload.models or any(
                item.tokens is not None for item in payload.models
            )
        return getattr(payload, self.key) is not None


DAILY_ACTIVITY = Requirement("daily", "daily activity", "--daily-activity")
TIME_PATTERNS = Requirement("hourly", "hourly time patterns", "--time-patterns")
PROJECT_ALIASES = Requirement("projects", "project aliases", "--project-aliases")
TOKEN_COUNTS = Requirement("model_tokens", "token counts", "--token-counts")


def load_public_payload(text: str, *, reader_version: str = __version__) -> PublicPayload:
    """Parse a published payload, failing loudly on any version skew."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PayloadError(f"payload is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise PayloadError("payload must be a JSON object")

    version = raw.get("schema_version")
    if version is None:
        raise PayloadError(
            "payload carries no schema_version, so it was written by "
            f"vibe-clock < 1.4.0 while this is {reader_version}. " + _UPGRADE_PRODUCER
        )
    if not isinstance(version, int) or isinstance(version, bool):
        raise PayloadError(f"payload schema_version must be an integer, got {version!r}")

    producer = raw.get("producer_version", "an unknown version")
    skew = (
        f"payload written by vibe-clock {producer} (schema v{version}), "
        f"this is {reader_version} (schema v{SCHEMA_VERSION})"
    )
    if version < MIN_READABLE_SCHEMA:
        raise PayloadError(f"{skew} — {_UPGRADE_PRODUCER}")
    if version > SCHEMA_VERSION:
        raise PayloadError(f"{skew} — {_UPGRADE_READER}")

    try:
        return PublicPayload.model_validate(raw)
    except ValidationError as exc:
        raise PayloadError(
            f"{skew}, and the payload does not match that schema. Every change to "
            f"the key set must bump SCHEMA_VERSION.\n{exc}"
        ) from exc


def to_agent_stats(payload: PublicPayload) -> AgentStats:
    """Adapt a payload to the model the SVG renderers take.

    Unshared fields keep `AgentStats`' defaults, which is safe only because
    `missing_requirements` refuses any chart that would read them.
    """
    return AgentStats(
        generated_at=payload.generated_at,
        days_covered=payload.days_covered,
        active_days=payload.active_days,
        total_sessions=payload.total_sessions,
        total_minutes=payload.total_minutes,
        total_messages=payload.total_messages or 0,
        total_tokens=payload.total_tokens or TokenUsage(),
        active_agents=list(payload.active_agents),
        favorite_model=payload.favorite_model,
        peak_hour=payload.peak_hour or 0,
        hourly=list(payload.hourly) if payload.hourly is not None else [0] * 24,
        daily=[
            DailyActivity(
                date=item.date,
                session_count=item.session_count,
                message_count=item.message_count or 0,
                tokens=item.tokens or TokenUsage(),
            )
            for item in payload.daily or []
        ],
        models=[
            ModelBreakdown(
                model=item.model,
                session_count=item.session_count,
                message_count=item.message_count or 0,
                tokens=item.tokens or TokenUsage(),
            )
            for item in payload.models
        ],
        projects=[
            ProjectBreakdown(
                project=item.project,
                agent=item.agent,
                session_count=item.session_count,
                tokens=item.tokens or TokenUsage(),
            )
            for item in payload.projects or []
        ],
    )


def missing_requirements(
    payload: PublicPayload, requirements: tuple[Requirement, ...]
) -> list[Requirement]:
    return [req for req in requirements if not req.satisfied_by(payload)]
