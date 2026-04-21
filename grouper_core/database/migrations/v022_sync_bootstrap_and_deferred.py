"""v022 - Add sync bootstrap state and deferred changes table.

Adds `bootstrap_complete` and `bootstrap_watermark` to `sync_state` to track
the progress of snapshotting existing data into the changelog.
Creates `sync_deferred_changes` to queue inbound changes that refer to
missing parent rows.
"""

import sqlite3

VERSION = 22
DESCRIPTION = "Add sync bootstrap state and deferred changes table"


def upgrade(conn: sqlite3.Connection) -> None:
    # 1. Add bootstrap state columns to sync_state
    cols = [r[1] for r in conn.execute("PRAGMA table_info(sync_state)").fetchall()]
    if "bootstrap_complete" not in cols:
        conn.execute(
            "ALTER TABLE sync_state ADD COLUMN bootstrap_complete INTEGER NOT NULL DEFAULT 0"
        )
    if "bootstrap_watermark" not in cols:
        conn.execute("ALTER TABLE sync_state ADD COLUMN bootstrap_watermark TEXT")

    # 2. Create sync_deferred_changes table
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sync_deferred_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peer_device_id TEXT NOT NULL,
            change_id INTEGER NOT NULL,
            table_name TEXT NOT NULL,
            row_uuid TEXT NOT NULL,
            operation TEXT NOT NULL,
            payload TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
        );

        CREATE INDEX IF NOT EXISTS idx_sync_deferred_peer ON sync_deferred_changes(peer_device_id);
    """)

    conn.commit()
