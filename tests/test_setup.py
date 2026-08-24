"""Onboarding: `vibe-clock setup`, the workflow template, and config safety.

All data here is synthetic. Nothing touches the network, `gh`, or a real HOME.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from vibe_clock.cli import init, render, setup, workflow
from vibe_clock.config import Config
from vibe_clock.models import AgentStats
from vibe_clock.workflow import WORKFLOW_PATH, readme_snippet, workflow_yaml

def _split_runner() -> CliRunner:
    """A runner that keeps stdout and stderr apart, across click versions.

    click < 8.2 mixes them unless told not to; 8.2 dropped the argument and
    splits by default.
    """
    if "mix_stderr" in inspect.signature(CliRunner.__init__).parameters:
        return CliRunner(mix_stderr=False)
    return CliRunner()


def _stats() -> AgentStats:
    return AgentStats(
        generated_at=datetime(2026, 2, 24, tzinfo=timezone.utc),
        days_covered=7,
        active_days=5,
        total_sessions=12,
        total_minutes=321.0,
        active_agents=["claude_code"],
        favorite_model="Claude",
    )


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """A config with one detected agent and every side effect captured."""
    config = Config()
    for name in ("claude_code", "codex", "gemini_cli", "opencode"):
        setattr(config.paths, name, tmp_path / f"missing-{name}")
    config.paths.claude_code = tmp_path / "claude"
    config.paths.claude_code.mkdir()
    config.github.token = "synthetic-token"

    published: list[Config] = []
    saved: list[Config] = []

    def fake_publish(current, stats):
        current.github.gist_id = "SYNTHETIC_GIST"
        published.append(current)

    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: config)
    monkeypatch.setattr("vibe_clock.cli.save_config", lambda c: saved.append(c))
    monkeypatch.setattr("vibe_clock.cli._collect_public_stats", lambda c: _stats())
    monkeypatch.setattr("vibe_clock.cli._publish_public_stats", fake_publish)
    monkeypatch.setattr("vibe_clock.cli._install_schedule", lambda *a, **k: None)
    monkeypatch.setattr("vibe_clock.cli.gh.is_available", lambda: False)
    monkeypatch.setattr("vibe_clock.cli.gh.login", lambda: None)
    return config, published, saved


# --------------------------------------------------------------------------
# setup
# --------------------------------------------------------------------------


def test_setup_publishes_and_prints_manual_instructions_without_gh(wired) -> None:
    config, published, saved = wired

    result = CliRunner().invoke(
        setup, ["--profile-repo", "someone/someone", "--yes", "--no-schedule"]
    )

    assert result.exit_code == 0, result.output
    assert published, "setup must publish the gist"
    assert config.privacy.public_sharing_enabled is True
    assert config.github.profile_repo == "someone/someone"
    # Without gh, the user is told exactly where to paste the ID.
    assert "VIBE_CLOCK_GIST_ID" in result.output
    assert "SYNTHETIC_GIST" in result.output
    # And gets the workflow verbatim, permissions block included.
    assert "permissions:" in result.output
    assert "contents: write" in result.output


def test_setup_refuses_a_chart_whose_data_would_not_be_shared(wired) -> None:
    """The exact trap the author fell into: a profile asking for charts built
    from data the payload never carried, discovered only in CI."""
    _config, published, _saved = wired

    result = CliRunner().invoke(
        setup, ["--profile-repo", "someone/someone", "--charts", "card,hourly", "--yes"]
    )

    assert result.exit_code != 0
    assert "--time-patterns" in result.output
    assert not published, "nothing may be published when the request is incoherent"


def test_setup_accepts_a_chart_once_its_data_is_shared(wired) -> None:
    _config, published, _saved = wired

    result = CliRunner().invoke(
        setup,
        [
            "--profile-repo", "someone/someone",
            "--charts", "card,hourly",
            "--time-patterns",
            "--yes",
            "--no-schedule",
        ],
    )

    assert result.exit_code == 0, result.output
    assert published


def test_setup_rejects_a_malformed_profile_repo(wired) -> None:
    _config, published, _saved = wired

    result = CliRunner().invoke(setup, ["--profile-repo", "not-a-slug", "--yes"])

    assert result.exit_code != 0
    assert "owner/repo" in result.output
    assert not published


def test_setup_writes_the_workflow_into_a_matching_checkout(wired, tmp_path, monkeypatch) -> None:
    """When run from inside the profile repo, setup installs the file itself."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    monkeypatch.chdir(checkout)
    monkeypatch.setattr("vibe_clock.cli._git_slug", lambda path: "someone/someone")

    result = CliRunner().invoke(
        setup, ["--profile-repo", "someone/someone", "--yes", "--no-schedule"]
    )

    assert result.exit_code == 0, result.output
    written = (checkout / WORKFLOW_PATH).read_text()
    assert written == workflow_yaml()


def test_setup_sets_the_repo_secret_when_gh_is_authenticated(wired, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr("vibe_clock.cli.gh.is_available", lambda: True)
    monkeypatch.setattr(
        "vibe_clock.cli.gh.set_secret",
        lambda repo, name, value: (calls.append((repo, name, value)), (True, "ok"))[1],
    )

    result = CliRunner().invoke(
        setup, ["--profile-repo", "someone/someone", "--yes", "--no-schedule"]
    )

    assert result.exit_code == 0, result.output
    assert calls == [("someone/someone", "VIBE_CLOCK_GIST_ID", "SYNTHETIC_GIST")]


def test_setup_stops_when_the_preview_is_declined(wired) -> None:
    _config, published, saved = wired

    result = CliRunner().invoke(
        setup, ["--profile-repo", "someone/someone"], input="n\n"
    )

    assert result.exit_code == 0
    assert not published
    assert not saved, "declining must not persist a half-finished config"


def test_setup_aborts_when_no_agent_is_installed(wired, tmp_path) -> None:
    config, published, _saved = wired
    config.paths.claude_code = tmp_path / "gone"

    result = CliRunner().invoke(setup, ["--profile-repo", "someone/someone", "--yes"])

    assert result.exit_code != 0
    assert "no agent data directories found" in result.output
    assert not published


# --------------------------------------------------------------------------
# init must not destroy a working setup
# --------------------------------------------------------------------------


def test_init_preserves_an_existing_share(monkeypatch, tmp_path) -> None:
    """Re-running init used to wipe the gist ID and disable sharing, leaving the
    scheduled push installed and failing forever."""
    config = Config()
    config.github.gist_id = "SYNTHETIC_GIST"
    config.github.token = "synthetic-token"
    config.privacy.public_sharing_enabled = True
    config.privacy.share_token_counts = True
    config.schedule.enabled = True
    for name in ("claude_code", "codex", "gemini_cli", "opencode"):
        setattr(config.paths, name, tmp_path / f"missing-{name}")

    saved: list[Config] = []
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: config)
    monkeypatch.setattr("vibe_clock.cli.save_config", lambda c: saved.append(c))
    monkeypatch.setattr("vibe_clock.cli.click.prompt", lambda *a, **k: "")

    result = CliRunner().invoke(init, [])

    assert result.exit_code == 0
    after = saved[-1]
    assert after.github.gist_id == "SYNTHETIC_GIST"
    assert after.github.token == "synthetic-token"
    assert after.privacy.public_sharing_enabled is True
    assert after.privacy.share_token_counts is True
    assert after.schedule.enabled is True


def test_init_reset_starts_from_defaults(monkeypatch, tmp_path) -> None:
    config = Config()
    config.github.gist_id = "SYNTHETIC_GIST"
    saved: list[Config] = []
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: config)
    monkeypatch.setattr("vibe_clock.cli.save_config", lambda c: saved.append(c))
    monkeypatch.setattr("vibe_clock.cli.click.prompt", lambda *a, **k: "")

    result = CliRunner().invoke(init, ["--reset"])

    assert result.exit_code == 0
    assert saved[-1].github.gist_id == ""


# --------------------------------------------------------------------------
# render: no more silent wrong output
# --------------------------------------------------------------------------


def test_render_rejects_an_unknown_theme(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: Config())

    result = CliRunner().invoke(render, ["--theme", "neon", "--output", str(tmp_path)])

    assert result.exit_code != 0
    assert not list(tmp_path.glob("*.svg"))


def test_render_rejects_an_unknown_chart_type(monkeypatch, tmp_path) -> None:
    """A typo used to print a red line and exit 0, so CI stayed green while the
    chart the profile links to was never written."""
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: Config())

    result = CliRunner().invoke(render, ["--type", "card,bogus", "--output", str(tmp_path)])

    assert result.exit_code != 0
    assert "bogus" in result.output
    assert not list(tmp_path.glob("*.svg"))


def test_render_rejects_an_unknown_theme_from_the_config_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: Config(theme="solarized"))

    result = CliRunner().invoke(render, ["--output", str(tmp_path)])

    assert result.exit_code != 0
    assert "solarized" in result.output


# --------------------------------------------------------------------------
# the workflow template
# --------------------------------------------------------------------------


def test_workflow_grants_the_permission_its_git_push_needs() -> None:
    """GITHUB_TOKEN is read-only by default, and the action ends in `git push`."""
    yaml = workflow_yaml()
    assert "permissions:\n  contents: write" in yaml
    assert "schedule:" in yaml and "cron:" in yaml
    assert "workflow_dispatch:" in yaml
    assert "${{ secrets.VIBE_CLOCK_GIST_ID }}" in yaml


def test_workflow_pins_the_action_to_an_exact_release() -> None:
    """A moving ref would let an upstream change rewrite a user's profile."""
    assert "dexhunter/vibe-clock@v" in workflow_yaml()
    assert "@main" not in workflow_yaml()


def test_workflow_command_prints_what_setup_would_write(monkeypatch) -> None:
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: Config())
    result = CliRunner().invoke(workflow, [])
    assert result.exit_code == 0
    assert result.output == workflow_yaml()


def test_workflow_command_rejects_an_unknown_chart(monkeypatch) -> None:
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: Config())
    result = CliRunner().invoke(workflow, ["--charts", "bogus"])
    assert result.exit_code != 0
    assert "bogus" in result.output


def test_workflow_command_warns_on_unshared_data_without_failing(monkeypatch) -> None:
    """Unlike `setup`, this command may be run on a machine that is not the one
    that pushes, so its local privacy config is advisory, not authoritative."""
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: Config())

    result = _split_runner().invoke(workflow, ["--charts", "heatmap"])

    assert result.exit_code == 0
    assert "--daily-activity" in result.stderr
    # The YAML must stay clean, so `vibe-clock workflow > file` still works.
    assert result.stdout == workflow_yaml(chart_types="heatmap")


def test_readme_snippet_names_the_files_the_action_writes() -> None:
    snippet = readme_snippet("card,donut")
    assert "images/vibe-clock-card.svg" in snippet
    assert "images/vibe-clock-donut.svg" in snippet


# --------------------------------------------------------------------------
# scheduling
# --------------------------------------------------------------------------


def test_schedule_explains_an_unsupported_platform(monkeypatch) -> None:
    """On Windows `get_scheduler()` raises. That used to surface as an
    unhandled traceback with no hint that WSL is the answer."""
    from vibe_clock.cli import schedule

    config = Config()
    config.github.token = "synthetic-token"
    config.privacy.public_sharing_enabled = True
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: config)
    monkeypatch.setattr("vibe_clock.cli.save_config", lambda c: None)

    def no_backend():
        raise RuntimeError("No supported scheduler found.")

    monkeypatch.setattr("vibe_clock.scheduler.get_scheduler", no_backend)

    result = CliRunner().invoke(schedule, [])

    assert result.exit_code == 0
    assert result.exception is None
    assert "WSL" in result.output


def test_schedule_warns_systemd_users_about_lingering(monkeypatch) -> None:
    """A user timer stops at logout unless lingering is enabled, which silently
    freezes the profile on a headless machine."""
    from vibe_clock.cli import schedule

    config = Config()
    config.github.token = "synthetic-token"
    config.privacy.public_sharing_enabled = True
    monkeypatch.setattr("vibe_clock.cli.load_config", lambda: config)
    monkeypatch.setattr("vibe_clock.cli.save_config", lambda c: None)

    class FakeSystemd:
        backend_name = "systemd"

        def is_scheduled(self):
            return False

        def schedule(self, binary, interval, run_time):
            return "systemctl --user status vibe-clock-push.timer"

    monkeypatch.setattr("vibe_clock.scheduler.get_scheduler", lambda: FakeSystemd())
    monkeypatch.setattr("vibe_clock.scheduler.resolve_binary", lambda: "/usr/bin/vibe-clock")

    result = CliRunner().invoke(schedule, [])

    assert result.exit_code == 0
    assert "enable-linger" in result.output
