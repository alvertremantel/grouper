"""v010 — Upgrade tasks table: add priority, completion/deletion columns."""

import sqlite3

VERSION = 10
DESCRIPTION = "Upgrade tasks schema (priority, is_completed, is_deleted, timestamps)"


def upgrade(conn: sqlite3.Connection) -> None:
    columns = [r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]

    additions: list[tuple[str, str]] = [
        ("priority", "INTEGER DEFAULT 0"),
        ("is_completed", "INTEGER DEFAULT 0"),
        ("is_deleted", "INTEGER DEFAULT 0"),
        ("completed_at", "TEXT"),
        ("deleted_at", "TEXT"),
    ]
    for col, typedef in additions:
        if col not in columns:
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {typedef}")

    # Migrate legacy 'status' data if the column exists
    if "status" in columns:
        conn.execute("UPDATE tasks SET is_completed = 1 WHERE status = 'done'")
        conn.execute("UPDATE tasks SET is_deleted = 1 WHERE status = 'cancelled'")

    conn.commit()
