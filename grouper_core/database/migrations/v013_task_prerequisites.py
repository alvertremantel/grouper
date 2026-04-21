"""v013_task_prerequisites.py — Add task prerequisite relationships."""

import sqlite3

VERSION = 13
DESCRIPTION = "Add task_prerequisites table"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_prerequisites (
            task_id              INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            prerequisite_task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            created_at           TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY (task_id, prerequisite_task_id),
            CHECK (task_id != prerequisite_task_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_prereq_reverse ON task_prerequisites(prerequisite_task_id)"
    )
    conn.commit()
