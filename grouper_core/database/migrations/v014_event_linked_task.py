"""v014 — Add linked_task_id column to events table."""

VERSION = 14
DESCRIPTION = "Add linked_task_id to events"


def upgrade(conn):  # type: ignore[no-untyped-def]
    columns = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
    if "linked_task_id" not in columns:
        conn.execute(
            "ALTER TABLE events ADD COLUMN linked_task_id INTEGER "
            "REFERENCES tasks(id) ON DELETE SET NULL"
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_linked_task ON events(linked_task_id)")
    conn.commit()
