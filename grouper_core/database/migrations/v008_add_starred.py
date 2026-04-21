"""v008 — Add is_starred column to projects and tasks."""

import sqlite3

VERSION = 8
DESCRIPTION = "Add is_starred to projects and tasks"


def upgrade(conn: sqlite3.Connection) -> None:
    for table in ("projects", "tasks"):
        columns = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if "is_starred" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN is_starred INTEGER DEFAULT 0")
    conn.commit()
