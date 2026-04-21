"""
calendars.py — CRUD operations for Calendar objects.
"""

from __future__ import annotations

import logging

from ..models import Calendar
from .connection import get_connection

logger = logging.getLogger(__name__)


def create_calendar(
    name: str,
    color: str = "#7aa2f7",
    weekly_budget_hours: float | None = None,
) -> Calendar:
    """Create a user calendar and return it with its generated id."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO calendars (name, color, type, weekly_budget_hours)
            VALUES (?, ?, 'user', ?)
            """,
            (name, color, weekly_budget_hours),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM calendars WHERE id = ?", (cur.lastrowid,)).fetchone()
        return Calendar.from_row(row)


def get_calendar(calendar_id: int) -> Calendar | None:
    """Return a single Calendar by id, or None if not found."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM calendars WHERE id = ?", (calendar_id,)).fetchone()
        return Calendar.from_row(row) if row else None


def list_calendars(
    include_archived: bool = False,
    include_system: bool = True,
) -> list[Calendar]:
    """Return all calendars matching the filters, ordered by id."""
    clauses: list[str] = []
    params: list = []

    if not include_archived:
        clauses.append("is_archived = 0")
    if not include_system:
        clauses.append("type = 'user'")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_connection() as conn:
        rows = conn.execute(f"SELECT * FROM calendars {where} ORDER BY id", params).fetchall()
        return [Calendar.from_row(r) for r in rows]


def update_calendar(calendar_id: int, **kwargs) -> None:
    """Update allowed fields on a calendar.

    Allowed keys: name, color, is_visible, weekly_budget_hours.
    System calendars may have is_visible toggled but not renamed.
    """
    allowed = {"name", "color", "is_visible", "weekly_budget_hours"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = [*updates.values(), calendar_id]
    with get_connection() as conn:
        cur = conn.execute(f"UPDATE calendars SET {set_clause} WHERE id = ?", values)
        if cur.rowcount == 0:
            logger.warning(
                "update_calendar(%d) affected 0 rows — calendar may not exist",
                calendar_id,
            )
        conn.commit()


def archive_calendar(calendar_id: int) -> None:
    """Archive a user calendar (hide from view, data preserved)."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE calendars SET is_archived = 1 WHERE id = ? AND type = 'user'",
            (calendar_id,),
        )
        conn.commit()


def get_default_calendar_id() -> int:
    """Return the id of the user's default calendar (fallback: 3 = Personal)."""
    default_id = 3
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'default_calendar_id'"
        ).fetchone()
        if row:
            try:
                return int(row["value"])
            except (ValueError, TypeError):
                logger.warning(
                    "Could not parse default_calendar_id setting %r; falling back to calendar %d",
                    row["value"],
                    default_id,
                )
        else:
            logger.debug(
                "No default_calendar_id in settings; using fallback calendar %d",
                default_id,
            )
        return default_id


def set_default_calendar(calendar_id: int) -> None:
    """Persist the user's default calendar choice."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('default_calendar_id', ?)",
            (str(calendar_id),),
        )
        conn.commit()
