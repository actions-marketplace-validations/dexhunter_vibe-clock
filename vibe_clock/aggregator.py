"""Aggregate sessions into AgentStats."""

from __future__ import annotations

import fnmatch
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from .config import Config
from .intervals import (
    Interval,
    clip_intervals,
    longest_stretch_minutes,
    minutes_by_utc_day,
    union_minutes,
)
from .models import (
    AgentStats,
    DailyActivity,
    ModelBreakdown,
    ProjectBreakdown,
    Session,
    TokenUsage,
)


def aggregate(
    sessions: list[Session],
    config: Config,
    *,
    end_at: datetime | None = None,
) -> AgentStats:
    """Aggregate raw sessions into AgentStats, applying privacy filters.

    Minutes are wall-clock active time: each session's active stretches are
    clipped to the window and then unioned, so overlapping sessions cost one
    minute, not two. Per-model and per-project minutes are unioned within their
    own group, so they legitimately do not add up to ``total_minutes`` when two
    groups were active at the same moment.
    """
    days = config.default_days
    window_end = end_at or datetime.now(timezone.utc)
    cutoff = window_end - timedelta(days=days)

    filtered = list(sessions)

    # Filter excluded date ranges
    for dr in config.privacy.exclude_date_ranges:
        if len(dr) == 2:
            try:
                start = date.fromisoformat(dr[0])
                end = date.fromisoformat(dr[1])
                filtered = [
                    s
                    for s in filtered
                    if not (start <= s.start_time.date() <= end)
                ]
            except ValueError:
                continue

    # Filter excluded projects
    if config.privacy.exclude_projects:
        filtered = [
            s
            for s in filtered
            if not _is_excluded(s.project, config.privacy.exclude_projects)
        ]

    # Clip every session's active stretches to the window instead of dropping
    # whole sessions by start time — a session that opened before the window
    # still spent real minutes inside it.
    windowed: list[tuple[Session, list[Interval]]] = []
    for s in filtered:
        in_window = clip_intervals(s.active_intervals, cutoff, window_end)
        if in_window:
            windowed.append((s, in_window))

    if not windowed:
        return AgentStats(days_covered=days)

    # Group by date
    daily_map: dict[date, _DailyAcc] = defaultdict(_DailyAcc)
    model_map: dict[str, _ModelAcc] = defaultdict(_ModelAcc)
    project_map: dict[tuple[str, str], _ProjectAcc] = defaultdict(_ProjectAcc)
    hour_counts: dict[int, int] = defaultdict(int)
    agents_seen: set[str] = set()
    all_intervals: list[Interval] = []

    total_tokens = TokenUsage()
    total_messages = 0

    for s, in_window in windowed:
        # The first in-window stretch, not the raw start time, which may sit
        # outside the window entirely.
        d = in_window[0][0].date()

        # Daily
        acc = daily_map[d]
        acc.session_count += 1
        acc.message_count += s.message_count
        _add_tokens(acc.tokens, s.tokens)

        # Model-level activity stays attached to the session's primary model,
        # while collectors that provide per-model token splits keep tokens on
        # the model that actually consumed them.
        macc = model_map[s.model]
        macc.session_count += 1
        macc.message_count += s.message_count
        macc.intervals.extend(in_window)
        if s.model_tokens:
            for model, tokens in s.model_tokens.items():
                _add_tokens(model_map[model].tokens, tokens)
        else:
            _add_tokens(macc.tokens, s.tokens)

        # Project
        key = (s.project, s.agent)
        pacc = project_map[key]
        pacc.session_count += 1
        pacc.intervals.extend(in_window)
        _add_tokens(pacc.tokens, s.tokens)

        # Totals
        _add_tokens(total_tokens, s.tokens)
        total_messages += s.message_count
        hour_counts[in_window[0][0].hour] += 1
        agents_seen.add(s.agent)
        all_intervals.extend(in_window)

    # Minutes are unioned across every session before being reported, so two
    # agents running at once cost one wall-clock minute, not two. Splitting the
    # union at UTC midnight is what keeps a day from exceeding 1440 minutes.
    daily_minutes = minutes_by_utc_day(all_intervals)
    for d in daily_minutes:
        # A day that only holds spill-over minutes is still an active day.
        daily_map.setdefault(d, _DailyAcc())

    # Build hourly distribution (24 slots)
    hourly = [hour_counts.get(h, 0) for h in range(24)]

    # Find peak hour
    peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else 0  # type: ignore[arg-type]

    # Find favorite model
    favorite = max(model_map, key=lambda m: model_map[m].session_count) if model_map else ""

    # Build daily list sorted by date
    daily = sorted(
        [
            DailyActivity(
                date=d,
                session_count=a.session_count,
                message_count=a.message_count,
                total_minutes=round(daily_minutes.get(d, 0.0), 1),
                tokens=a.tokens,
            )
            for d, a in daily_map.items()
        ],
        key=lambda x: x.date,
    )

    models = sorted(
        [
            ModelBreakdown(
                model=m,
                session_count=a.session_count,
                message_count=a.message_count,
                total_minutes=round(union_minutes(a.intervals), 1),
                tokens=a.tokens,
            )
            for m, a in model_map.items()
        ],
        key=lambda x: x.session_count,
        reverse=True,
    )

    projects = sorted(
        [
            ProjectBreakdown(
                project=proj,
                agent=agent,
                session_count=a.session_count,
                total_minutes=round(union_minutes(a.intervals), 1),
                tokens=a.tokens,
            )
            for (proj, agent), a in project_map.items()
        ],
        key=lambda x: x.total_minutes,
        reverse=True,
    )

    return AgentStats(
        days_covered=days,
        active_days=len(daily),
        total_sessions=len(windowed),
        total_messages=total_messages,
        total_minutes=round(union_minutes(all_intervals), 1),
        total_tokens=total_tokens,
        active_agents=sorted(agents_seen),
        favorite_model=favorite,
        peak_hour=peak_hour,
        longest_stretch_minutes=round(longest_stretch_minutes(all_intervals), 1),
        hourly=hourly,
        daily=daily,
        models=models,
        projects=projects,
    )


def _is_excluded(project: str, patterns: list[str]) -> bool:
    """Whether a project matches an `exclude_projects` entry.

    A pattern matches either as a shell glob or as a plain substring, and case
    is ignored. This is the escape hatch for keeping a client or an NDA repo out
    of your stats, so it has to work the obvious way: glob-only matching meant
    `exclude_projects = ["acme"]` silently excluded nothing unless a project was
    named exactly `acme`, and silence is the worst possible answer here.
    Accepting both forms can only ever exclude more, never less.
    """
    haystack = project.casefold()
    return any(
        fnmatch.fnmatchcase(haystack, pattern.casefold())
        or pattern.casefold() in haystack
        for pattern in patterns
        if pattern
    )


def _add_tokens(target: TokenUsage, source: TokenUsage) -> None:
    target.input_tokens += source.input_tokens
    target.output_tokens += source.output_tokens
    target.cache_read_tokens += source.cache_read_tokens
    target.cache_write_tokens += source.cache_write_tokens


class _DailyAcc:
    def __init__(self) -> None:
        self.session_count = 0
        self.message_count = 0
        self.tokens = TokenUsage()


class _ModelAcc:
    def __init__(self) -> None:
        self.session_count = 0
        self.message_count = 0
        self.intervals: list[Interval] = []
        self.tokens = TokenUsage()


class _ProjectAcc:
    def __init__(self) -> None:
        self.session_count = 0
        self.intervals: list[Interval] = []
        self.tokens = TokenUsage()
