"""v015 — Backfill linked_task_id on legacy task-generated events.

Events created by the old task-drop handler (pre-v014) have
linked_task_id = NULL even though they were created from a task.
Match them by title + date + ~1hr duration and set the FK.
"""

VERSION = 15
DESCRIPTION = "Backfill linked_task_id on legacy task-generated events"


def upgrade(conn):  # type: ignore[no-untyped-def]
    rows = conn.execute(
        """
        SELECT e.id AS eid, t.id AS tid
        FROM events e
        JOIN tasks t ON e.title = t.title
        WHERE e.linked_task_id IS NULL
          AND t.is_deleted = 0
          AND t.due_date IS NOT NULL
          AND date(e.start_dt) = date(t.due_date)
          AND CAST(
                (julianday(e.end_dt) - julianday(e.start_dt)) * 86400
              AS INTEGER) BETWEEN 3540 AND 3660
        GROUP BY e.id
        HAVING COUNT(*) = 1
        """
    ).fetchall()
    for row in rows:
        conn.execute(
            "UPDATE events SET linked_task_id = ? WHERE id = ?",
            (row["tid"], row["eid"]),
        )
    conn.commit()
