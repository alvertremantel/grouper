"""v021 — Add sync conflict convergence metadata and bookkeeping."""

from __future__ import annotations

import sqlite3

VERSION = 21
DESCRIPTION = "Add sync convergence metadata, tombstones, aliases, and conflicts"

_SYNCED_TABLES = [
    "activities",
    "boards",
    "projects",
    "sessions",
    "pause_events",
    "tasks",
    "tags",
    "groups",
    "activity_groups",
    "project_tags",
    "task_tags",
    "activity_tags",
    "task_prerequisites",
    "task_links",
    "calendars",
    "events",
    "event_exceptions",
    "settings",
]


def upgrade(conn: sqlite3.Connection) -> None:
    for table_name in _SYNCED_TABLES:
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()}
        if "sync_version" not in cols:
            conn.execute(
                f'ALTER TABLE "{table_name}" ADD COLUMN sync_version INTEGER NOT NULL DEFAULT 0'
            )
        if "sync_updated_by" not in cols:
            conn.execute(
                f'ALTER TABLE "{table_name}" ADD COLUMN sync_updated_by TEXT NOT NULL DEFAULT ""'
            )

    sync_state_cols = {r[1] for r in conn.execute("PRAGMA table_info(sync_state)").fetchall()}
    if "logical_clock" not in sync_state_cols:
        conn.execute("ALTER TABLE sync_state ADD COLUMN logical_clock INTEGER NOT NULL DEFAULT 0")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sync_tombstones (
            table_name      TEXT NOT NULL,
            row_uuid        TEXT NOT NULL,
            sync_version    INTEGER NOT NULL,
            sync_updated_by TEXT NOT NULL,
            deleted_payload TEXT NOT NULL DEFAULT '{}',
            created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY (table_name, row_uuid)
        );

        CREATE TABLE IF NOT EXISTS sync_uuid_aliases (
            table_name   TEXT NOT NULL,
            source_uuid  TEXT NOT NULL,
            target_uuid  TEXT NOT NULL,
            created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY (table_name, source_uuid)
        );

        CREATE TABLE IF NOT EXISTS sync_conflicts (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            peer_device_id TEXT NOT NULL DEFAULT '',
            table_name     TEXT NOT NULL,
            row_uuid       TEXT NOT NULL,
            conflict_type  TEXT NOT NULL,
            natural_key    TEXT,
            payload        TEXT NOT NULL DEFAULT '{}',
            created_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        """
    )

    conn.commit()
