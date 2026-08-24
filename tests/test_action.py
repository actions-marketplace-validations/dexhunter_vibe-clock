"""Regression tests for the composite GitHub Action."""

from pathlib import Path


ACTION_YAML = Path(__file__).parents[1] / "action.yml"


def test_action_installs_from_checked_out_source() -> None:
    action = ACTION_YAML.read_text()

    assert "github.action_ref" not in action
    assert "VIBE_CLOCK_ACTION_PATH: ${{ github.action_path }}" in action
    assert 'python -m pip install "$VIBE_CLOCK_ACTION_PATH"' in action


def test_action_names_the_permission_its_push_needs() -> None:
    """A bare `git push` 403s on every repo that has not granted write access,
    which is the default. The log must say what to add, not just fail."""
    action = ACTION_YAML.read_text()

    assert "contents: write" in action
    assert "::error::git push failed" in action


def test_action_explains_a_failed_gist_fetch() -> None:
    action = ACTION_YAML.read_text()

    assert "gist_id is empty" in action
    assert "Could not fetch vibe-clock-data.json" in action
