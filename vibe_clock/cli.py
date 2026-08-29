"""CLI entry point for vibe-clock."""

from __future__ import annotations

import json
import sys
from datetime import datetime, time, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

import click
import rich.box as box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .aggregator import aggregate
from .collectors import COLLECTOR_MAP, get_collectors
from .formatting import format_bar, format_hourly_chart, format_hours, format_number
from .config import CONFIG_PATH, Config, load_config, save_config
from .models import AgentStats
from .payload import (
    DAILY_ACTIVITY,
    PROJECT_ALIASES,
    TIME_PATTERNS,
    TOKEN_COUNTS,
    PayloadError,
    Requirement,
    load_public_payload,
    missing_requirements,
    to_agent_stats,
)
from .sanitizer import build_public_payload, preview, public_payload
from .svg.bars import render_bars
from .svg.card import render_card
from .svg.donut import render_donut
from .svg.heatmap import render_heatmap
from .svg.hourly import render_hourly
from .svg.token_bars import render_token_bars
from .svg.weekly import render_weekly
from . import gh
from .workflow import (
    DEFAULT_CHART_TYPES,
    WORKFLOW_PATH,
    readme_snippet,
    workflow_yaml,
)

console = Console()
# Warnings go to stderr so `vibe-clock workflow > file` captures only the YAML.
err_console = Console(stderr=True)

# Every renderer branches on `theme == "dark"`, so an unrecognised value used to
# render light without saying so.
THEMES = ("dark", "light")

# filename, renderer, and the shared data the chart cannot be drawn without.
SVG_RENDERERS: dict[str, tuple[str, object, tuple[Requirement, ...]]] = {
    "card": ("vibe-clock-card.svg", render_card, ()),
    "heatmap": ("vibe-clock-heatmap.svg", render_heatmap, (DAILY_ACTIVITY,)),
    "donut": ("vibe-clock-donut.svg", render_donut, ()),
    "bars": ("vibe-clock-bars.svg", render_bars, (PROJECT_ALIASES,)),
    "token_bars": ("vibe-clock-token-bars.svg", render_token_bars, (TOKEN_COUNTS,)),
    "hourly": ("vibe-clock-hourly.svg", render_hourly, (TIME_PATTERNS,)),
    "weekly": ("vibe-clock-weekly.svg", render_weekly, (DAILY_ACTIVITY,)),
}


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """vibe-clock: Track AI coding agent usage."""


@cli.command()
@click.option("--reset", is_flag=True, help="Discard the existing config and start from defaults.")
def init(reset: bool) -> None:
    """Create or refresh the config file (`setup` does the whole onboarding)."""
    console.print("[bold]vibe-clock init[/bold]")

    # Start from what is already configured. Constructing a fresh Config() here
    # used to silently wipe gist_id, profile_repo, and every privacy and
    # schedule setting — so re-running init, the most natural thing a confused
    # user does, permanently disabled their share while leaving the scheduled
    # push installed and failing.
    config = Config() if reset else load_config()

    config.enabled_agents = _detect_agents(config)

    prompt = "\nGitHub token (Classic PAT with 'gist' scope, or press Enter to skip)"
    if config.github.token:
        prompt = "\nGitHub token (press Enter to keep the one already configured)"
    token = click.prompt(prompt, default="", show_default=False, hide_input=True)
    if token:
        config.github.token = token

    save_config(config)
    from .config import CONFIG_PATH
    console.print(f"\n[green]Config saved to {CONFIG_PATH}[/green]")
    if not config.privacy.public_sharing_enabled:
        console.print("[dim]Nothing is published yet — run `vibe-clock setup` to finish.[/dim]")


def _detect_agents(config: Config) -> list[str]:
    """Report which agents have a data directory, and return their names."""
    available = []
    for name in COLLECTOR_MAP:
        path = getattr(config.paths, name, None)
        if path and path.exists():
            available.append(name)
            console.print(f"  [green]✓[/green] Found {name} at {path}")
        elif path:
            console.print(f"  [dim]✗ {name} not found at {path}[/dim]")
    return available


@cli.command()
@click.option("--days", "-d", default=None, type=int, help="Number of days to include.")
def summary(days: int | None) -> None:
    """Show a summary of AI agent usage."""
    config = load_config()
    if days:
        config.default_days = days

    collectors = get_collectors(config)
    if not collectors:
        console.print(
            "[yellow]No agent data found. Check that an agent has written logs, "
            "then run 'vibe-clock setup'.[/yellow]"
        )
        return

    all_sessions = []
    for c in collectors:
        sessions = c.collect(days=config.default_days)
        console.print(f"  [dim]{c.agent_name}: {len(sessions)} sessions[/dim]")
        all_sessions.extend(sessions)

    stats = aggregate(all_sessions, config)

    # Header
    header = Text()
    header.append("  ⏱  V I B E   C L O C K", style="bold cyan")
    header.append(f"  Last {config.default_days} Days", style="dim")
    console.print(Panel(header, box=box.ROUNDED, border_style="cyan"))

    # Overview
    _print_overview(stats)

    # Token Breakdown
    if stats.total_tokens.total > 0:
        _print_token_breakdown(stats)

    # Hourly Activity
    if any(stats.hourly):
        _print_hourly(stats)

    # Models
    if stats.models:
        _print_models(stats)

    # Projects
    if stats.projects:
        _print_projects(stats)

    # Footer
    console.print(f"[dim]Generated {stats.generated_at:%Y-%m-%d %H:%M} UTC[/dim]")


def _print_overview(stats: "AgentStats") -> None:
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column(style="cyan")
    t.add_column(style="bold white")
    t.add_column(style="cyan")
    t.add_column(style="bold white")
    t.add_row(
        "⏱  Agent Time",
        format_hours(stats.total_minutes),
        "🤖 Favorite Model",
        stats.favorite_model or "—",
    )
    t.add_row(
        "💬 Sessions",
        str(stats.total_sessions),
        "🕐 Peak Hour",
        f"{stats.peak_hour}:00",
    )
    t.add_row(
        "📨 Messages",
        format_number(stats.total_messages),
        "🔥 Longest Stretch",
        f"{stats.longest_stretch_minutes:.0f} min",
    )
    t.add_row(
        "🔢 Tokens",
        format_number(stats.total_tokens.total),
        "🛠  Active Agents",
        ", ".join(stats.active_agents) or "—",
    )
    console.print(Panel(t, title="Overview", box=box.ROUNDED, border_style="blue"))


def _print_token_breakdown(stats: "AgentStats") -> None:
    total = stats.total_tokens.total
    parts = [
        ("Input", stats.total_tokens.input_tokens, "cyan"),
        ("Output", stats.total_tokens.output_tokens, "green"),
        ("Cache R", stats.total_tokens.cache_read_tokens, "yellow"),
        ("Cache W", stats.total_tokens.cache_write_tokens, "magenta"),
    ]
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_column(style="bold", width=10)
    t.add_column(width=50)
    t.add_column(justify="right", width=8)
    t.add_column(justify="right", width=6)
    for label, value, color in parts:
        pct = (value / total * 100) if total > 0 else 0
        bar = format_bar(value, total, width=30, filled_style=color)
        t.add_row(label, bar, format_number(value), f"({pct:.0f}%)")
    console.print(Panel(t, title="Token Breakdown", box=box.ROUNDED, border_style="blue"))


def _print_hourly(stats: "AgentStats") -> None:
    chart = format_hourly_chart(stats.hourly, height=6, peak_hour=stats.peak_hour)
    console.print(Panel(chart, title="Hourly Activity", box=box.ROUNDED, border_style="blue"))


def _print_models(stats: "AgentStats") -> None:
    filtered = [
        m for m in stats.models if m.model not in ("unknown", "<synthetic>")
    ][:8]
    if not filtered:
        return
    total_tokens = sum(m.tokens.total for m in filtered)
    t = Table(box=None, padding=(0, 1))
    t.add_column("Model", style="bold")
    t.add_column("Sessions", justify="right")
    t.add_column("Messages", justify="right")
    t.add_column("Tokens", justify="right")
    t.add_column("Share", width=22)
    for m in filtered:
        share = (m.tokens.total / total_tokens * 100) if total_tokens > 0 else 0
        bar = format_bar(m.tokens.total, total_tokens, width=14, filled_style="cyan")
        t.add_row(
            m.model,
            f"{m.session_count:,}",
            f"{m.message_count:,}",
            format_number(m.tokens.total),
            f"{bar} {share:.0f}%",
        )
    console.print(Panel(t, title="Models", box=box.ROUNDED, border_style="blue"))


def _print_projects(stats: "AgentStats") -> None:
    projects = stats.projects[:8]
    if not projects:
        return
    t = Table(box=None, padding=(0, 1))
    t.add_column("Project", style="bold")
    t.add_column("Agent")
    t.add_column("Time", justify="right")
    t.add_column("Sessions", justify="right")
    t.add_column("Tokens", justify="right")
    for p in projects:
        name = p.project.split("/")[-1][:24]
        t.add_row(
            name,
            p.agent,
            format_hours(p.total_minutes),
            str(p.session_count),
            format_number(p.tokens.total),
        )
    console.print(Panel(t, title="Projects", box=box.ROUNDED, border_style="blue"))


@cli.command()
@click.option("--days", "-d", default=None, type=int, help="Number of days to include.")
def status(days: int | None) -> None:
    """Print a compact one-line status summary."""
    config = load_config()
    if days:
        config.default_days = days

    collectors = get_collectors(config)
    if not collectors:
        click.echo("No agent data found. Check that an agent has written logs, then run 'vibe-clock setup'.")
        return

    all_sessions = []
    for c in collectors:
        all_sessions.extend(c.collect(days=config.default_days))

    stats = aggregate(all_sessions, config)
    hours = stats.total_minutes / 60
    model = stats.favorite_model or "—"
    peak = f"{stats.peak_hour}:00"

    click.echo(
        f"\u23f1 {hours:.1f} hrs | {stats.total_sessions} sessions"
        f" | {format_number(stats.total_messages)} msgs"
        f" | {format_number(stats.total_tokens.total)} tokens"
        f" | {model} | peak {peak}"
    )


@cli.command()
@click.option(
    "--type",
    "-t",
    "chart_type",
    default="card,donut",
    show_default=True,
    help="Chart types: card, donut, heatmap, weekly, hourly, bars, token_bars, all",
)
@click.option("--output", "-o", "output_dir", default=".", help="Output directory for SVG files.")
@click.option("--from-json", "json_path", default=None, help="Generate from exported JSON instead of collecting.")
@click.option("--theme", default=None, type=click.Choice(THEMES), help="Theme (default: from config).")
def render(chart_type: str, output_dir: str, json_path: str | None, theme: str | None) -> None:
    """Generate SVG visualizations."""
    config = load_config()
    th = theme or config.theme
    if th not in THEMES:
        raise click.ClickException(
            f"unknown theme {th!r} in {CONFIG_PATH}. Valid themes: {', '.join(THEMES)}."
        )

    types = (
        list(SVG_RENDERERS.keys())
        if chart_type == "all"
        else [t.strip() for t in chart_type.split(",") if t.strip()]
    )
    # A typo in --type used to print a red line and exit 0, so CI stayed green
    # while a chart the profile links to was never written.
    unknown = [t for t in types if t not in SVG_RENDERERS]
    if unknown:
        raise click.ClickException(
            f"unknown chart type(s): {', '.join(unknown)}. "
            f"Valid types: {', '.join(SVG_RENDERERS)}, all."
        )

    if json_path:
        try:
            payload = load_public_payload(Path(json_path).read_text())
        except PayloadError as exc:
            raise click.ClickException(str(exc)) from exc
        console.print(
            f"  [dim]payload schema v{payload.schema_version} "
            f"from vibe-clock {payload.producer_version}[/dim]"
        )
        _require_shared_data(payload, types, where="on the machine that pushes")
        stats = to_agent_stats(payload)
    else:
        # Local rendering goes through the *same* public payload as CI, never
        # the raw aggregate. An SVG is a file the README tells you to commit to
        # a public repo, so it must not be able to carry anything the published
        # JSON could not: `bars` used to draw the raw working directory as its
        # label, and `card`/`donut`/`token_bars` printed the raw model ID —
        # both of which the privacy contract says are never published under any
        # flag. `vibe-clock export` remains the unsanitized local view.
        payload = build_public_payload(_collect_public_stats(config), config)
        _require_shared_data(payload, types)
        stats = to_agent_stats(payload)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for t in types:
        filename, renderer, _ = SVG_RENDERERS[t]
        svg = renderer(stats, theme=th)
        path = out / filename
        path.write_text(svg)
        console.print(f"  [green]✓[/green] {path}")


def _require_shared_data(payload, types: list[str], *, where: str = "") -> None:
    """Refuse to draw a chart from data the payload does not carry.

    Rendering an empty heatmap from a payload that simply never shared daily
    activity looks like "you did nothing for a year". Failing names the flag
    that fixes it.
    """
    suffix = f" {where}" if where else ""
    problems: list[str] = []
    for t in types:
        entry = SVG_RENDERERS.get(t)
        if entry is None:
            continue
        for req in missing_requirements(payload, entry[2]):
            problems.append(
                f"chart '{t}' needs {req.label}, which is not published"
                f" — run `vibe-clock share {req.flag}`{suffix}"
            )
    if problems:
        raise click.ClickException("\n".join(problems))


@cli.command()
@click.option("--output", "-o", default="vibe-clock-data.json", help="Output file path.")
@click.option("--days", "-d", default=None, type=int)
def export(output: str, days: int | None) -> None:
    """Export AgentStats as JSON (local, unsanitized)."""
    config = load_config()
    if days:
        config.default_days = days

    collectors = get_collectors(config)
    all_sessions = []
    for c in collectors:
        all_sessions.extend(c.collect(days=config.default_days))

    stats = aggregate(all_sessions, config)
    Path(output).write_text(stats.model_dump_json(indent=2))
    console.print(f"[green]Exported to {output}[/green]")


def _trigger_render(client: httpx.Client, profile_repo: str, workflow_file: str) -> None:
    """Ask the profile repo to re-render now, instead of waiting for its cron."""
    repo_resp = client.get(f"https://api.github.com/repos/{profile_repo}")
    if repo_resp.status_code != 200:
        console.print(
            f"[yellow]Could not read {profile_repo} ({repo_resp.status_code}). "
            "Check `github.profile_repo` in your config, or that your token has "
            "`repo` scope.[/yellow]"
        )
        return

    default_branch = repo_resp.json().get("default_branch", "main")
    dispatch_resp = client.post(
        f"https://api.github.com/repos/{profile_repo}/actions/workflows/{workflow_file}/dispatches",
        json={"ref": default_branch},
    )

    if dispatch_resp.status_code == 204:
        console.print(f"[green]Triggered {workflow_file} on {profile_repo}[/green]")
        return

    # The two real causes, named, instead of a bare status code. Neither is
    # fatal: the workflow's own cron still renders the Gist we just updated.
    console.print(
        f"[yellow]Could not trigger {workflow_file} on {profile_repo} "
        f"({dispatch_resp.status_code}). Either the token lacks `repo` scope "
        "(dispatching needs it; `gist` alone is not enough), or the workflow is "
        f"not named {workflow_file} — set `github.workflow_file` to its real name. "
        "The scheduled run will still pick this push up.[/yellow]"
    )


def _collect_public_stats(config: Config) -> AgentStats:
    """Collect the last complete public reporting window in UTC."""
    public_config = config.model_copy(deep=True)
    public_config.default_days = config.privacy.public_days
    window_end = datetime.combine(
        datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc
    )

    collectors = get_collectors(public_config)
    all_sessions = []
    for collector in collectors:
        sessions = collector.collect(days=public_config.default_days + 1)
        console.print(f"  [dim]{collector.agent_name}: {len(sessions)} sessions scanned[/dim]")
        all_sessions.extend(sessions)

    return aggregate(all_sessions, public_config, end_at=window_end)


def _publish_public_stats(config: Config, stats: AgentStats) -> None:
    """Publish an already-sanitized, allowlisted public snapshot."""
    import httpx

    token = config.github.token
    if not token:
        console.print("[red]No GitHub token configured. Run 'vibe-clock init' or set GITHUB_TOKEN.[/red]")
        sys.exit(1)

    payload_json = json.dumps(public_payload(stats, config), indent=2)

    gist_data = {
        "description": "vibe-clock stats — AI coding agent usage",
        "public": True,
        "files": {
            "vibe-clock-data.json": {"content": payload_json},
        },
    }

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }

    client = httpx.Client(headers=headers, timeout=30)
    gist_id = config.github.gist_id
    if gist_id:
        resp = client.patch(
            f"https://api.github.com/gists/{gist_id}",
            json=gist_data,
        )
    else:
        resp = client.post(
            "https://api.github.com/gists",
            json=gist_data,
        )

    if resp.status_code not in (200, 201):
        client.close()
        console.print(f"[red]GitHub API error ({resp.status_code}): {resp.text}[/red]")
        sys.exit(1)

    result = resp.json()
    new_gist_id = result["id"]

    if not gist_id:
        config.github.gist_id = new_gist_id
        save_config(config)
        console.print(f"[green]Created gist: {new_gist_id}[/green]")
    else:
        console.print(f"[green]Updated gist: {gist_id}[/green]")

    console.print(f"[dim]{result.get('html_url', '')}[/dim]")

    # Only dispatch when the user asked for it. This used to guess the repo as
    # <owner>/<owner> and always attempt a dispatch, which needs `repo` scope —
    # so everyone following the docs (which ask only for `gist`) saw a warning
    # on every single push, forever, about a step they never requested.
    if config.github.trigger_workflow and config.github.profile_repo:
        _trigger_render(client, config.github.profile_repo, config.github.workflow_file)

    client.close()


@cli.command()
@click.option("--dry-run", is_flag=True, help="Preview the public allowlist without pushing.")
@click.option("--days", "-d", default=None, type=click.IntRange(1, 365))
def push(dry_run: bool, days: int | None) -> None:
    """Update a public share previously enabled with `vibe-clock share`."""
    config = load_config()
    if days is not None:
        config.privacy.public_days = days

    if not dry_run and not config.privacy.public_sharing_enabled:
        console.print(
            "[yellow]Public sharing is disabled. Preview with 'vibe-clock push --dry-run', "
            "then opt in with 'vibe-clock share'.[/yellow]"
        )
        return

    stats = _collect_public_stats(config)
    if dry_run:
        console.print(preview(stats, config))
        return

    _publish_public_stats(config, stats)


def _share_options(command):
    """The five opt-in data flags, shared by `share` and `setup`."""
    for option in reversed(
        [
            click.option("--daily-activity/--no-daily-activity", default=False),
            click.option("--message-counts/--no-message-counts", default=False),
            click.option("--token-counts/--no-token-counts", default=False),
            click.option("--time-patterns/--no-time-patterns", default=False),
            click.option("--project-aliases/--no-project-aliases", default=False),
        ]
    ):
        command = option(command)
    return command


@cli.command()
@click.option("--days", default=7, type=click.IntRange(1, 365), show_default=True)
@_share_options
@click.option("--yes", "assume_yes", is_flag=True, help="Skip the confirmation prompt.")
def share(
    days: int,
    daily_activity: bool,
    message_counts: bool,
    token_counts: bool,
    time_patterns: bool,
    project_aliases: bool,
    assume_yes: bool,
) -> None:
    """Explicitly opt in to a public GitHub profile share."""
    config = load_config()
    if config.github.gist_id and not config.privacy.public_sharing_enabled:
        console.print(
            "[yellow]A legacy public Gist is configured. Run 'vibe-clock unshare' first "
            "to delete its revision history, then run 'vibe-clock share' again.[/yellow]"
        )
        return
    config.privacy.public_days = days
    config.privacy.share_daily_activity = daily_activity
    config.privacy.share_message_counts = message_counts
    config.privacy.share_token_counts = token_counts
    config.privacy.share_time_patterns = time_patterns
    config.privacy.share_project_aliases = project_aliases

    stats = _collect_public_stats(config)
    console.print(preview(stats, config))
    if not assume_yes and not click.confirm(
        "Publish this snapshot to a public GitHub Gist? Updates remain in Gist revision history"
    ):
        console.print("[yellow]Public sharing remains disabled.[/yellow]")
        return

    config.privacy.public_sharing_enabled = True
    _publish_public_stats(config, stats)
    save_config(config)
    console.print("[green]Public sharing enabled. Future scheduled pushes use this allowlist.[/green]")


@cli.command()
@click.option("--yes", "assume_yes", is_flag=True, help="Skip the confirmation prompt.")
def unshare(assume_yes: bool) -> None:
    """Delete the public Gist and disable future public updates."""
    import httpx

    config = load_config()
    gist_id = config.github.gist_id
    if not gist_id:
        config.privacy.public_sharing_enabled = False
        save_config(config)
        console.print("[yellow]No public Gist is configured. Public sharing is disabled.[/yellow]")
        return
    if not config.github.token:
        console.print("[red]No GitHub token configured; cannot delete the public Gist.[/red]")
        sys.exit(1)
    if not assume_yes and not click.confirm(
        "Delete the public Gist and all of its revisions? Profile SVG commits are not removed"
    ):
        return

    response = httpx.delete(
        f"https://api.github.com/gists/{gist_id}",
        headers={
            "Authorization": f"token {config.github.token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=30,
    )
    if response.status_code not in (204, 404):
        console.print(f"[red]GitHub API error ({response.status_code}): {response.text}[/red]")
        sys.exit(1)

    config.github.gist_id = ""
    config.privacy.public_sharing_enabled = False
    save_config(config)
    console.print("[green]Public Gist deleted and future public updates disabled.[/green]")


@cli.command()
@click.option(
    "--interval",
    type=click.Choice(["hourly", "daily", "weekly"]),
    default="daily",
    help="How often to push stats.",
)
@click.option("--time", "run_time", default=None, help="Time of day to run (HH:MM, 24h). Defaults to local equivalent of 00:00 UTC. Ignored for hourly.")
@click.option("--force", is_flag=True, help="Overwrite existing schedule.")
def schedule(interval: str, run_time: str | None, force: bool) -> None:
    """Schedule automatic vibe-clock push."""
    config = load_config()

    if not config.github.token:
        console.print("[red]No GitHub token configured. Run 'vibe-clock setup' first.[/red]")
        sys.exit(1)
    if not config.privacy.public_sharing_enabled:
        console.print("[yellow]Run 'vibe-clock share' before scheduling public updates.[/yellow]")
        return

    _install_schedule(config, interval, run_time, force=force)


def _install_schedule(
    config: Config, interval: str, run_time: str | None, *, force: bool
) -> None:
    """Install the periodic local push on whichever backend this OS provides."""
    from .scheduler import get_scheduler, resolve_binary

    if run_time is None:
        # Default to the local wall-clock time of 00:00 UTC, so the push lands
        # just before the workflow's own 00:30 UTC render.
        utc_midnight = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        run_time = utc_midnight.astimezone().strftime("%H:%M")

    try:
        datetime.strptime(run_time, "%H:%M")
    except ValueError:
        console.print("[red]Invalid time format. Use HH:MM (e.g. 08:00, 23:30).[/red]")
        sys.exit(1)

    try:
        scheduler = get_scheduler()
    except RuntimeError as exc:
        # Windows has no backend. Say so, and say what to do instead, rather
        # than dying on an unhandled traceback.
        console.print(f"[yellow]{exc}[/yellow]")
        console.print(
            "[dim]On Windows, run vibe-clock inside WSL, or create a Task "
            "Scheduler task that runs `vibe-clock push` daily.[/dim]"
        )
        return

    if scheduler.is_scheduled() and not force:
        console.print(
            f"[yellow]Already scheduled via {scheduler.backend_name}. "
            f"Use --force to overwrite.[/yellow]"
        )
        return

    if scheduler.is_scheduled():
        scheduler.unschedule()

    binary = resolve_binary()
    verify_cmd = scheduler.schedule(binary, interval, run_time)

    config.schedule.enabled = True
    config.schedule.interval = interval
    config.schedule.time = run_time
    config.schedule.backend = scheduler.backend_name
    save_config(config)

    time_msg = "" if interval == "hourly" else f" at {run_time}"
    console.print(
        f"  [green]✓[/green] Scheduled {interval} push{time_msg} via {scheduler.backend_name}"
    )
    console.print(f"  [dim]Verify: {verify_cmd}[/dim]")
    if scheduler.backend_name == "systemd":
        # A user timer is suspended when the user logs out unless lingering is
        # on, which silently freezes the profile on a headless box.
        console.print(
            "  [dim]If this machine has no permanent login session, enable "
            "lingering so the timer runs anyway: "
            "sudo loginctl enable-linger $USER[/dim]"
        )


@cli.command()
def unschedule() -> None:
    """Remove scheduled vibe-clock push."""
    from .scheduler import get_scheduler

    config = load_config()
    scheduler = get_scheduler()

    if not scheduler.is_scheduled():
        console.print("[yellow]No active schedule found.[/yellow]")
        return

    scheduler.unschedule()

    config.schedule.enabled = False
    config.schedule.backend = ""
    save_config(config)

    console.print(f"[green]Unscheduled vibe-clock push ({scheduler.backend_name}).[/green]")


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------


def _confirm(question: str, assume_yes: bool, *, default: bool = True) -> bool:
    """Ask before every remote or system mutation. `--yes` answers all of them."""
    if assume_yes:
        console.print(f"  [dim]{question} — yes (--yes)[/dim]")
        return True
    return click.confirm(question, default=default)


def _step(number: int, title: str) -> None:
    console.print(f"\n[bold cyan]{number}.[/bold cyan] [bold]{title}[/bold]")


def _resolve_token(config: Config, assume_yes: bool) -> str:
    """Find a GitHub token, preferring one `gh` already holds."""
    if config.github.token:
        console.print(
            "  [green]✓[/green] Using the token already configured "
            f"({CONFIG_PATH}, or $GITHUB_TOKEN)"
        )
        return config.github.token

    if gh.is_available():
        scopes = gh.scopes()
        token = gh.token()
        if token:
            if scopes and "gist" not in scopes:
                console.print(
                    "  [yellow]![/yellow] Your `gh` token has scopes "
                    f"{sorted(scopes)} but not `gist`, which is required to "
                    "create the Gist. Run: gh auth refresh -s gist"
                )
            else:
                console.print(
                    "  [green]✓[/green] Borrowed a token from `gh auth` — no PAT to mint.\n"
                    f"  [dim]It is stored in {CONFIG_PATH} (0600), because the "
                    "scheduled push runs without your shell's PATH and cannot "
                    "call `gh` itself.[/dim]"
                )
                return token

    console.print(
        "  No `gh` login found. Create a [bold]Classic[/bold] token at\n"
        "  [link]https://github.com/settings/tokens/new?scopes=gist&description=vibe-clock[/link]\n"
        "  and tick [bold]gist[/bold]. Fine-grained tokens cannot write Gists."
    )
    if assume_yes:
        raise click.ClickException(
            "no GitHub token available and --yes cannot prompt for one. "
            "Set GITHUB_TOKEN, or run `gh auth login -s gist`."
        )
    token = click.prompt("  Paste the token", default="", show_default=False, hide_input=True)
    if not token:
        raise click.ClickException("a GitHub token is required to publish the Gist")
    return token


def _resolve_profile_repo(config: Config, given: str | None, assume_yes: bool) -> str:
    """Decide which repo renders the SVGs. Suggested, never silently assumed.

    Guessing `<login>/<login>` without asking is how `push` ended up warning
    about a repo the user had never named.
    """
    if given:
        return _valid_slug(given)

    suggestion = config.github.profile_repo
    if not suggestion:
        login = gh.login()
        if login:
            suggestion = f"{login}/{login}"
            console.print(f"  [dim]`gh` says you are {login}[/dim]")

    if assume_yes:
        if not suggestion:
            raise click.ClickException(
                "could not determine your profile repo. Pass --profile-repo owner/repo."
            )
        return _valid_slug(suggestion)

    answer = click.prompt(
        "  Profile repo (owner/repo)",
        default=suggestion or None,
        show_default=bool(suggestion),
    )
    return _valid_slug(answer)


def _valid_slug(value: str) -> str:
    value = value.strip()
    if value.count("/") != 1 or not all(value.split("/")):
        raise click.ClickException(f"profile repo must look like owner/repo, got {value!r}")
    return value


def _chart_names(charts: str) -> list[str]:
    """Parse and validate a --charts list."""
    names = [t.strip() for t in charts.split(",") if t.strip()]
    if not names:
        raise click.ClickException("--charts must name at least one chart")
    unknown = [n for n in names if n not in SVG_RENDERERS]
    if unknown:
        raise click.ClickException(
            f"unknown chart type(s): {', '.join(unknown)}. Valid: {', '.join(SVG_RENDERERS)}."
        )
    return names


def _unshared_chart_data(names: list[str], privacy) -> list[str]:
    """Charts among `names` whose data these privacy settings never publish."""
    return [
        f"chart '{n}' needs {req.label}; add {req.flag}"
        for n in names
        for req in SVG_RENDERERS[n][2]
        if not getattr(privacy, req.privacy_attr)
    ]


def _git_slug(path: Path) -> str | None:
    """The owner/repo of the git checkout at `path`, if it is one."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "-C", str(path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip().removesuffix(".git")
    if ":" in url and "//" not in url:  # git@github.com:owner/repo
        url = url.split(":", 1)[1]
    parts = [p for p in url.split("/") if p]
    return "/".join(parts[-2:]) if len(parts) >= 2 else None


def _install_workflow(profile_repo: str, charts: str, assume_yes: bool) -> None:
    """Write the workflow into the profile repo checkout, or print it."""
    yaml = workflow_yaml(chart_types=charts)
    cwd = Path.cwd()
    in_profile_repo = _git_slug(cwd) == profile_repo
    if in_profile_repo:
        target = cwd / WORKFLOW_PATH
        action = "Overwrite" if target.exists() else "Write"
        if _confirm(f"  {action} {target}?", assume_yes):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(yaml)
            console.print(f"  [green]✓[/green] {target} — commit and push it")
            return
    else:
        # Say why, at the moment it matters. Run from $HOME — the obvious place
        # right after `uv tool install` — setup otherwise quietly prints YAML
        # where the docs said a file would be written, with no hint that
        # standing in the repo is what makes the difference.
        console.print(
            f"  [dim]This is not a {profile_repo} checkout, so no file is written. "
            f"`cd` there and re-run to have it written for you.[/dim]"
        )
    console.print(
        f"  Create [bold]{WORKFLOW_PATH}[/bold] in {profile_repo} with:\n"
        "  [dim](or run `vibe-clock workflow` from inside that checkout)[/dim]"
    )
    console.print(yaml)


@cli.command()
@click.option("--profile-repo", default=None, help="owner/repo whose Actions render your SVGs.")
@click.option("--days", default=7, type=click.IntRange(1, 365), show_default=True)
@_share_options
@click.option(
    "--charts",
    default=DEFAULT_CHART_TYPES,
    show_default=True,
    help="Charts the workflow should generate.",
)
@click.option("--no-schedule", is_flag=True, help="Skip installing the local scheduled push.")
@click.option("--yes", "assume_yes", is_flag=True, help="Accept every prompt (non-interactive).")
def setup(
    profile_repo: str | None,
    days: int,
    daily_activity: bool,
    message_counts: bool,
    token_counts: bool,
    time_patterns: bool,
    project_aliases: bool,
    charts: str,
    no_schedule: bool,
    assume_yes: bool,
) -> None:
    """Set up everything: detect agents, publish the Gist, wire up Actions.

    Replaces a thirteen-step manual walkthrough. Every step that changes
    something outside this machine asks first.
    """
    config = load_config()

    _step(1, "Detect agents")
    config.enabled_agents = _detect_agents(config)
    if not config.enabled_agents:
        raise click.ClickException(
            "no agent data directories found. Use one of Claude Code, Codex, "
            "Gemini CLI, or OpenCode first, or set [paths] in your config."
        )

    _step(2, "GitHub credentials")
    config.github.token = _resolve_token(config, assume_yes)

    _step(3, "Profile repo")
    config.github.profile_repo = _resolve_profile_repo(config, profile_repo, assume_yes)
    console.print(f"  [green]✓[/green] {config.github.profile_repo}")

    _step(4, "Choose what to publish")
    config.privacy.public_days = days
    config.privacy.share_daily_activity = daily_activity
    config.privacy.share_message_counts = message_counts
    config.privacy.share_token_counts = token_counts
    config.privacy.share_time_patterns = time_patterns
    config.privacy.share_project_aliases = project_aliases
    # Catching this now beats letting the workflow fail on its first run — or,
    # worse, drawing an empty chart from data that was never shared. Here the
    # config being checked is definitely the one this machine will push with.
    problems = _unshared_chart_data(_chart_names(charts), config.privacy)
    if problems:
        raise click.ClickException(
            "\n".join(problems) + "\n(or drop those charts from --charts)"
        )

    if config.github.gist_id and not config.privacy.public_sharing_enabled:
        raise click.ClickException(
            "a Gist from an older release is configured. Run `vibe-clock unshare` "
            "to delete its revision history first, then run setup again."
        )

    _step(5, "Review the exact public payload")
    stats = _collect_public_stats(config)
    console.print(preview(stats, config))
    if not _confirm("  Publish this to a public GitHub Gist?", assume_yes):
        console.print("[yellow]Nothing published. Config left unchanged.[/yellow]")
        return

    config.privacy.public_sharing_enabled = True
    _publish_public_stats(config, stats)
    save_config(config)

    _step(6, "Tell your profile repo the Gist ID")
    gist_id = config.github.gist_id
    if gh.is_available() and _confirm(
        f"  Set secret VIBE_CLOCK_GIST_ID on {config.github.profile_repo} via gh?", assume_yes
    ):
        ok, message = gh.set_secret(config.github.profile_repo, "VIBE_CLOCK_GIST_ID", gist_id)
        console.print(
            f"  [green]✓[/green] {message}" if ok else f"  [yellow]![/yellow] {message}"
        )
        if not ok:
            _print_manual_secret(config.github.profile_repo, gist_id)
    else:
        _print_manual_secret(config.github.profile_repo, gist_id)

    _step(7, "Install the render workflow")
    _install_workflow(config.github.profile_repo, charts, assume_yes)

    _step(8, "Keep the Gist fresh")
    if no_schedule:
        console.print("  [dim]Skipped. Run `vibe-clock schedule` when you want it.[/dim]")
    elif _confirm("  Install a daily local `vibe-clock push`?", assume_yes):
        _install_schedule(config, "daily", None, force=True)
    else:
        console.print(
            "  [dim]Without it the Gist never updates and your profile freezes. "
            "Run `vibe-clock schedule` later.[/dim]"
        )

    _step(9, "Add the charts to your README")
    console.print(readme_snippet(charts))
    console.print(
        f"\n[green]Done.[/green] Commit {WORKFLOW_PATH} and your README to "
        f"{config.github.profile_repo}, then run the workflow once from its Actions tab."
    )


def _print_manual_secret(profile_repo: str, gist_id: str) -> None:
    console.print(
        f"  Add a repository secret to {profile_repo} by hand:\n"
        f"  [link]https://github.com/{profile_repo}/settings/secrets/actions/new[/link]\n"
        f"    Name:  VIBE_CLOCK_GIST_ID\n"
        f"    Value: {gist_id}"
    )


@cli.command()
@click.option(
    "--charts",
    default=DEFAULT_CHART_TYPES,
    show_default=True,
    help="Charts the workflow should generate.",
)
@click.option("--write", is_flag=True, help=f"Write {WORKFLOW_PATH} instead of printing it.")
def workflow(charts: str, write: bool) -> None:
    """Print the GitHub Actions workflow to install in your profile repo."""
    names = _chart_names(charts)
    # A warning rather than an error: the machine printing a workflow file is
    # not necessarily the machine that pushes, so this config may not be the
    # one that decides. Say which config was consulted.
    problems = _unshared_chart_data(names, load_config().privacy)
    for problem in problems:
        err_console.print(f"[yellow]![/yellow] {problem}")
    if problems:
        err_console.print(
            f"[dim]  (checked {CONFIG_PATH} on this machine; the workflow will "
            "fail unless the machine that pushes shares this data)[/dim]"
        )
    yaml = workflow_yaml(chart_types=charts)
    if not write:
        click.echo(yaml, nl=False)
        return
    target = Path(WORKFLOW_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml)
    console.print(f"[green]Wrote {target}[/green] — commit it to your profile repo.")
