"""Configuration loading from TOML + environment variables."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from .workflow import WORKFLOW_FILENAME

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

CONFIG_DIR = Path.home() / ".config" / "vibe-clock"
CONFIG_PATH = CONFIG_DIR / "config.toml"


class PathsConfig(BaseModel):
    claude_code: Path = Field(default_factory=lambda: Path.home() / ".claude")
    codex: Path = Field(default_factory=lambda: Path.home() / ".codex")
    gemini_cli: Path = Field(default_factory=lambda: Path.home() / ".gemini")
    opencode: Path = Field(
        default_factory=lambda: Path.home() / ".local" / "share" / "opencode"
    )


class GithubConfig(BaseModel):
    token: str = ""
    gist_id: str = ""
    # "owner/repo" that renders your SVGs. Empty means "not configured"; it is
    # never guessed, because guessing produced a confusing 404 warning on every
    # push for anyone whose profile repo is not <login>/<login>.
    profile_repo: str = ""
    # Workflow file to dispatch, relative to .github/workflows/. Configurable
    # because the name was previously hardcoded, so any other name 404'd.
    workflow_file: str = WORKFLOW_FILENAME
    # Dispatching a workflow needs a token with `repo` scope, which is far
    # broader than the `gist` scope everything else needs. Off by default: the
    # workflow's own cron covers the common case with no extra permission.
    trigger_workflow: bool = False


class PrivacyConfig(BaseModel):
    # Glob patterns or plain substrings, case-insensitive; a matching project is
    # dropped from every statistic.
    exclude_projects: list[str] = Field(default_factory=list)
    exclude_date_ranges: list[list[str]] = Field(default_factory=list)
    # NOTE: `anonymize_projects` used to be documented here. It was read by
    # nothing, so setting it to `false` did not disable anonymisation and
    # setting it to `true` did not enable anything. Project names are aliased
    # unconditionally by `sanitizer._public_projects`, and are only published at
    # all behind `share_project_aliases`. Old config files still load: pydantic
    # ignores the extra key.
    public_sharing_enabled: bool = False
    public_days: int = 7
    share_daily_activity: bool = False
    share_message_counts: bool = False
    share_token_counts: bool = False
    share_time_patterns: bool = False
    share_project_aliases: bool = False


class ScheduleConfig(BaseModel):
    enabled: bool = False
    interval: str = "daily"
    time: str = "00:00"
    backend: str = ""


class Config(BaseModel):
    default_days: int = 30
    theme: str = "dark"
    paths: PathsConfig = Field(default_factory=PathsConfig)
    github: GithubConfig = Field(default_factory=GithubConfig)
    enabled_agents: list[str] = Field(
        default_factory=lambda: ["claude_code", "codex", "gemini_cli", "opencode"]
    )
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)


def load_config() -> Config:
    """Load config from TOML file, overlay environment variables."""
    data: dict = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            raw = tomllib.load(f)
        # Map TOML sections to Config fields
        if "general" in raw:
            data["default_days"] = raw["general"].get("default_days", 30)
            data["theme"] = raw["general"].get("theme", "dark")
        if "paths" in raw:
            paths = {}
            for key, val in raw["paths"].items():
                paths[key] = Path(val).expanduser()
            data["paths"] = paths
        if "github" in raw:
            data["github"] = raw["github"]
        if "agents" in raw and "enabled" in raw["agents"]:
            data["enabled_agents"] = raw["agents"]["enabled"]
        if "privacy" in raw:
            data["privacy"] = raw["privacy"]
        if "schedule" in raw:
            data["schedule"] = raw["schedule"]

    config = Config(**data)

    # Environment variable fallbacks (TOML takes precedence if set)
    if not config.github.token:
        if token := os.environ.get("GITHUB_TOKEN"):
            config.github.token = token
    if gist_id := os.environ.get("VIBE_CLOCK_GIST_ID"):
        config.github.gist_id = gist_id
    if days := os.environ.get("VIBE_CLOCK_DAYS"):
        config.default_days = int(days)

    return config


def save_config(config: Config) -> None:
    """Write config back to TOML file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, stat.S_IRWXU)  # 0700
    lines = [
        "[general]",
        f'default_days = {config.default_days}',
        f'theme = "{config.theme}"',
        "",
        "[paths]",
        f'claude_code = "{config.paths.claude_code}"',
        f'codex = "{config.paths.codex}"',
        f'gemini_cli = "{config.paths.gemini_cli}"',
        f'opencode = "{config.paths.opencode}"',
        "",
        "[github]",
        f'token = "{config.github.token}"',
        f'gist_id = "{config.github.gist_id}"',
        f'profile_repo = "{config.github.profile_repo}"',
        f'workflow_file = "{config.github.workflow_file}"',
        f'trigger_workflow = {"true" if config.github.trigger_workflow else "false"}',
        "",
        "[agents]",
        f'enabled = {config.enabled_agents}',
        "",
        "[privacy]",
        f'exclude_projects = {config.privacy.exclude_projects}',
        f'exclude_date_ranges = {config.privacy.exclude_date_ranges}',
        f'public_sharing_enabled = {"true" if config.privacy.public_sharing_enabled else "false"}',
        f'public_days = {config.privacy.public_days}',
        f'share_daily_activity = {"true" if config.privacy.share_daily_activity else "false"}',
        f'share_message_counts = {"true" if config.privacy.share_message_counts else "false"}',
        f'share_token_counts = {"true" if config.privacy.share_token_counts else "false"}',
        f'share_time_patterns = {"true" if config.privacy.share_time_patterns else "false"}',
        f'share_project_aliases = {"true" if config.privacy.share_project_aliases else "false"}',
        "",
        "[schedule]",
        f'enabled = {"true" if config.schedule.enabled else "false"}',
        f'interval = "{config.schedule.interval}"',
        f'time = "{config.schedule.time}"',
        f'backend = "{config.schedule.backend}"',
    ]
    CONFIG_PATH.write_text("\n".join(lines) + "\n")
    os.chmod(CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 0600
