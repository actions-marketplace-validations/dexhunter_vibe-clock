"""Optional integration with the GitHub CLI (`gh`).

The manual path — mint a Classic PAT in a browser, copy it into a prompt, copy a
Gist ID into a repo secret page — is the single largest onboarding cost. Anyone
who already has `gh` authenticated has all three of those things already, so we
borrow them instead of asking again.

`gh` is never required. Every function here returns None / False when `gh` is
missing, unauthenticated, or fails, and the caller falls back to the manual
flow. Nothing in this module raises.
"""

from __future__ import annotations

import re
import shutil
import subprocess

_TIMEOUT = 30


def _run(args: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess | None:
    if shutil.which("gh") is None:
        return None
    try:
        return subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            input=stdin,
            timeout=_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def is_available() -> bool:
    """True when `gh` is installed and holds a live authentication."""
    result = _run(["auth", "status"])
    return result is not None and result.returncode == 0


def token() -> str | None:
    """The token `gh` is authenticated with, if any."""
    result = _run(["auth", "token"])
    if result is None or result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def scopes() -> set[str]:
    """Scopes on the active `gh` token, empty when they cannot be determined.

    `gh auth status` prints them as: ``- Token scopes: 'gist', 'repo'``. Newer
    `gh` writes this to stdout, older versions to stderr, so read both.
    """
    result = _run(["auth", "status"])
    if result is None or result.returncode != 0:
        return set()
    match = re.search(r"Token scopes:(.*)", result.stdout + "\n" + result.stderr)
    if not match:
        return set()
    return {value.strip().strip("'\"") for value in match.group(1).split(",") if value.strip()}


def login() -> str | None:
    """The authenticated user's GitHub login."""
    result = _run(["api", "user", "-q", ".login"])
    if result is None or result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def repo_exists(repo: str) -> bool:
    result = _run(["api", f"repos/{repo}", "-q", ".full_name"])
    return result is not None and result.returncode == 0


def set_secret(repo: str, name: str, value: str) -> tuple[bool, str]:
    """Set an Actions secret. Returns (ok, message).

    The value goes over stdin rather than `--body` so it never appears in the
    process list.
    """
    result = _run(["secret", "set", name, "--repo", repo], stdin=value)
    if result is None:
        return False, "gh is not available"
    if result.returncode == 0:
        return True, f"set {name} on {repo}"
    return False, (result.stderr or result.stdout).strip() or "gh secret set failed"
