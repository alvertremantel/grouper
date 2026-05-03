"""formatting.py — Shared formatting and serialisation utilities.

Used by the CLI package to avoid duplicating common serialisation logic
(duration formatting, session dicts, task filtering, JSON default handlers).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .models import Session, Task

__all__ = [
    "default_json_serializer",
    "filter_upcoming_tasks",
    "format_duration",
    "format_session",
    "start_of_day",
]


def start_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def format_duration(seconds: int | float) -> str:
    """Format a number of seconds as ``Xh YYm ZZs``."""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def format_session(session: Session) -> dict[str, Any]:
    """Serialize a Session model to a plain dict with computed duration fields.

    Field names follow the canonical schema:
      - ``duration_seconds``: int
      - ``duration_formatted``: human-readable string
    """
    return {
        "id": session.id,
        "activity": session.activity_name,
        "start": session.start_time.isoformat() if session.start_time else "",
        "end": session.end_time.isoformat() if session.end_time else "",
        "paused": session.is_paused,
        "duration_seconds": session.duration_seconds,
        "duration_formatted": session.format_duration(),
        "notes": session.notes or "",
    }


def filter_upcoming_tasks(tasks: list[Task], limit: int = 10, days: int = 7) -> list[Task]:
    """Return incomplete tasks due within *days* from now, sorted by due date."""
    now = datetime.now()
    today = start_of_day(now)
    cutoff = now + timedelta(days=days)
    upcoming = [
        t
        for t in tasks
        if t.due_date is not None and today <= t.due_date <= cutoff and not t.is_completed
    ]
    upcoming.sort(key=lambda t: t.due_date)  # type: ignore[arg-type,return-value]
    return upcoming[:limit]


def default_json_serializer(obj: Any) -> str | int | float:
    """JSON default handler for datetime and timedelta objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, timedelta):
        return int(obj.total_seconds())
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")
