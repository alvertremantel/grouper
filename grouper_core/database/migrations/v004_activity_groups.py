"""v004_activity_groups.py — Add activity groups (many-to-many)."""

import sqlite3

VERSION = 4
DESCRIPTION = "Add activity groups (many-to-many)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER NOT NULL,
            group_name TEXT NOT NULL,
            FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE,
            UNIQUE(activity_id, group_name)
        )
    """)
    # Guard index creation — column may not exist if v016 schema is already active
    columns = [r[1] for r in conn.execute("PRAGMA table_info(activity_groups)").fetchall()]
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_activity_groups_activity ON activity_groups(activity_id)"
    )
    if "group_name" in columns:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_activity_groups_name ON activity_groups(group_name)"
        )

    conn.commit()
