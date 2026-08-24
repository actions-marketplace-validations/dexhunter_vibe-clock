#!/usr/bin/env python3
"""Bump the vibe-clock version and propagate it everywhere it is written down.

Usage:
    python scripts/bump_version.py 1.5.0
    python scripts/bump_version.py patch|minor|major

The action reference in the docs is generated from `vibe_clock/workflow.py`, so
this script updates that constant and the docs follow. Before this existed as
part of the release flow, the release workflow bumped only pyproject.toml and
every `@vX.Y.Z` pin in the docs silently went stale.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"

WORKFLOW_PY = ROOT / "vibe_clock" / "workflow.py"

# Files that may contain a `<owner>/vibe-clock@vX.Y.Z` reference.
DOC_FILES = [
    ROOT / "README.md",
    ROOT / "README.zh-CN.md",
    ROOT / "README.ja.md",
    ROOT / "README.es.md",
    ROOT / "SKILL.md",
]

VERSION_RE = re.compile(r"^version\s*=\s*\"(.+?)\"", re.MULTILINE)
# Owner-agnostic, so a fork's own ref is bumped instead of silently skipped.
ACTION_REF_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?/vibe-clock@v[\d.]+")
ACTION_REF_CONST_RE = re.compile(r'ACTION_REF = "(.+?)@v[\d.]+"')


def action_owner() -> str:
    """The owner half of the action ref currently in workflow.py."""
    match = ACTION_REF_CONST_RE.search(WORKFLOW_PY.read_text())
    return match.group(1) if match else "dexhunter/vibe-clock"


def resolve_version(argument: str) -> str:
    """Accept an explicit version or a patch/minor/major bump keyword."""
    if argument not in ("patch", "minor", "major"):
        return argument
    major, minor, patch = (int(part) for part in read_current_version().split("."))
    if argument == "major":
        return f"{major + 1}.0.0"
    if argument == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def read_current_version() -> str:
    text = PYPROJECT.read_text()
    m = VERSION_RE.search(text)
    if not m:
        print("Could not find version in pyproject.toml", file=sys.stderr)
        sys.exit(1)
    return m.group(1)


def bump(new_version: str) -> None:
    old_version = read_current_version()
    if old_version == new_version:
        print(f"Already at {new_version}")
        return

    # 1. Update pyproject.toml
    text = PYPROJECT.read_text()
    text = text.replace(f'version = "{old_version}"', f'version = "{new_version}"', 1)
    PYPROJECT.write_text(text)
    print(f"  pyproject.toml: {old_version} -> {new_version}")

    # 2. Update the action ref that the workflow template is generated from
    new_ref = f"{action_owner()}@v{new_version}"
    workflow_text = WORKFLOW_PY.read_text()
    updated_workflow = ACTION_REF_CONST_RE.sub(f'ACTION_REF = "{new_ref}"', workflow_text)
    if updated_workflow != workflow_text:
        WORKFLOW_PY.write_text(updated_workflow)
        print(f"  vibe_clock/workflow.py: ACTION_REF -> {new_ref}")

    # 3. Update any action ref written out longhand in the docs
    for doc in DOC_FILES:
        if not doc.exists():
            continue
        content = doc.read_text()
        updated = ACTION_REF_RE.sub(new_ref, content)
        if updated != content:
            doc.write_text(updated)
            print(f"  {doc.name}: updated action ref to v{new_version}")

    print(f"\nBumped to {new_version}. Review changes, then commit.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <new-version|patch|minor|major>")
        print(f"Current version: {read_current_version()}")
        sys.exit(1)
    bump(resolve_version(sys.argv[1]))
