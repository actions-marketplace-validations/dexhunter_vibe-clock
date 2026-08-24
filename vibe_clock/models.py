"""Pydantic models for vibe-clock data."""

from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .intervals import Interval, merge_intervals, total_minutes


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


class Session(BaseModel):
    session_id: str
    agent: str  # "claude_code", "codex", "opencode"
    start_time: datetime
    end_time: datetime | None = None
    model: str = "unknown"
    project: str = "unknown"
    message_count: int = 0
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    model_tokens: dict[str, TokenUsage] = Field(default_factory=dict)
    # Stretches during which this session was actually emitting events. A
    # collector that can see per-event timestamps fills this in; anything else
    # falls back to the single [start_time, end_time] span below.
    active_intervals: list[Interval] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_intervals(self) -> "Session":
        intervals = self.active_intervals or [
            (self.start_time, self.end_time or self.start_time)
        ]
        self.active_intervals = merge_intervals(intervals)
        return self

    @property
    def duration_minutes(self) -> float:
        """Active minutes — the summed active stretches, never the raw span."""
        return total_minutes(self.active_intervals)


class DailyActivity(BaseModel):
    date: date
    session_count: int = 0
    message_count: int = 0
    total_minutes: float = 0.0
    tokens: TokenUsage = Field(default_factory=TokenUsage)


class ModelBreakdown(BaseModel):
    model: str
    session_count: int = 0
    message_count: int = 0
    total_minutes: float = 0.0
    tokens: TokenUsage = Field(default_factory=TokenUsage)


class ProjectBreakdown(BaseModel):
    project: str
    agent: str
    session_count: int = 0
    total_minutes: float = 0.0
    tokens: TokenUsage = Field(default_factory=TokenUsage)


class AgentStats(BaseModel):
    """Top-level aggregated stats, internal to one vibe-clock version.

    The published wire format is `payload.PublicPayload`, not this model: every
    field here has a default, so validating foreign JSON against it would turn
    a missing field into a plausible-looking zero. Unknown keys are rejected so
    a renamed field is caught here too.
    """

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    days_covered: int = 30
    active_days: int = 0
    total_sessions: int = 0
    total_messages: int = 0
    total_minutes: float = 0.0
    total_tokens: TokenUsage = Field(default_factory=TokenUsage)
    active_agents: list[str] = Field(default_factory=list)
    favorite_model: str = ""
    peak_hour: int = 0  # 0-23
    # Longest uninterrupted active stretch, not the longest session: a session
    # can be a CLI process that stayed open for weeks.
    longest_stretch_minutes: float = 0.0
    hourly: list[int] = Field(default_factory=lambda: [0] * 24)  # sessions per hour 0-23
    daily: list[DailyActivity] = Field(default_factory=list)
    models: list[ModelBreakdown] = Field(default_factory=list)
    projects: list[ProjectBreakdown] = Field(default_factory=list)
