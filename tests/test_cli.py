"""CLI privacy and public-sharing behavior."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from click.testing import CliRunner

from vibe_clock.cli import init, push, render, schedule, share, unshare
from vibe_clock.config import Config
from vibe_clock.models import AgentStats, Session, TokenUsage
from vibe_clock.payload import SCHEMA_VERSION


def _render_locally(monkeypatch, tmp_path, config, *args):
    """Run `vibe-clock render` (no --from-json) over one private session."""
    session = Session(
        session_id="local",
        agent="codex",
        # Yesterday: the public window ends at the last complete UTC midnight,
        # so today's activity is not published and must not be rendered either.
        start_time=datetime.now(timezone.utc) - timedelta(days=1, hours=2),
        end_time=datetime.now(timezone.utc) - timedelta(days=1, hours=1),
        model="gpt-private-model-unreleased",
        project="/Volumes/work/AcmeCorp-nda-project",
        message_count=4,
        tokens=TokenUsage(input_tokens=1000, output_tokens=500),
    )

    class Collector:
        agent_name = "codex"

        def collect(self, days: int = 365) -> list[Session]:
            return [session]

    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: config)
    monkeypatch.setattr("vibe_clock.cli.get_collectors", lambda _config: [Collector()])
    return CliRunner().invoke(render, [*args, "--output", str(tmp_path)])


def test_local_render_cannot_leak_a_private_project_or_model(monkeypatch, tmp_path) -> None:
    """`render` without --from-json used to bypass the sanitizer entirely.

    It handed raw `AgentStats` to the renderers, so `bars` drew the working
    directory as a label and `card`/`donut`/`token_bars` printed the raw model
    ID — into files the README tells you to commit to a public profile repo.
    """
    config = Config(default_days=30)
    config.privacy.share_token_counts = True
    config.privacy.share_project_aliases = True

    result = _render_locally(
        monkeypatch, tmp_path, config, "--type", "token_bars,bars,card,donut"
    )

    assert result.exit_code == 0, result.output
    for svg_path in tmp_path.glob("*.svg"):
        svg = svg_path.read_text()
        assert "gpt-private-model-unreleased" not in svg, svg_path.name
        assert "AcmeCorp" not in svg, svg_path.name
        assert "/Volumes" not in svg, svg_path.name

    assert "OpenAI" in (tmp_path / "vibe-clock-donut.svg").read_text()
    assert "Project A" in (tmp_path / "vibe-clock-bars.svg").read_text()
    assert "No token data" not in (tmp_path / "vibe-clock-token-bars.svg").read_text()


def test_local_render_refuses_a_chart_whose_data_is_not_published(
    monkeypatch, tmp_path
) -> None:
    """The README promises this for every render, not only the CI one."""
    config = Config(default_days=30)  # every share flag off

    result = _render_locally(monkeypatch, tmp_path, config, "--type", "bars")

    assert result.exit_code != 0
    assert "--project-aliases" in result.output
    assert not list(tmp_path.glob("*.svg"))


def _write_payload(tmp_path, **overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "producer_version": "1.5.0",
        "generated_at": "2026-02-24T00:00:00Z",
        "days_covered": 7,
        "active_days": 5,
        "total_sessions": 12,
        "total_minutes": 321.0,
        "active_agents": ["claude_code"],
        "favorite_model": "Claude",
        "models": [{"model": "Claude", "session_count": 12}],
    }
    payload.update(overrides)
    path = tmp_path / "vibe-clock-data.json"
    path.write_text(json.dumps(payload))
    return path


def test_render_from_json_refuses_a_payload_written_by_an_older_vibe_clock(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: Config())
    # A v1.3.0-shaped document: no schema_version, and no active_days at all.
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"total_sessions": 1294, "days_covered": 30}))

    result = CliRunner().invoke(
        render, ["--from-json", str(legacy), "--output", str(tmp_path)]
    )

    assert result.exit_code == 1
    assert "no schema_version" in result.output
    assert "vibe-clock push" in result.output
    assert not (tmp_path / "vibe-clock-card.svg").exists()


def test_render_from_json_refuses_charts_whose_data_was_not_shared(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: Config())
    path = _write_payload(tmp_path)

    result = CliRunner().invoke(
        render,
        ["--from-json", str(path), "--type", "heatmap", "--output", str(tmp_path)],
    )

    assert result.exit_code == 1
    assert "daily activity" in result.output
    assert "--daily-activity" in result.output
    assert not (tmp_path / "vibe-clock-heatmap.svg").exists()


def test_render_from_json_draws_the_card_from_always_shared_fields(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: Config())
    path = _write_payload(tmp_path)

    result = CliRunner().invoke(
        render,
        ["--from-json", str(path), "--type", "card", "--output", str(tmp_path)],
    )

    assert result.exit_code == 0
    svg = (tmp_path / "vibe-clock-card.svg").read_text()
    assert ">5</text>" in svg  # active days, not a silent 0
    assert "5.3 hrs" in svg  # 321 minutes of active time
    assert "Active Agents" not in svg


def test_init_detects_gemini_cli(monkeypatch, tmp_path) -> None:
    config = Config()
    config.paths.claude_code = tmp_path / "missing-claude"
    config.paths.codex = tmp_path / "missing-codex"
    config.paths.gemini_cli = tmp_path / "gemini"
    config.paths.opencode = tmp_path / "missing-opencode"
    config.paths.gemini_cli.mkdir()
    saves = []

    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: config)
    monkeypatch.setattr("vibe_clock.cli.click.prompt", lambda *args, **kwargs: "")
    monkeypatch.setattr("vibe_clock.cli.save_config", lambda current: saves.append(current))

    result = CliRunner().invoke(init)

    assert result.exit_code == 0
    assert saves[-1].enabled_agents == ["gemini_cli"]


def test_push_requires_explicit_public_opt_in(monkeypatch) -> None:
    config = Config()
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: config)
    monkeypatch.setattr(
        "vibe_clock.cli._collect_public_stats",
        lambda _config: AgentStats(days_covered=7),
    )

    def fail_publish(_config: Config, _stats: AgentStats) -> None:
        raise AssertionError("disabled sharing must not publish")

    monkeypatch.setattr("vibe_clock.cli._publish_public_stats", fail_publish)

    result = CliRunner().invoke(push)

    assert result.exit_code == 0
    assert "Public sharing is disabled" in result.output


def test_share_enables_future_updates_after_confirmation(monkeypatch) -> None:
    config = Config()
    saves = []
    publishes = []
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: config)
    monkeypatch.setattr(
        "vibe_clock.cli._collect_public_stats",
        lambda _config: AgentStats(days_covered=7),
    )
    monkeypatch.setattr(
        "vibe_clock.cli._publish_public_stats",
        lambda current, _stats: publishes.append(current.privacy.public_sharing_enabled),
    )
    monkeypatch.setattr("vibe_clock.cli.save_config", lambda current: saves.append(current))

    result = CliRunner().invoke(share, ["--yes"])

    assert result.exit_code == 0
    assert publishes == [True]
    assert saves[-1].privacy.public_sharing_enabled is True
    assert saves[-1].privacy.public_days == 7


def test_share_requires_legacy_history_cleanup(monkeypatch) -> None:
    config = Config()
    config.github.gist_id = "legacy-gist"
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: config)

    result = CliRunner().invoke(share, ["--yes"])

    assert result.exit_code == 0
    assert "legacy public Gist" in result.output
    assert config.privacy.public_sharing_enabled is False


def test_unshare_deletes_gist_and_disables_updates(monkeypatch) -> None:
    config = Config()
    config.github.token = "configured"
    config.github.gist_id = "gist-id"
    config.privacy.public_sharing_enabled = True
    saves = []
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: config)
    monkeypatch.setattr("vibe_clock.cli.save_config", lambda current: saves.append(current))
    monkeypatch.setattr(
        "httpx.delete",
        lambda *args, **kwargs: SimpleNamespace(status_code=204, text=""),
    )

    result = CliRunner().invoke(unshare, ["--yes"])

    assert result.exit_code == 0
    assert saves[-1].github.gist_id == ""
    assert saves[-1].privacy.public_sharing_enabled is False


def test_unshare_clears_local_state_when_gist_is_already_gone(monkeypatch) -> None:
    config = Config()
    config.github.token = "configured"
    config.github.gist_id = "missing-gist"
    config.privacy.public_sharing_enabled = True
    saves = []
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: config)
    monkeypatch.setattr("vibe_clock.cli.save_config", lambda current: saves.append(current))
    monkeypatch.setattr(
        "httpx.delete",
        lambda *args, **kwargs: SimpleNamespace(status_code=404, text="Not Found"),
    )

    result = CliRunner().invoke(unshare, ["--yes"])

    assert result.exit_code == 0
    assert saves[-1].github.gist_id == ""
    assert saves[-1].privacy.public_sharing_enabled is False


def test_schedule_rejects_out_of_range_time(monkeypatch) -> None:
    config = Config()
    config.github.token = "configured"
    config.privacy.public_sharing_enabled = True
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: config)

    def fail_scheduler():
        raise AssertionError("invalid time must be rejected before scheduler selection")

    monkeypatch.setattr("vibe_clock.scheduler.get_scheduler", fail_scheduler)

    result = CliRunner().invoke(schedule, ["--time", "99:99"])

    assert result.exit_code == 1
    assert "Invalid time format" in result.output
