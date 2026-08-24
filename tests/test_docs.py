"""The docs must agree with the code they instruct people to run.

The published workflow example was broken as written for every new user: no
`permissions:` (so the action's `git push` 403'd) and no `schedule:` (so a
profile promising daily updates never updated). Both had been fixed by hand in
the author's own profile repo and never fed back. These tests make the README
copies of the workflow generated output rather than prose someone remembers to
update.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vibe_clock.workflow import ACTION_REF, workflow_yaml

ROOT = Path(__file__).parents[1]
READMES = [
    ROOT / "README.md",
    ROOT / "README.zh-CN.md",
    ROOT / "README.ja.md",
    ROOT / "README.es.md",
]
DOCS = [*READMES, ROOT / "SKILL.md"]


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_doc_embeds_the_generated_workflow(doc: Path) -> None:
    assert workflow_yaml().rstrip("\n") in doc.read_text()


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_no_doc_pins_the_action_to_a_moving_ref(doc: Path) -> None:
    """`@main` would let an upstream change rewrite a reader's profile."""
    text = doc.read_text()
    assert "vibe-clock@main" not in text
    assert ACTION_REF in text


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_doc_names_the_scope_the_dispatch_needs(doc: Path) -> None:
    """Docs used to ask only for `gist`, while push always tried a
    workflow_dispatch, which needs `repo`. The mismatch printed a warning on
    every push forever."""
    text = doc.read_text()
    assert "gist" in text
    assert "trigger_workflow" in text or "repo" in text


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_no_doc_claims_the_removed_proxy_behaviour(doc: Path) -> None:
    """SKILL.md told users vibe-clock sets `trust_env=False`; it has not since
    commit 311952d."""
    assert "trust_env" not in doc.read_text()


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_doc_mentions_gemini_cli(doc: Path) -> None:
    """It ships enabled by default but was missing from the docs entirely."""
    assert "gemini" in doc.read_text().lower()


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_doc_points_at_the_scheduler(doc: Path) -> None:
    """Without a local schedule the Gist goes stale and the profile freezes —
    yet `schedule` appeared once, in a table, in one README."""
    assert "vibe-clock schedule" in doc.read_text()


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_doc_leads_with_setup(doc: Path) -> None:
    assert "vibe-clock setup" in doc.read_text()


def test_readmes_all_link_to_each_other() -> None:
    for readme in READMES:
        text = readme.read_text()
        for other in READMES:
            if other is readme:
                continue
            assert other.name in text, f"{readme.name} does not link to {other.name}"


def test_readme_config_block_matches_what_save_config_writes(monkeypatch, tmp_path) -> None:
    """The documented TOML drifted from `config.py` before — SKILL.md's copy was
    missing gemini_cli entirely, and no README mentioned workflow_file."""
    import re

    from vibe_clock import config as config_module
    from vibe_clock.config import Config, save_config

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.toml")
    save_config(Config())
    real = set(re.findall(r"^(\w+) = ", (tmp_path / "config.toml").read_text(), re.M))

    block = (ROOT / "README.md").read_text().split("```toml")[1].split("```")[0]
    documented = set(re.findall(r"^(\w+) = ", block, re.M))

    assert real == documented


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_no_doc_names_a_command_that_does_not_exist(doc: Path) -> None:
    import re

    from vibe_clock.cli import cli

    # Only lines that look like a shell invocation, so prose such as
    # "vibe-clock reads them" is not mistaken for a subcommand.
    invoked = set(re.findall(r"^\s*(?:\$ )?vibe-clock ([a-z_]+)", doc.read_text(), re.M))
    assert invoked <= set(cli.commands), sorted(invoked - set(cli.commands))
