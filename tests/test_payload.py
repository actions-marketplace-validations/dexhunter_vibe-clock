"""The public payload must fail loudly on version skew, never default silently."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from vibe_clock.aggregator import aggregate
from vibe_clock.config import Config
from vibe_clock.models import Session, TokenUsage
from vibe_clock.payload import (
    MIN_READABLE_SCHEMA,
    SCHEMA_VERSION,
    PayloadError,
    PublicPayload,
    load_public_payload,
    to_agent_stats,
)
from vibe_clock.sanitizer import public_payload

_WINDOW_END = datetime.fromisoformat("2026-03-01T00:00:00+00:00")

# Every key the producer emits unconditionally. Deleting any one of them means
# the producer is a different version than it claims to be.
REQUIRED_KEYS = {
    name
    for name, field in PublicPayload.model_fields.items()
    if field.is_required()
}


def _full_config() -> Config:
    config = Config(default_days=30)
    config.privacy.share_daily_activity = True
    config.privacy.share_message_counts = True
    config.privacy.share_token_counts = True
    config.privacy.share_time_patterns = True
    config.privacy.share_project_aliases = True
    return config


def _stats(config: Config):
    session = Session(
        session_id="s1",
        agent="claude_code",
        model="claude-test",
        project="/synthetic/project",
        start_time=datetime.fromisoformat("2026-02-10T10:00:00+00:00"),
        end_time=datetime.fromisoformat("2026-02-10T10:30:00+00:00"),
        message_count=10,
        tokens=TokenUsage(input_tokens=1000, output_tokens=500),
    )
    return aggregate([session], config, end_at=_WINDOW_END)


def test_required_keys_are_the_unconditional_ones() -> None:
    assert REQUIRED_KEYS == {
        "schema_version",
        "producer_version",
        "generated_at",
        "days_covered",
        "active_days",
        "total_sessions",
        "total_minutes",
        "active_agents",
        "favorite_model",
        "models",
    }


@pytest.mark.parametrize("key", sorted(REQUIRED_KEYS))
def test_a_missing_required_key_is_rejected(key: str) -> None:
    """This is the "Active Days: 0" regression: absent must not mean zero."""
    payload = public_payload(_stats(_full_config()), _full_config())
    del payload[key]

    with pytest.raises(PayloadError):
        load_public_payload(json.dumps(payload))


def test_every_emitted_field_survives_the_round_trip() -> None:
    """A field on the contract that the serializer forgets would fail here."""
    config = _full_config()
    payload = public_payload(_stats(config), config)

    loaded = load_public_payload(json.dumps(payload))

    assert loaded.model_dump(mode="json", exclude_none=True) == payload
    assert set(payload) >= REQUIRED_KEYS


def test_default_share_omits_unshared_fields_rather_than_zeroing_them() -> None:
    config = Config(default_days=30)
    payload = public_payload(_stats(config), config)

    loaded = load_public_payload(json.dumps(payload))

    assert "daily" not in payload
    assert loaded.daily is None  # "not shared", not "no activity"
    assert loaded.hourly is None
    assert loaded.total_tokens is None


def test_legacy_payload_without_schema_version_is_rejected() -> None:
    """A v1.3.0-shaped document: no schema_version, no active_days."""
    legacy = {
        "generated_at": "2026-02-24T00:00:00Z",
        "days_covered": 30,
        "total_sessions": 1294,
        "total_messages": 118564,
        "total_minutes": 106237.0,
        "active_agents": ["claude_code", "codex"],
        "favorite_model": "gpt-5.1-codex",
        "peak_hour": 14,
        "longest_session_minutes": 14882.0,
        "hourly": [0] * 24,
        "daily": [],
        "models": [],
        "projects": [],
    }

    with pytest.raises(PayloadError) as excinfo:
        load_public_payload(json.dumps(legacy), reader_version="1.4.1")

    message = str(excinfo.value)
    assert "no schema_version" in message
    assert "1.4.1" in message
    assert "vibe-clock push" in message


def test_older_schema_names_both_versions_and_tells_you_to_upgrade_the_pusher() -> None:
    old = {"schema_version": MIN_READABLE_SCHEMA - 1, "producer_version": "1.4.1"}

    with pytest.raises(PayloadError) as excinfo:
        load_public_payload(json.dumps(old), reader_version="9.9.9")

    message = str(excinfo.value)
    assert "written by vibe-clock 1.4.1" in message
    assert "this is 9.9.9" in message
    assert "vibe-clock push" in message


def test_newer_schema_tells_you_to_upgrade_the_reader() -> None:
    future = {"schema_version": SCHEMA_VERSION + 1, "producer_version": "99.0.0"}

    with pytest.raises(PayloadError) as excinfo:
        load_public_payload(json.dumps(future), reader_version="1.4.1")

    message = str(excinfo.value)
    assert "written by vibe-clock 99.0.0" in message
    assert "workflow" in message


def test_unknown_key_is_rejected_rather_than_dropped() -> None:
    config = _full_config()
    payload = public_payload(_stats(config), config)
    payload["invented_field"] = 1

    with pytest.raises(PayloadError) as excinfo:
        load_public_payload(json.dumps(payload))

    assert "SCHEMA_VERSION" in str(excinfo.value)


def test_to_agent_stats_carries_the_card_fields() -> None:
    config = _full_config()
    stats = _stats(config)
    payload = public_payload(stats, config)

    rendered = to_agent_stats(load_public_payload(json.dumps(payload)))

    assert rendered.active_days == stats.active_days == 1
    assert rendered.total_sessions == stats.total_sessions
    assert rendered.total_minutes == stats.total_minutes == 30.0
    assert rendered.generated_at == stats.generated_at.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
