"""Collector for OpenCode sessions.

Data layout:
  {data_dir}/storage/session/{projectID}/ses_*.json  — session metadata
  {data_dir}/storage/message/{sessionID}/msg_*.json  — per-message token data
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ..intervals import intervals_from_timestamps
from ..models import Session, TokenUsage
from .base import BaseCollector


class OpenCodeCollector(BaseCollector):
    agent_name = "opencode"

    def collect(self, days: int = 365) -> list[Session]:
        storage = self.data_dir / "storage"
        session_dir = storage / "session"
        message_dir = storage / "message"

        if not session_dir.exists():
            return []

        results: list[Session] = []
        for ses_file in session_dir.rglob("ses_*.json"):
            session = self._parse_session(ses_file, message_dir)
            if session is not None:
                results.append(session)
        return results

    def _parse_session(
        self, ses_path: Path, message_dir: Path
    ) -> Session | None:
        try:
            with open(ses_path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

        session_id = data.get("id")
        if not session_id:
            return None

        project = data.get("directory", "unknown")
        time_info = data.get("time", {})

        # Timestamps are Unix milliseconds
        created_ms = time_info.get("created")
        updated_ms = time_info.get("updated")
        if created_ms is None:
            return None

        start_time = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
        end_time = (
            datetime.fromtimestamp(updated_ms / 1000, tz=timezone.utc)
            if updated_ms
            else None
        )

        # Parse messages for this session
        tokens = TokenUsage()
        message_count = 0
        models: dict[str, int] = defaultdict(int)
        # `time.created`/`time.updated` on the session record span from the
        # first message to the last, idle time included. Per-message timestamps
        # are what actually show when the session was working, so the distrusted
        # session-metadata value must not be seeded in among them: doing so
        # invented a zero-length stretch on the day the session record was
        # created, which counted as a whole extra active day.
        timestamps: list[datetime] = []

        msg_session_dir = message_dir / session_id
        if msg_session_dir.exists():
            for msg_file in msg_session_dir.glob("msg_*.json"):
                try:
                    with open(msg_file) as f:
                        msg = json.load(f)
                except (OSError, json.JSONDecodeError):
                    continue

                msg_time = msg.get("time", {})
                for key in ("created", "completed"):
                    value = msg_time.get(key)
                    if value:
                        timestamps.append(
                            datetime.fromtimestamp(value / 1000, tz=timezone.utc)
                        )

                role = msg.get("role")
                if role == "user":
                    message_count += 1
                elif role == "assistant":
                    message_count += 1

                    model_id = msg.get("modelID", "unknown")
                    if model_id != "unknown":
                        models[model_id] += 1

                    tok = msg.get("tokens", {})
                    tokens.input_tokens += tok.get("input", 0)
                    tokens.output_tokens += tok.get("output", 0)

                    cache = tok.get("cache", {})
                    tokens.cache_read_tokens += cache.get("read", 0)
                    tokens.cache_write_tokens += cache.get("write", 0)

        model = "unknown"
        if models:
            model = max(models, key=models.get)  # type: ignore[arg-type]

        if not timestamps:
            # No message ever recorded a time. The session happened, but there
            # is no evidence of how long for, so it contributes a single point
            # rather than the untrusted `created`-to-`updated` span.
            timestamps = [start_time]

        intervals = intervals_from_timestamps(timestamps)
        last_event = intervals[-1][1]
        if end_time is None or last_event > end_time:
            end_time = last_event

        return Session(
            session_id=session_id,
            agent="opencode",
            start_time=start_time,
            end_time=end_time,
            model=model,
            project=project,
            message_count=message_count,
            tokens=tokens,
            active_intervals=intervals,
        )
