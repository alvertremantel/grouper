"""v002_add_boards.py — Add boards table and board_id to projects."""

import sqlite3

VERSION = 2
DESCRIPTION = "Add boards table and board_id to projects"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS boards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("INSERT OR IGNORE INTO boards (id, name) VALUES (1, 'Default Board')")

    cursor = conn.execute("PRAGMA table_info(projects)")
    columns = [col["name"] for col in cursor.fetchall()]
    if "board_id" not in columns:
        conn.execute("ALTER TABLE projects ADD COLUMN board_id INTEGER REFERENCES boards(id)")
        conn.execute("UPDATE projects SET board_id = 1 WHERE board_id IS NULL")

    conn.commit()
