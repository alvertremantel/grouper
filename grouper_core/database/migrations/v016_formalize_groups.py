"""v016 — Formalize groups as first-class entities.

Moves from implicit group strings in activity_groups.group_name to a proper
groups table with id/name/created_at.  The activity_groups junction table is
rebuilt to reference group_id instead of group_name.
"""

import sqlite3

VERSION = 16
DESCRIPTION = "Formalize groups as first-class entities with groups table"


def upgrade(conn: sqlite3.Connection) -> None:
    # 1. Create the groups table
    conn.execute(
        """CREATE TABLE IF NOT EXISTS groups (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )"""
    )

    # Check if activity_groups still uses the old group_name column.
    # On fresh installs, the initial schema already has group_id — skip migration.
    columns = [r[1] for r in conn.execute("PRAGMA table_info(activity_groups)").fetchall()]
    if "group_name" not in columns:
        conn.commit()
        return

    # 2. Backfill distinct group names from existing data
    conn.execute(
        "INSERT OR IGNORE INTO groups (name) SELECT DISTINCT group_name FROM activity_groups"
    )

    # 3. Create the new junction table with group_id FK
    conn.execute(
        """CREATE TABLE activity_groups_new (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER NOT NULL,
            group_id    INTEGER NOT NULL,
            FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE,
            FOREIGN KEY (group_id)    REFERENCES groups(id)     ON DELETE CASCADE,
            UNIQUE(activity_id, group_id)
        )"""
    )

    # 4. Migrate data from old table via JOIN on name
    conn.execute(
        """INSERT OR IGNORE INTO activity_groups_new (activity_id, group_id)
           SELECT ag.activity_id, g.id
           FROM activity_groups ag
           JOIN groups g ON ag.group_name = g.name"""
    )

    # 5. Drop old table, rename new, recreate indexes
    conn.execute("DROP TABLE activity_groups")
    conn.execute("ALTER TABLE activity_groups_new RENAME TO activity_groups")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_activity_groups_activity ON activity_groups(activity_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_activity_groups_group ON activity_groups(group_id)"
    )

    conn.commit()
