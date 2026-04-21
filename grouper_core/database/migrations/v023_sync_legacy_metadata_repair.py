"""v023 - Normalize legacy sync metadata for deterministic convergence."""

from __future__ import annotations

import sqlite3

VERSION = 23
DESCRIPTION = "Normalize legacy sync metadata for deterministic convergence"

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
    sync_state = conn.execute("SELECT device_id, syncing FROM sync_state WHERE id = 1").fetchone()
    if sync_state is None:
        conn.commit()
        return

    device_id = str(sync_state[0] or "")
    if not device_id:
        conn.commit()
        return

    original_syncing = int(sync_state[1] or 0)
    conn.execute("UPDATE sync_state SET syncing = 1 WHERE id = 1")
    conn.commit()
    try:
        max_version = int(
            conn.execute("SELECT COALESCE(MAX(sync_version), 0) FROM sync_tombstones").fetchone()[0]
            or 0
        )

        for table_name in _SYNCED_TABLES:
            identity_column = "key" if table_name == "settings" else "uuid"
            rows = conn.execute(
                f'SELECT rowid, sync_version, sync_updated_by FROM "{table_name}" '
                f'WHERE COALESCE(sync_version, 0) <= 0 OR COALESCE(sync_updated_by, "") = "" '
                f'ORDER BY "{identity_column}", rowid'
            ).fetchall()
            for row in rows:
                sync_version = int(row[1] or 0)
                sync_updated_by = str(row[2] or "")
                if sync_version <= 0:
                    max_version += 1
                    sync_version = max_version
                if not sync_updated_by:
                    sync_updated_by = device_id
                conn.execute(
                    f'UPDATE "{table_name}" SET sync_version = ?, sync_updated_by = ? WHERE rowid = ?',
                    (sync_version, sync_updated_by, row[0]),
                )

            table_max = conn.execute(
                f'SELECT COALESCE(MAX(sync_version), 0) FROM "{table_name}"'
            ).fetchone()
            max_version = max(max_version, int(table_max[0] or 0))

        conn.execute(
            "UPDATE sync_state SET logical_clock = MAX(logical_clock, ?) WHERE id = 1",
            (max_version,),
        )
        conn.commit()
    finally:
        conn.execute("UPDATE sync_state SET syncing = ? WHERE id = 1", (original_syncing,))
        conn.commit()
