"""v017 — Add description column to tasks table."""

VERSION = 17
DESCRIPTION = "Add description field to tasks"


def upgrade(conn):  # type: ignore[no-untyped-def]
    columns = [r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
    if "description" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN description TEXT NOT NULL DEFAULT ''")
    conn.commit()
