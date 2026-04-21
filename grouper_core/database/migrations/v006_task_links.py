"""v006_task_links.py — Add task links table."""

import sqlite3

VERSION = 6
DESCRIPTION = "Add task links table"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_links (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id    INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            label      TEXT,
            url        TEXT NOT NULL,
            link_type  TEXT NOT NULL DEFAULT 'url',
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_links_task ON task_links(task_id)")

    conn.commit()
