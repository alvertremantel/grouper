"""
events.py — CRUD operations for Event objects.

Recurring events are stored once with an RRULE string (RFC 5545).
list_events_for_range() expands recurrences at query time using
python-dateutil so no pre-materialised rows are ever written.
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timedelta

from dateutil.rrule import rrulestr

from ..models import Event
from .connection import get_connection

logger = logging.getLogger(__name__)


def create_event(
    calendar_id: int,
    title: str,
    start_dt: datetime,
    end_dt: datetime,
    *,
    description: str = "",
    location: str = "",
    all_day: bool = False,
    color: str | None = None,
    recurrence_rule: str = "",
    recurrence_end_dt: datetime | None = None,
    linked_activity_id: int | None = None,
    linked_task_id: int | None = None,
) -> Event:
    """Insert a new event and return it with its generated id."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO events (
                calendar_id, title, description, location,
                start_dt, end_dt, all_day, color,
                recurrence_rule, recurrence_end_dt,
                linked_activity_id, linked_task_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                calendar_id,
                title,
                description,
                location,
                start_dt.isoformat(),
                end_dt.isoformat(),
                int(all_day),
                color,
                recurrence_rule,
                recurrence_end_dt.isoformat() if recurrence_end_dt else None,
                linked_activity_id,
                linked_task_id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM events WHERE id = ?", (cur.lastrowid,)).fetchone()
        return Event.from_row(row)


def get_event(event_id: int) -> Event | None:
    """Return a single Event by id, or None."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return Event.from_row(row) if row else None


def get_event_for_task(task_id: int) -> Event | None:
    """Return the event linked to a task, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM events WHERE linked_task_id = ? LIMIT 1",
            (task_id,),
        ).fetchone()
        return Event.from_row(row) if row else None


def update_event(event_id: int, *, _from_task_sync: bool = False, **kwargs) -> None:
    """Update allowed fields on an event.

    Allowed keys match Event fields: title, description, location, calendar_id,
    start_dt, end_dt, all_day, color, recurrence_rule, recurrence_end_dt,
    linked_activity_id, linked_task_id.

    When _from_task_sync is True, the cross-sync to the linked task is skipped
    (prevents infinite recursion).
    """
    allowed = {
        "title",
        "description",
        "location",
        "calendar_id",
        "start_dt",
        "end_dt",
        "all_day",
        "color",
        "recurrence_rule",
        "recurrence_end_dt",
        "linked_activity_id",
        "linked_task_id",
    }
    updates: dict = {}
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        if isinstance(v, datetime):
            updates[k] = v.isoformat()
        elif k == "all_day":
            updates[k] = int(v)
        else:
            updates[k] = v

    if not updates:
        return

    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = [*updates.values(), event_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE events SET {set_clause} WHERE id = ?", values)
        conn.commit()

    # Sync start_dt change to linked task's due_date
    if not _from_task_sync and "start_dt" in kwargs:
        event = get_event(event_id)
        if event and event.linked_task_id is not None:
            new_start = kwargs["start_dt"]
            if isinstance(new_start, str):
                new_start = datetime.fromisoformat(new_start)
            from .tasks import update_task

            update_task(
                event.linked_task_id,
                due_date=new_start,
                _from_event_sync=True,
            )


def delete_event(event_id: int) -> None:
    """Hard-delete an event (and its exceptions via CASCADE).

    If the event has a linked_task_id, the linked task's due_date is cleared.
    """
    event = get_event(event_id)
    with get_connection() as conn:
        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        conn.commit()
    if event and event.linked_task_id is not None:
        from .tasks import update_task

        update_task(event.linked_task_id, due_date=None, _from_event_sync=True)


def list_events_for_range(
    start: datetime,
    end: datetime,
    calendar_ids: list[int] | None = None,
) -> list[Event]:
    """Return all event instances (including recurrence expansions) in [start, end).

    For recurring events, instances are generated at query time using
    python-dateutil's rrulestr.  Cancelled occurrences (event_exceptions with
    is_cancelled=1) are excluded.
    """
    if start >= end:
        return []

    cal_filter = ""
    cal_params: list = []
    if calendar_ids is not None:
        placeholders = ",".join("?" * len(calendar_ids))
        cal_filter = f"AND calendar_id IN ({placeholders})"
        cal_params = list(calendar_ids)

    with get_connection() as conn:
        # --- Non-recurring events in range ---
        rows = conn.execute(
            f"""
            SELECT * FROM events
            WHERE recurrence_rule = ''
              AND start_dt >= ? AND start_dt < ?
              {cal_filter}
            ORDER BY start_dt
            """,
            [start.isoformat(), end.isoformat(), *cal_params],
        ).fetchall()
        results: list[Event] = [Event.from_row(r) for r in rows]

        # --- Recurring events ---
        rec_rows = conn.execute(
            f"""
            SELECT * FROM events
            WHERE recurrence_rule != ''
              {cal_filter}
            """,
            cal_params,
        ).fetchall()

        for row in rec_rows:
            event = Event.from_row(row)
            if event.start_dt is None:
                continue

            # Fetch cancelled occurrence datetimes for this event
            cancelled = {
                r["occurrence_dt"]
                for r in conn.execute(
                    "SELECT occurrence_dt FROM event_exceptions WHERE parent_event_id = ? AND is_cancelled = 1",
                    (event.id,),
                ).fetchall()
            }

            try:
                rule = rrulestr(event.recurrence_rule, dtstart=event.start_dt)
            except Exception as e:
                logger.warning("Invalid recurrence rule for event %d: %s", event.id, e)
                continue

            duration: timedelta = (
                (event.end_dt - event.start_dt) if event.end_dt else timedelta(hours=1)
            )

            for occurrence in rule.between(start, end, inc=True):
                if occurrence.isoformat() in cancelled:
                    continue
                # Shallow copy is safe: Event fields are all immutable types
                # (int, str, bool, datetime, None) — no lists or dicts.
                instance = copy.copy(event)
                instance.start_dt = occurrence
                instance.end_dt = occurrence + duration
                results.append(instance)

    results.sort(key=lambda e: e.start_dt or datetime.min)
    return results
