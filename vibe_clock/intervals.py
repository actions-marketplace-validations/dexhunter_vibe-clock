"""Active-time intervals — the one definition of "time spent" in vibe-clock.

An agent log is a stream of event timestamps, not a stopwatch. Measuring a
session as ``last_timestamp - first_timestamp`` bills every idle minute as
usage: an overnight break, a lunch, or a long-lived CLI process that stayed
open for weeks all become "time spent". Two sessions running side by side get
counted twice for the same wall-clock minute.

Instead:

1. Consecutive events belong to the same active stretch while the silence
   between them stays under ``IDLE_THRESHOLD_MINUTES``.
2. Stretches are *unioned* — never summed — before they are reported, so one
   wall-clock minute is one minute no matter how many agents were running.

Every collector and the aggregator go through this module, so all four agents
mean the same thing by "active".
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

Interval = tuple[datetime, datetime]

# Silence longer than this ends an active stretch.
#
# Justification: while a turn is actually running, every supported agent writes
# a record every few seconds — Codex emits a `token_count` event per turn plus
# patch/tool/sub-agent events, Claude Code writes an assistant record per tool
# call, OpenCode and Gemini CLI write one record per message. A gap of more
# than a few minutes therefore means nothing was running, including during
# unattended autonomous work.
#
# The exact value is deliberately not load-bearing: measured against real logs,
# the reported daily average moves only from 11.2 h/day at 5 minutes to
# 12.5 h/day at 30 minutes, so no plausible choice of threshold changes the
# picture. 5 minutes is the most conservative of those.
IDLE_THRESHOLD_MINUTES = 5.0


def as_utc(value: datetime) -> datetime:
    """Normalize to UTC; a naive timestamp is read as UTC rather than local."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def intervals_from_timestamps(
    timestamps: Iterable[datetime],
    idle_threshold_minutes: float = IDLE_THRESHOLD_MINUTES,
) -> list[Interval]:
    """Group event timestamps into active stretches split by idle gaps."""
    ordered = sorted(as_utc(ts) for ts in timestamps)
    if not ordered:
        return []

    gap = timedelta(minutes=idle_threshold_minutes)
    stretches: list[Interval] = []
    start = previous = ordered[0]
    for ts in ordered[1:]:
        if ts - previous > gap:
            stretches.append((start, previous))
            start = ts
        previous = ts
    stretches.append((start, previous))
    return stretches


def merge_intervals(intervals: Iterable[Interval]) -> list[Interval]:
    """Union overlapping or touching intervals, so overlap is counted once."""
    ordered = sorted(
        (as_utc(start), as_utc(end)) for start, end in intervals if end >= start
    )
    merged: list[Interval] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def clip_intervals(
    intervals: Iterable[Interval], start: datetime, end: datetime
) -> list[Interval]:
    """Trim intervals to the ``[start, end)`` window, dropping those outside it.

    Clipping (rather than filtering whole sessions by their start time) keeps
    the in-window part of a session that began before the window opened.
    """
    window_start = as_utc(start)
    window_end = as_utc(end)
    clipped: list[Interval] = []
    for raw_start, raw_end in intervals:
        interval_start = as_utc(raw_start)
        interval_end = as_utc(raw_end)
        if interval_end < window_start or interval_start >= window_end:
            continue
        clipped.append((max(interval_start, window_start), min(interval_end, window_end)))
    return clipped


def total_minutes(intervals: Iterable[Interval]) -> float:
    """Minutes covered by already-merged intervals."""
    return sum((end - start).total_seconds() for start, end in intervals) / 60.0


def union_minutes(intervals: Iterable[Interval]) -> float:
    """Wall-clock minutes covered by intervals, counting overlap once."""
    return total_minutes(merge_intervals(intervals))


def longest_stretch_minutes(intervals: Iterable[Interval]) -> float:
    """Length of the longest uninterrupted active stretch."""
    merged = merge_intervals(intervals)
    if not merged:
        return 0.0
    return max((end - start).total_seconds() for start, end in merged) / 60.0


def minutes_by_utc_day(intervals: Iterable[Interval]) -> dict[date, float]:
    """Split intervals at UTC midnight so no day can exceed 1440 minutes."""
    per_day: dict[date, float] = defaultdict(float)
    for start, end in merge_intervals(intervals):
        cursor = start
        while True:
            day = cursor.date()
            day_end = datetime.combine(
                day + timedelta(days=1), time.min, tzinfo=timezone.utc
            )
            piece_end = min(end, day_end)
            per_day[day] += (piece_end - cursor).total_seconds() / 60.0
            if piece_end >= end:
                break
            cursor = piece_end
    return dict(per_day)
