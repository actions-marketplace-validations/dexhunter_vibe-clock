"""Tests for aggregator and sanitizer."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from vibe_clock.aggregator import aggregate
from vibe_clock.config import Config
from vibe_clock.intervals import intervals_from_timestamps
from vibe_clock.models import AgentStats, Session, TokenUsage
from vibe_clock.payload import SCHEMA_VERSION, load_public_payload
from vibe_clock.sanitizer import preview, public_payload, sanitize


_WINDOW_END = datetime.fromisoformat("2026-03-01T00:00:00+00:00")


def _make_session(
    sid: str = "s1",
    agent: str = "claude_code",
    model: str = "claude-opus-4-6",
    project: str = "/home/user/myproject",
    start: str = "2026-02-10T10:00:00Z",
    end: str = "2026-02-10T10:30:00Z",
    messages: int = 10,
    input_tok: int = 1000,
    output_tok: int = 500,
) -> Session:
    return Session(
        session_id=sid,
        agent=agent,
        model=model,
        project=project,
        start_time=datetime.fromisoformat(start.replace("Z", "+00:00")),
        end_time=datetime.fromisoformat(end.replace("Z", "+00:00")),
        message_count=messages,
        tokens=TokenUsage(input_tokens=input_tok, output_tokens=output_tok),
    )
def test_aggregate_basic() -> None:
    sessions = [
        _make_session(sid="s1", start="2026-02-10T10:00:00Z", end="2026-02-10T10:30:00Z"),
        _make_session(sid="s2", agent="codex", model="gpt-5.1", start="2026-02-10T14:00:00Z", end="2026-02-10T14:45:00Z"),
        _make_session(sid="s3", start="2026-02-11T09:00:00Z", end="2026-02-11T09:10:00Z", messages=5),
    ]

    config = Config(default_days=30)
    stats = aggregate(sessions, config, end_at=_WINDOW_END)

    assert stats.total_sessions == 3
    assert stats.total_messages == 25  # 10 + 10 + 5
    assert stats.active_days == 2
    assert len(stats.daily) == 2  # Feb 10, Feb 11
    assert len(stats.models) == 2  # claude-opus-4-6, gpt-5.1
    assert set(stats.active_agents) == {"claude_code", "codex"}


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_long_running_session_counts_active_time_not_span() -> None:
    """A session open for days bills only the minutes it was actually working."""
    # Three bursts of work spread over four days, with multi-hour silences
    # between them. Timestamps are two minutes apart, i.e. inside the idle
    # threshold, so each burst is one continuous stretch.
    bursts = [
        ("2026-02-10T09:00:00Z", "2026-02-10T09:30:00Z"),  # 30 min
        ("2026-02-12T14:00:00Z", "2026-02-12T14:20:00Z"),  # 20 min
        ("2026-02-14T22:00:00Z", "2026-02-14T22:10:00Z"),  # 10 min
    ]
    timestamps: list[datetime] = []
    for start, end in bursts:
        cursor, stop = _at(start), _at(end)
        while cursor <= stop:
            timestamps.append(cursor)
            cursor += timedelta(minutes=2)

    session = Session(
        session_id="daemon",
        agent="codex",
        start_time=timestamps[0],
        end_time=timestamps[-1],
        model="gpt-5.1",
        project="proj",
        active_intervals=intervals_from_timestamps(timestamps),
    )

    span_minutes = (timestamps[-1] - timestamps[0]).total_seconds() / 60
    assert span_minutes > 4 * 1440  # the old measurement: over four days

    stats = aggregate([session], Config(default_days=30), end_at=_WINDOW_END)

    assert session.duration_minutes == 60.0  # 30 + 20 + 10
    assert stats.total_minutes == 60.0
    assert stats.longest_stretch_minutes == 30.0
    assert stats.active_days == 3
    assert {d.date.isoformat(): d.total_minutes for d in stats.daily} == {
        "2026-02-10": 30.0,
        "2026-02-12": 20.0,
        "2026-02-14": 10.0,
    }


def test_concurrent_sessions_share_wall_clock_minutes() -> None:
    """Two agents running at once cost one wall-clock minute, not two."""
    overlapping = [
        _make_session(sid="a", start="2026-02-10T10:00:00Z", end="2026-02-10T11:00:00Z"),
        _make_session(
            sid="b",
            agent="codex",
            start="2026-02-10T10:30:00Z",
            end="2026-02-10T11:30:00Z",
        ),
    ]

    stats = aggregate(overlapping, Config(default_days=30), end_at=_WINDOW_END)

    assert sum(s.duration_minutes for s in overlapping) == 120.0
    assert stats.total_minutes == 90.0
    assert stats.daily[0].total_minutes == 90.0


def test_no_day_can_exceed_twenty_four_hours() -> None:
    sessions = [
        _make_session(
            sid=f"s{index}",
            start="2026-02-10T00:00:00Z",
            end="2026-02-10T23:59:00Z",
        )
        for index in range(5)
    ]

    stats = aggregate(sessions, Config(default_days=30), end_at=_WINDOW_END)

    assert max(d.total_minutes for d in stats.daily) <= 1440


def test_session_crossing_midnight_splits_across_days() -> None:
    session = _make_session(
        start="2026-02-10T23:00:00Z", end="2026-02-11T01:00:00Z"
    )

    stats = aggregate([session], Config(default_days=30), end_at=_WINDOW_END)

    assert {d.date.isoformat(): d.total_minutes for d in stats.daily} == {
        "2026-02-10": 60.0,
        "2026-02-11": 60.0,
    }
    assert stats.active_days == 2


def test_session_starting_before_the_window_still_counts_inside_it() -> None:
    """Clipping keeps in-window minutes that a start-time filter would drop."""
    session = _make_session(
        start="2026-01-29T22:00:00Z", end="2026-01-30T02:00:00Z"
    )
    config = Config(default_days=30)

    stats = aggregate([session], config, end_at=_WINDOW_END)

    # Window opens 2026-01-30T00:00Z, so only the last two hours count.
    assert stats.total_sessions == 1
    assert stats.total_minutes == 120.0


def test_aggregate_filters_old_sessions() -> None:
    old = _make_session(start="2025-01-01T10:00:00Z", end="2025-01-01T10:30:00Z")
    recent = _make_session(sid="s2", start="2026-02-10T10:00:00Z", end="2026-02-10T10:30:00Z")

    config = Config(default_days=30)
    stats = aggregate([old, recent], config, end_at=_WINDOW_END)
    assert stats.total_sessions == 1


def test_aggregate_supports_complete_day_window() -> None:
    sessions = [
        _make_session(
            sid="inside",
            start="2026-02-22T00:00:00Z",
            end="2026-02-22T00:30:00Z",
        ),
        _make_session(
            sid="today",
            start="2026-03-01T00:00:00Z",
            end="2026-03-01T00:30:00Z",
        ),
    ]
    config = Config(default_days=7)

    stats = aggregate(sessions, config, end_at=_WINDOW_END)

    assert stats.total_sessions == 1
    assert stats.daily[0].date.isoformat() == "2026-02-22"


def test_aggregate_exclude_projects() -> None:
    sessions = [
        _make_session(sid="s1", project="/home/user/secret-project"),
        _make_session(sid="s2", project="/home/user/public-project"),
    ]

    config = Config(default_days=30)
    config.privacy.exclude_projects = ["*/secret-*"]
    stats = aggregate(sessions, config, end_at=_WINDOW_END)
    assert stats.total_sessions == 1


def test_aggregate_peak_hour() -> None:
    sessions = [
        _make_session(sid="s1", start="2026-02-10T14:00:00Z", end="2026-02-10T14:30:00Z"),
        _make_session(sid="s2", start="2026-02-10T14:30:00Z", end="2026-02-10T15:00:00Z"),
        _make_session(sid="s3", start="2026-02-10T09:00:00Z", end="2026-02-10T09:30:00Z"),
    ]
    config = Config(default_days=30)
    stats = aggregate(sessions, config, end_at=_WINDOW_END)
    assert stats.peak_hour == 14


def test_aggregate_preserves_per_model_token_usage() -> None:
    session = _make_session(model="claude-test", input_tok=150, output_tok=0)
    session.model_tokens = {
        "claude-test": TokenUsage(input_tokens=100),
        "gpt-test": TokenUsage(input_tokens=50),
    }

    stats = aggregate([session], Config(default_days=30), end_at=_WINDOW_END)
    models = {item.model: item for item in stats.models}

    assert models["claude-test"].tokens.total == 100
    assert models["gpt-test"].tokens.total == 50
    assert models["claude-test"].session_count == 1
    assert models["gpt-test"].session_count == 0


def test_sanitize_hides_projects_by_default() -> None:
    sessions = [
        _make_session(sid="s1", project="/home/user/project-alpha"),
        _make_session(sid="s2", project="/home/user/project-beta"),
        _make_session(sid="s3", project="/home/user/project-alpha"),
    ]

    config = Config(default_days=30)
    stats = aggregate(sessions, config, end_at=_WINDOW_END)
    safe = sanitize(stats, config)

    assert safe.projects == []


def test_sanitize_normalizes_model_names() -> None:
    sessions = [
        _make_session(model="gpt-5.6-private-alias", project="safe-name"),
        _make_session(sid="s2", model="claude-internal", project="safe-name"),
    ]
    config = Config(default_days=30)
    stats = aggregate(sessions, config, end_at=_WINDOW_END)
    safe = sanitize(stats, config)

    assert safe.favorite_model in {"OpenAI", "Claude"}
    assert {item.model for item in safe.models} == {"OpenAI", "Claude"}
    assert "private-alias" not in safe.model_dump_json()
    assert "internal" not in safe.model_dump_json()


def test_sanitize_keeps_empty_favorite_model_empty() -> None:
    config = Config(default_days=30)

    safe = sanitize(AgentStats(), config)

    assert safe.favorite_model == ""


def test_public_payload_is_allowlisted() -> None:
    sessions = [
        _make_session(
            project="/home/user/secret-project",
            model="gpt-5.6-private-alias",
        )
    ]
    config = Config(default_days=30)
    stats = aggregate(sessions, config, end_at=_WINDOW_END)

    payload = public_payload(stats, config)
    serialized = json.dumps(payload)

    assert set(payload) == {
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
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["favorite_model"] == "OpenAI"
    assert set(payload["models"][0]) == {"model", "session_count"}
    assert "secret-project" not in serialized
    assert "private-alias" not in serialized
    assert "total_tokens" not in payload
    assert "daily" not in payload
    assert "hourly" not in payload
    loaded = load_public_payload(serialized)
    assert loaded.total_sessions == 1
    assert loaded.models[0].model == "OpenAI"


def test_preview_contains_the_exact_public_payload() -> None:
    sessions = [_make_session(model="gpt-private")]
    config = Config(default_days=30)
    config.privacy.share_token_counts = True
    stats = aggregate(sessions, config, end_at=_WINDOW_END)

    output = preview(stats, config)
    rendered_payload = json.loads(output.split("\n\n", 1)[1])

    assert rendered_payload == public_payload(stats, config)


def test_public_payload_optional_fields_are_explicit() -> None:
    sessions = [_make_session(project="/home/user/secret-project")]
    config = Config(default_days=30)
    config.privacy.share_daily_activity = True
    config.privacy.share_message_counts = True
    config.privacy.share_token_counts = True
    config.privacy.share_time_patterns = True
    config.privacy.share_project_aliases = True
    stats = aggregate(sessions, config, end_at=_WINDOW_END)

    payload = public_payload(stats, config)

    assert payload["total_messages"] == 10
    assert payload["total_tokens"]["input_tokens"] == 1000
    assert payload["daily"][0]["date"] == "2026-02-10"
    assert len(payload["hourly"]) == 24
    assert payload["projects"][0]["project"] == "Project A"
    assert "total_minutes" not in payload["daily"][0]
    assert "total_minutes" not in payload["models"][0]
    assert "total_minutes" not in payload["projects"][0]
    assert "secret-project" not in json.dumps(payload)


def test_exclude_projects_accepts_a_plain_substring() -> None:
    """The documented form used to exclude nothing.

    Matching was glob-only and anchored, so `exclude_projects = ["AcmeCorp"]` —
    exactly what the config comment told people to write — matched only a
    project named precisely `AcmeCorp` and silently published the rest. This is
    the only escape hatch for keeping a client out of your public stats, so
    silence is the worst possible answer.
    """
    sessions = [
        _make_session(sid="s1", project="/work/clients/AcmeCorp/nda-project"),
        _make_session(sid="s2", project="/work/public-project"),
    ]
    config = Config(default_days=30)
    config.privacy.exclude_projects = ["AcmeCorp"]

    assert aggregate(sessions, config, end_at=_WINDOW_END).total_sessions == 1


def test_exclude_projects_ignores_case() -> None:
    sessions = [_make_session(sid="s1", project="/work/ACMECORP-PRIVATE-REPO")]
    config = Config(default_days=30)
    config.privacy.exclude_projects = ["acmecorp"]

    assert aggregate(sessions, config, end_at=_WINDOW_END).total_sessions == 0


def test_exclude_projects_still_accepts_globs() -> None:
    sessions = [
        _make_session(sid="s1", project="/home/user/secret-project"),
        _make_session(sid="s2", project="/home/user/public-project"),
    ]
    config = Config(default_days=30)
    config.privacy.exclude_projects = ["*/secret-*"]

    assert aggregate(sessions, config, end_at=_WINDOW_END).total_sessions == 1


def test_a_session_running_past_midnight_counts_on_both_days() -> None:
    """A day full of activity must not show up blank.

    `daily[].session_count` used to be credited only to the day a session first
    became active, while its minutes were split across midnight. The heatmap and
    the weekly chart key off the session count, so a day holding hours of
    spill-over work rendered as an empty cell.
    """
    sessions = [
        _make_session(
            sid="overnight",
            start="2026-02-10T23:00:00Z",
            end="2026-02-11T02:00:00Z",
        )
    ]
    config = Config(default_days=30)

    daily = {d.date.isoformat(): d for d in aggregate(sessions, config, end_at=_WINDOW_END).daily}

    assert daily["2026-02-10"].session_count == 1
    assert daily["2026-02-11"].session_count == 1
    assert daily["2026-02-10"].total_minutes == 60.0
    assert daily["2026-02-11"].total_minutes == 120.0
    # Messages have no per-day split, so they are not counted twice.
    assert daily["2026-02-10"].message_count == 10
    assert daily["2026-02-11"].message_count == 0


def test_no_day_has_minutes_without_sessions_or_sessions_without_minutes() -> None:
    sessions = [
        _make_session(sid="a", start="2026-02-10T23:30:00Z", end="2026-02-11T00:30:00Z"),
        _make_session(sid="b", start="2026-02-13T09:00:00Z", end="2026-02-13T09:45:00Z"),
    ]
    stats = aggregate(sessions, Config(default_days=30), end_at=_WINDOW_END)

    for day in stats.daily:
        assert (day.total_minutes > 0) == (day.session_count > 0), day
    assert stats.active_days == len(stats.daily)


def test_pii_guard_does_not_fire_on_the_tools_own_constants(monkeypatch) -> None:
    """A user whose Unix login is `code` or `claude` could not publish at all.

    The guard scanned the whole serialized payload for the login name with
    non-letter boundaries, and `active_agents` carries the constant
    `claude_code` — whose boundaries are underscores. `push`, `share` and
    `setup` all died with an unhandled traceback blaming a leak that had not
    happened, with no documented workaround.
    """
    from vibe_clock import sanitizer

    sessions = [_make_session(sid="s1", agent="claude_code")]
    stats = aggregate(sessions, Config(default_days=30), end_at=_WINDOW_END)

    for login in ("code", "claude", "dex"):
        monkeypatch.setattr(sanitizer, "_USERNAME", login)
        payload = sanitizer.public_payload(stats, Config(default_days=30))
        assert payload["active_agents"] == ["claude_code"]


def test_pii_guard_still_fires_when_a_raw_name_reaches_the_payload(monkeypatch) -> None:
    """It is a backstop against a future bug, so it must still catch one."""
    import pytest

    from vibe_clock import sanitizer

    monkeypatch.setattr(sanitizer, "_USERNAME", "dex")
    monkeypatch.setattr(sanitizer, "_model_family", lambda model: model)

    stats = aggregate(
        [_make_session(sid="s1", model="private-dex-model")],
        Config(default_days=30),
        end_at=_WINDOW_END,
    )

    with pytest.raises(ValueError, match="username"):
        sanitizer.public_payload(stats, Config(default_days=30))
