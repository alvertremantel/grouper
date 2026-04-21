"""
sessions.py — Time tracking session operations.

Sessions belong to Activities (not Projects).  Key features:
  - start / stop / pause / resume lifecycle
  - segment splitting on stop when pause events exist
  - retroactive logging
  - summaries by activity and by day
  - midnight splitting
  - CSV export
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timedelta

from ..models import PauseEvent, Session
from .connection import get_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _record_pause_event(conn, session_id: int, event_type: str) -> PauseEvent:
    now = datetime.now()
    conn.execute(
        "INSERT INTO pause_events (session_id, event_type, event_time) VALUES (?, ?, ?)",
        (session_id, event_type, now.isoformat()),
    )
    return PauseEvent(session_id=session_id, event_type=event_type, event_time=now)


def _get_pause_events(conn, session_id: int) -> list[PauseEvent]:
    rows = conn.execute(
        "SELECT id, session_id, event_type, event_time FROM pause_events "
        "WHERE session_id = ? ORDER BY event_time",
        (session_id,),
    ).fetchall()
    return [PauseEvent.from_row(r) for r in rows]


def _get_active_periods(
    session: Session, events: list[PauseEvent], end_time: datetime | None = None
) -> list[tuple[datetime, datetime]]:
    """Compute (start, end) tuples for each active work segment."""
    end = end_time or datetime.now()
    periods: list[tuple[datetime, datetime]] = []
    seg_start = session.start_time

    for ev in events:
        if ev.event_type == "pause":
            if seg_start:
                periods.append((seg_start, ev.event_time))
                seg_start = None
        elif ev.event_type == "resume":
            seg_start = ev.event_time

    if seg_start:
        periods.append((seg_start, end))

    return periods


# ---------------------------------------------------------------------------
# Start / Stop
# ---------------------------------------------------------------------------


def start_session(activity_name: str) -> Session:
    """Begin a new timed session.  Creates the activity if it doesn't exist."""
    from .activities import get_or_create_activity

    get_or_create_activity(activity_name)

    now = datetime.now()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (activity_name, start_time) VALUES (?, ?)",
            (activity_name, now.isoformat()),
        )
        conn.commit()
    return Session(id=cur.lastrowid, activity_name=activity_name, start_time=now)


def stop_session(
    activity_name: str | None = None,
    notes: str = "",
    task_id: int | None = None,
) -> list[Session]:
    """Stop an active session, splitting into segments if pause events exist.

    If *activity_name* is None, stops the most recent active session.
    Returns the list of created segment sessions.
    """
    now = datetime.now()
    completed: list[Session] = []

    with get_connection() as conn:
        if activity_name:
            row = conn.execute(
                "SELECT * FROM sessions WHERE activity_name = ? AND end_time IS NULL "
                "ORDER BY start_time DESC LIMIT 1",
                (activity_name,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM sessions WHERE end_time IS NULL ORDER BY start_time DESC LIMIT 1",
            ).fetchone()

        if row is None:
            return []

        session = Session.from_row(row)
        events = _get_pause_events(conn, session.id)

        if not events:
            # Simple case — no pauses
            conn.execute(
                "UPDATE sessions SET end_time = ?, notes = ?, is_paused = 0, "
                "pause_started_at = NULL, task_id = ? WHERE id = ?",
                (now.isoformat(), notes, task_id, session.id),
            )
            conn.commit()
            session.end_time = now
            session.notes = notes
            session.is_paused = False
            session.task_id = task_id
            return [session]

        # Split into segments
        periods = _get_active_periods(session, events, now)
        for i, (seg_start, seg_end) in enumerate(periods):
            seg_notes = notes if i == len(periods) - 1 else ""
            cur = conn.execute(
                "INSERT INTO sessions (activity_name, start_time, end_time, notes, task_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    session.activity_name,
                    seg_start.isoformat(),
                    seg_end.isoformat(),
                    seg_notes,
                    task_id,
                ),
            )
            completed.append(
                Session(
                    id=cur.lastrowid,
                    activity_name=session.activity_name,
                    start_time=seg_start,
                    end_time=seg_end,
                    notes=seg_notes,
                    task_id=task_id,
                )
            )

        # Remove original + its pause events
        conn.execute("DELETE FROM pause_events WHERE session_id = ?", (session.id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session.id,))
        conn.commit()

    return completed


def stop_all_sessions(notes: str = "") -> list[Session]:
    """Stop every active session."""
    results: list[Session] = []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT activity_name FROM sessions WHERE end_time IS NULL"
        ).fetchall()
    for r in rows:
        results.extend(stop_session(r["activity_name"], notes))
    return results


# ---------------------------------------------------------------------------
# Pause / Resume
# ---------------------------------------------------------------------------


def pause_session(session_id: int) -> Session | None:
    now = datetime.now()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None or row["end_time"] or row["is_paused"]:
            return None
        conn.execute(
            "UPDATE sessions SET is_paused = 1, pause_started_at = ? WHERE id = ?",
            (now.isoformat(), session_id),
        )
        _record_pause_event(conn, session_id, "pause")
        conn.commit()
    return get_session_by_id(session_id)


def resume_session(session_id: int) -> Session | None:
    now = datetime.now()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None or row["end_time"] or not row["is_paused"]:
            return None

        if row["pause_started_at"]:
            paused_at = datetime.fromisoformat(row["pause_started_at"])
            extra = round((now - paused_at).total_seconds())
        else:
            # pause_started_at is NULL -- data integrity issue.  Record 0
            # pause duration rather than silently masking with `now`.
            logger.warning(
                "Session %d is_paused=1 but pause_started_at is NULL; recording 0 pause duration",
                session_id,
            )
            extra = 0
        new_total = (row["paused_seconds"] or 0) + extra

        conn.execute(
            "UPDATE sessions SET is_paused = 0, pause_started_at = NULL, "
            "paused_seconds = ? WHERE id = ?",
            (new_total, session_id),
        )
        _record_pause_event(conn, session_id, "resume")
        conn.commit()
    return get_session_by_id(session_id)


# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------


def get_active_session() -> Session | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE end_time IS NULL ORDER BY start_time DESC LIMIT 1"
        ).fetchone()
    return Session.from_row(row) if row else None


def get_active_sessions() -> list[Session]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE end_time IS NULL ORDER BY start_time DESC"
        ).fetchall()
    return [Session.from_row(r) for r in rows]


def get_active_session_by_activity(activity_name: str) -> Session | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE activity_name = ? AND end_time IS NULL "
            "ORDER BY start_time DESC LIMIT 1",
            (activity_name,),
        ).fetchone()
    return Session.from_row(row) if row else None


def get_session_by_id(session_id: int) -> Session | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return Session.from_row(row) if row else None


def get_sessions(
    activity_name: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 50,
) -> list[Session]:
    """Flexible session query with optional filters."""
    with get_connection() as conn:
        q = "SELECT s.* FROM sessions s"
        params: list = []
        conds: list[str] = ["s.end_time IS NOT NULL"]  # only completed

        if activity_name:
            conds.append("s.activity_name = ?")
            params.append(activity_name)
        if start_date:
            conds.append("s.start_time >= ?")
            params.append(start_date.isoformat())
        if end_date:
            conds.append("s.start_time < ?")
            params.append(end_date.isoformat())

        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY s.start_time DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(q, params).fetchall()
    return [Session.from_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Retroactive logging
# ---------------------------------------------------------------------------


def log_session(
    activity_name: str,
    duration: timedelta,
    notes: str = "",
    date: datetime | None = None,
) -> Session:
    """Record a session retroactively."""
    from .activities import get_or_create_activity

    get_or_create_activity(activity_name)

    end = date or datetime.now()
    start = end - duration

    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (activity_name, start_time, end_time, notes) VALUES (?, ?, ?, ?)",
            (activity_name, start.isoformat(), end.isoformat(), notes),
        )
        conn.commit()
    return Session(
        id=cur.lastrowid, activity_name=activity_name, start_time=start, end_time=end, notes=notes
    )


def delete_session(session_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

# SQL expression: active seconds = (end - start) - paused, clamped to 0.
# Equivalent to Session.duration_seconds for completed sessions (end_time IS NOT NULL).
_SQL_DURATION = (
    "MAX(CAST(strftime('%s', end_time) AS INTEGER)"
    " - CAST(strftime('%s', start_time) AS INTEGER)"
    " - COALESCE(paused_seconds, 0), 0)"
)


def get_summary(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, int]:
    """Total seconds per activity within a date range."""
    with get_connection() as conn:
        clauses = ["end_time IS NOT NULL"]
        params: list[str] = []
        if start_date is not None:
            clauses.append("start_time >= ?")
            params.append(start_date.isoformat())
        if end_date is not None:
            clauses.append("start_time < ?")
            params.append(end_date.isoformat())
        where = " AND ".join(clauses)
        rows = conn.execute(
            f"SELECT activity_name, SUM({_SQL_DURATION}) AS total_seconds "
            f"FROM sessions WHERE {where} GROUP BY activity_name",
            params,
        ).fetchall()
    return {row["activity_name"]: row["total_seconds"] for row in rows}


def get_summary_by_day(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict[str, int]]:
    """Per-activity, per-day breakdown.  Outer key = activity, inner key = date string."""
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT activity_name, date(start_time) AS day, "
            f"SUM({_SQL_DURATION}) AS total_seconds "
            f"FROM sessions "
            f"WHERE end_time IS NOT NULL AND start_time IS NOT NULL "
            f"AND start_time >= ? AND start_time < ? "
            f"GROUP BY activity_name, date(start_time)",
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
    result: dict[str, dict[str, int]] = {}
    for row in rows:
        result.setdefault(row["activity_name"], {})[row["day"]] = row["total_seconds"]
    return result


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


def split_sessions_at_midnight() -> int:
    """Split completed sessions that span midnight into per-day segments."""
    created = 0
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM sessions WHERE end_time IS NOT NULL").fetchall()

        for row in rows:
            start = datetime.fromisoformat(row["start_time"])
            end = datetime.fromisoformat(row["end_time"])
            if start.date() == end.date():
                continue  # same day

            # Split: end original at 23:59:59, create new for each subsequent day
            mid = start.replace(hour=23, minute=59, second=59)
            conn.execute(
                "UPDATE sessions SET end_time = ? WHERE id = ?",
                (mid.isoformat(), row["id"]),
            )
            cursor = mid + timedelta(seconds=1)
            while cursor.date() <= end.date():
                day_end = min(
                    cursor.replace(hour=23, minute=59, second=59),
                    end,
                )
                conn.execute(
                    "INSERT INTO sessions (activity_name, start_time, end_time, notes, task_id) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        row["activity_name"],
                        cursor.isoformat(),
                        day_end.isoformat(),
                        row["notes"],
                        row["task_id"],
                    ),
                )
                created += 1
                cursor = (cursor + timedelta(days=1)).replace(hour=0, minute=0, second=0)

        conn.commit()
    if created:
        logger.debug("Split %d session segment(s) at midnight boundaries", created)
    return created


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_sessions_csv(filepath: str) -> None:
    sessions = get_sessions(limit=100_000)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "activity", "start", "end", "duration_s", "notes"])
        for s in sessions:
            writer.writerow(
                [
                    s.id,
                    s.activity_name,
                    s.start_time.isoformat() if s.start_time else "",
                    s.end_time.isoformat() if s.end_time else "",
                    s.duration_seconds,
                    s.notes,
                ]
            )
