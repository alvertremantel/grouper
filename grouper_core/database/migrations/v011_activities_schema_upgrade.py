"""v011 — Upgrade activities table: add description, background, archive columns."""

import sqlite3

VERSION = 11
DESCRIPTION = "Upgrade activities schema (description, is_background, is_archived, timestamps)"


def upgrade(conn: sqlite3.Connection) -> None:
    columns = [r[1] for r in conn.execute("PRAGMA table_info(activities)").fetchall()]

    additions: list[tuple[str, str]] = [
        ("description", "TEXT"),
        ("is_background", "INTEGER DEFAULT 0"),
        ("is_archived", "INTEGER DEFAULT 0"),
        ("created_at", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ("archived_at", "TEXT"),
    ]
    for col, typedef in additions:
        if col not in columns:
            conn.execute(f"ALTER TABLE activities ADD COLUMN {col} {typedef}")

    conn.commit()
