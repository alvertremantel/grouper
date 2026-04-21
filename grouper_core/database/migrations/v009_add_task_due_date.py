"""v009 — Add due_date column to tasks."""

import sqlite3

VERSION = 9
DESCRIPTION = "Add due_date to tasks"


def upgrade(conn: sqlite3.Connection) -> None:
    columns = [r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
    if "due_date" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN due_date TEXT")
    conn.commit()
