"""The GitHub Actions workflow vibe-clock asks its users to install.

This lives in the package rather than in the README because the README is not
executable: the previously documented example omitted `permissions:` (so the
action's `git push` 403'd on every new repo since GitHub made GITHUB_TOKEN
read-only by default) and omitted `schedule:` (so a profile that promised daily
updates never updated). Those were fixed once, by hand, in the author's own
profile repo, and the published example stayed broken.

`vibe-clock setup` writes exactly this file, `vibe-clock workflow` prints it,
and a test asserts every README embeds it verbatim. There is one copy.
"""

from __future__ import annotations

from . import __version__

# Name is load-bearing: `push --trigger-workflow` dispatches this file by name.
WORKFLOW_FILENAME = "vibe-clock.yml"
WORKFLOW_PATH = f".github/workflows/{WORKFLOW_FILENAME}"

# 00:30 UTC — half an hour after the default local `vibe-clock push`, which runs
# at your local equivalent of 00:00 UTC. Rendering before the push just redraws
# yesterday's numbers.
DEFAULT_CRON = "30 0 * * *"
DEFAULT_CHART_TYPES = "card,donut"

# Where the composite action lives. A fork changes this one line.
ACTION_OWNER = "dexhunter/vibe-clock"

# Pinned to an exact release, not a branch: a moving ref would let an upstream
# change rewrite your profile without you asking.
#
# Derived from the package version rather than written out, because a literal
# went stale the moment a release bumped one and not the other — and the pin is
# load-bearing: `action.yml` installs the action's own checkout, not PyPI, so
# the tag named here decides which code renders a reader's profile.
ACTION_REF = f"{ACTION_OWNER}@v{__version__}"


def workflow_yaml(
    *,
    chart_types: str = DEFAULT_CHART_TYPES,
    cron: str = DEFAULT_CRON,
    action_ref: str = ACTION_REF,
) -> str:
    """Return the complete workflow file, ready to commit."""
    return f"""name: Update Vibe Clock Stats

on:
  schedule:
    # Runs after your local `vibe-clock push` updates the Gist.
    - cron: "{cron}"
  workflow_dispatch:

# Required: the action commits the generated SVGs back to this repo, and
# GITHUB_TOKEN is read-only by default.
permissions:
  contents: write

concurrency:
  group: vibe-clock
  cancel-in-progress: false

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: {action_ref}
        with:
          gist_id: ${{{{ secrets.VIBE_CLOCK_GIST_ID }}}}
          chart_types: {chart_types}
"""


def readme_snippet(chart_types: str = DEFAULT_CHART_TYPES) -> str:
    """Return the `<img>` block to paste into a profile README."""
    from .cli import SVG_RENDERERS  # local import: cli imports this module

    lines = ['<p align="center">']
    for name in [t.strip() for t in chart_types.split(",") if t.strip()]:
        entry = SVG_RENDERERS.get(name)
        if entry is None:
            continue
        lines.append(f'  <img src="images/{entry[0]}" alt="{name}" />')
    lines.append("</p>")
    return "\n".join(lines)
