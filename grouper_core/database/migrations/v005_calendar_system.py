"""v005_calendar_system.py — Add calendar, events, and event exceptions tables."""

import sqlite3

VERSION = 5
DESCRIPTION = "Add calendar system"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calendars (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            name                TEXT NOT NULL,
            color               TEXT NOT NULL DEFAULT '#7aa2f7',
            type                TEXT NOT NULL DEFAULT 'user',
            is_visible          INTEGER NOT NULL DEFAULT 1,
            weekly_budget_hours REAL,
            is_archived         INTEGER NOT NULL DEFAULT 0,
            created_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            calendar_id         INTEGER NOT NULL REFERENCES calendars(id) ON DELETE CASCADE,
            title               TEXT NOT NULL,
            description         TEXT NOT NULL DEFAULT '',
            location            TEXT NOT NULL DEFAULT '',
            start_dt            TEXT NOT NULL,
            end_dt              TEXT NOT NULL,
            all_day             INTEGER NOT NULL DEFAULT 0,
            color               TEXT,
            recurrence_rule     TEXT NOT NULL DEFAULT '',
            recurrence_end_dt   TEXT,
            linked_activity_id  INTEGER REFERENCES activities(id) ON DELETE SET NULL,
            created_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            updated_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_calendar ON events(calendar_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_start    ON events(start_dt)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS event_exceptions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            occurrence_dt     TEXT NOT NULL,
            is_cancelled      INTEGER DEFAULT 0,
            override_event_id INTEGER REFERENCES events(id) ON DELETE CASCADE
        )
    """)

    # Seed system calendars
    conn.execute(
        "INSERT OR IGNORE INTO calendars (id, name, color, type) VALUES (1, 'Tasks', '#f7c948', 'system:tasks')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO calendars (id, name, color, type) VALUES (2, 'Tracked Sessions', '#7aa2f7', 'system:sessions')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO calendars (id, name, color, type) VALUES (3, 'Personal', '#9ece6a', 'user')"
    )
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('default_calendar_id', '3')")

    conn.commit()
