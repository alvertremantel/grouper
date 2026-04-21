"""v003_soft_delete_activities.py — Add soft-delete columns to activities."""

import sqlite3

VERSION = 3
DESCRIPTION = "Add soft-delete columns to activities"


def upgrade(conn: sqlite3.Connection) -> None:
    cursor = conn.execute("PRAGMA table_info(activities)")
    columns = [col["name"] for col in cursor.fetchall()]
    if "is_deleted" not in columns:
        conn.execute("ALTER TABLE activities ADD COLUMN is_deleted INTEGER DEFAULT 0")
    if "deleted_at" not in columns:
        conn.execute("ALTER TABLE activities ADD COLUMN deleted_at TEXT")

    conn.commit()
