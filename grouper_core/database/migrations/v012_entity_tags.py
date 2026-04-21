"""v012_entity_tags.py — Add tag junction tables for tasks and activities."""

import sqlite3

VERSION = 12
DESCRIPTION = "Add task_tags and activity_tags junction tables"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_tags (
            task_id    INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            tag_id     INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY (task_id, tag_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_tags (
            activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
            tag_id      INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY (activity_id, tag_id)
        )
    """)

    conn.commit()
