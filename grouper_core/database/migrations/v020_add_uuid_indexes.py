"""v020 — add UNIQUE indexes on uuid columns for sync/CDC lookups."""

from __future__ import annotations

import sqlite3

VERSION = 20
DESCRIPTION = "add uuid unique indexes for sync"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_project_tags_uuid ON project_tags(uuid)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_task_tags_uuid ON task_tags(uuid)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_tags_uuid ON activity_tags(uuid)")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_task_prerequisites_uuid ON task_prerequisites(uuid)"
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_groups_uuid ON groups(uuid)")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_groups_uuid ON activity_groups(uuid)"
    )
    conn.commit()
