"""Build the allowlisted stats payload used for public sharing."""

from __future__ import annotations

import getpass
import json
import re
import string
from collections import defaultdict
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .config import Config
from .models import (
    AgentStats,
    DailyActivity,
    ModelBreakdown,
    ProjectBreakdown,
    TokenUsage,
)
from .payload import (
    SCHEMA_VERSION,
    PublicDaily,
    PublicModel,
    PublicPayload,
    PublicProject,
)

_HOME_DIR = str(Path.home())
_USERNAME = getpass.getuser()
_KNOWN_AGENTS = {"claude_code", "codex", "gemini_cli", "opencode"}


def sanitize(stats: AgentStats, config: Config) -> AgentStats:
    """Return a privacy-safe view containing only explicitly shareable data."""
    privacy = config.privacy

    data = AgentStats(
        generated_at=datetime.combine(
            stats.generated_at.date(), time.min, tzinfo=timezone.utc
        ),
        days_covered=stats.days_covered,
        active_days=stats.active_days,
        total_sessions=stats.total_sessions,
        total_minutes=stats.total_minutes,
        total_messages=stats.total_messages if privacy.share_message_counts else 0,
        total_tokens=(
            stats.total_tokens.model_copy(deep=True)
            if privacy.share_token_counts
            else TokenUsage()
        ),
        active_agents=sorted(set(stats.active_agents) & _KNOWN_AGENTS),
        favorite_model=_model_family(stats.favorite_model),
        peak_hour=stats.peak_hour if privacy.share_time_patterns else 0,
        hourly=list(stats.hourly) if privacy.share_time_patterns else [0] * 24,
        daily=_public_daily(stats, config),
        models=_public_models(stats, config),
        projects=_public_projects(stats, config),
    )

    _validate_no_pii(data)
    return data


def build_public_payload(stats: AgentStats, config: Config) -> PublicPayload:
    """Build the typed public payload from an allowlisted, sanitized view.

    The emitted key set is derived from `PublicPayload`, so a field cannot live
    on the contract and be forgotten by the serializer.
    """
    safe = sanitize(stats, config)
    privacy = config.privacy
    share_tokens = privacy.share_token_counts
    share_messages = privacy.share_message_counts

    return PublicPayload(
        schema_version=SCHEMA_VERSION,
        producer_version=__version__,
        generated_at=safe.generated_at,
        days_covered=safe.days_covered,
        active_days=safe.active_days,
        total_sessions=safe.total_sessions,
        total_minutes=safe.total_minutes,
        active_agents=list(safe.active_agents),
        favorite_model=safe.favorite_model,
        models=[
            PublicModel(
                model=item.model,
                session_count=item.session_count,
                message_count=item.message_count if share_messages else None,
                tokens=item.tokens if share_tokens else None,
            )
            for item in safe.models
        ],
        daily=(
            [
                PublicDaily(
                    date=item.date,
                    session_count=item.session_count,
                    message_count=item.message_count if share_messages else None,
                    tokens=item.tokens if share_tokens else None,
                )
                for item in safe.daily
            ]
            if privacy.share_daily_activity
            else None
        ),
        hourly=list(safe.hourly) if privacy.share_time_patterns else None,
        peak_hour=safe.peak_hour if privacy.share_time_patterns else None,
        total_messages=safe.total_messages if share_messages else None,
        total_tokens=safe.total_tokens if share_tokens else None,
        projects=(
            [
                PublicProject(
                    project=item.project,
                    agent=item.agent,
                    session_count=item.session_count,
                    tokens=item.tokens if share_tokens else None,
                )
                for item in safe.projects
            ]
            if privacy.share_project_aliases
            else None
        ),
    )


def public_payload(stats: AgentStats, config: Config) -> dict[str, Any]:
    """Serialize only fields enabled for the public profile.

    Unshared fields are omitted rather than sent as null or zero, so a reader
    can tell "not shared" from "no activity".
    """
    return build_public_payload(stats, config).model_dump(
        mode="json", exclude_none=True
    )


def _public_daily(stats: AgentStats, config: Config) -> list[DailyActivity]:
    if not config.privacy.share_daily_activity:
        return []
    return [
        DailyActivity(
            date=item.date,
            session_count=item.session_count,
            message_count=(
                item.message_count if config.privacy.share_message_counts else 0
            ),
            tokens=(
                item.tokens.model_copy(deep=True)
                if config.privacy.share_token_counts
                else TokenUsage()
            ),
        )
        for item in stats.daily
    ]


def _public_models(stats: AgentStats, config: Config) -> list[ModelBreakdown]:
    grouped: dict[str, _ModelAcc] = defaultdict(_ModelAcc)
    for item in stats.models:
        family = _model_family(item.model)
        acc = grouped[family]
        acc.session_count += item.session_count
        if config.privacy.share_message_counts:
            acc.message_count += item.message_count
        if config.privacy.share_token_counts:
            _add_tokens(acc.tokens, item.tokens)

    return sorted(
        [
            ModelBreakdown(
                model=family,
                session_count=acc.session_count,
                message_count=acc.message_count,
                tokens=acc.tokens,
            )
            for family, acc in grouped.items()
        ],
        key=lambda item: item.session_count,
        reverse=True,
    )


def _public_projects(stats: AgentStats, config: Config) -> list[ProjectBreakdown]:
    if not config.privacy.share_project_aliases:
        return []

    aliases: dict[str, str] = {}
    result = []
    for item in stats.projects:
        if item.project not in aliases:
            aliases[item.project] = _make_label(len(aliases))
        result.append(
            ProjectBreakdown(
                project=aliases[item.project],
                agent=item.agent if item.agent in _KNOWN_AGENTS else "unknown",
                session_count=item.session_count,
                tokens=(
                    item.tokens.model_copy(deep=True)
                    if config.privacy.share_token_counts
                    else TokenUsage()
                ),
            )
        )
    return result


def _model_family(model: str) -> str:
    """Map raw or private model identifiers to a small public family allowlist."""
    if not model:
        return ""
    value = model.casefold()
    if "claude" in value:
        return "Claude"
    if "gemini" in value:
        return "Gemini"
    if "gpt" in value or "codex" in value or "openai" in value:
        return "OpenAI"
    if "minimax" in value:
        return "MiniMax"
    if "deepseek" in value:
        return "DeepSeek"
    if "qwen" in value:
        return "Qwen"
    if "llama" in value or "meta" in value:
        return "Llama"
    if "mistral" in value or "mixtral" in value:
        return "Mistral"
    return "Other"


def _make_label(idx: int) -> str:
    """Generate Project A, Project B, ... Project AA, etc."""
    letters = string.ascii_uppercase
    if idx < 26:
        return f"Project {letters[idx]}"
    return f"Project {letters[idx // 26 - 1]}{letters[idx % 26]}"


def _validate_no_pii(stats: AgentStats) -> None:
    """Fail closed if a local identity or home path reaches the safe view."""
    json_str = stats.model_dump_json()
    blocked_values = {_HOME_DIR, f"/home/{_USERNAME}", f"/Users/{_USERNAME}"}
    for blocked in blocked_values:
        if blocked and blocked in json_str:
            raise ValueError(f"PII leak detected in public stats: {blocked!r}")

    if len(_USERNAME) >= 3:
        pattern = re.compile(rf"(?<![a-zA-Z]){re.escape(_USERNAME)}(?![a-zA-Z])")
        if pattern.search(json_str):
            raise ValueError("PII leak detected in public stats: local username")


def preview(stats: AgentStats, config: Config) -> str:
    """Human-readable preview of the exact allowlisted public payload."""
    payload = public_payload(stats, config)
    return "=== Exact public JSON ===\n\n" + json.dumps(payload, indent=2)


def _add_tokens(target: TokenUsage, source: TokenUsage) -> None:
    target.input_tokens += source.input_tokens
    target.output_tokens += source.output_tokens
    target.cache_read_tokens += source.cache_read_tokens
    target.cache_write_tokens += source.cache_write_tokens


class _ModelAcc:
    def __init__(self) -> None:
        self.session_count = 0
        self.message_count = 0
        self.tokens = TokenUsage()
