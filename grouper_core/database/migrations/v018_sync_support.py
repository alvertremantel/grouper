"""v018 — Add sync infrastructure: UUID columns, CDC changelog, sync state.

Adds a `uuid` TEXT column to every synced table (globally unique row
identity), plus the bookkeeping tables that the sync system needs:
  - sync_state:     single-row flag controlling CDC trigger behavior
  - sync_changelog: append-only log of every INSERT/UPDATE/DELETE
  - sync_peers:     high-water marks for each known peer device

CDC triggers are created dynamically by grouper_server.sync.changelog so that
they always reflect the current schema (including columns added by
future migrations).
"""

import sqlite3
import uuid as _uuid

VERSION = 18
DESCRIPTION = "Add sync support: UUID columns, CDC changelog, sync state"

# Tables that get a uuid column.  Must match grouper_server.sync.schema.SYNCED_TABLES
# minus 'settings' (which uses TEXT PK 'key', not integer id).
_UUID_TABLES = [
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
]


def upgrade(conn: sqlite3.Connection) -> None:
    # ── 1. Add uuid column to every synced table ────────────────────────
    # ALTER TABLE ADD COLUMN rejects non-deterministic defaults like
    # randomblob(), so we add with no default and backfill in Python.
    for table in _UUID_TABLES:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if "uuid" in cols:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN uuid TEXT")
        # Backfill each existing row with a unique hex UUID
        row_ids = conn.execute(f"SELECT rowid FROM {table}").fetchall()
        for (rid,) in row_ids:
            conn.execute(
                f"UPDATE {table} SET uuid = ? WHERE rowid = ?",
                (_uuid.uuid4().hex, rid),
            )
        conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_uuid ON {table}(uuid)")

    # ── 2. Sync bookkeeping tables ──────────────────────────────────────
    conn.executescript("""
        -- Single-row table: device identity + CDC gate
        CREATE TABLE IF NOT EXISTS sync_state (
            id        INTEGER PRIMARY KEY CHECK (id = 1),
            device_id TEXT NOT NULL,
            syncing   INTEGER NOT NULL DEFAULT 0
        );

        -- Append-only CDC log
        CREATE TABLE IF NOT EXISTS sync_changelog (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id  TEXT    NOT NULL,
            table_name TEXT    NOT NULL,
            row_uuid   TEXT    NOT NULL,
            operation  TEXT    NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
            payload    TEXT    NOT NULL DEFAULT '{}',
            timestamp  TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sync_cl_device
            ON sync_changelog(device_id);
        CREATE INDEX IF NOT EXISTS idx_sync_cl_table
            ON sync_changelog(table_name);

        -- Per-peer high-water marks
        CREATE TABLE IF NOT EXISTS sync_peers (
            peer_device_id TEXT PRIMARY KEY,
            peer_name      TEXT    NOT NULL DEFAULT '',
            last_changelog_id INTEGER NOT NULL DEFAULT 0,
            last_sync_at   TEXT
        );
    """)

    conn.commit()
