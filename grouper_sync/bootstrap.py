"""
bootstrap.py - Snapshot existing rows into sync_changelog.
"""

from __future__ import annotations

import json
import logging
import sqlite3

from .changelog import get_full_table_state
from .schema import INSERT_ORDER, KEY_PK_TABLES, SYNCED_TABLES

log = logging.getLogger(__name__)


def _encode_bootstrap_cursor(table_name: str | None) -> str | None:
    if table_name is None:
        return None
    return f"next:{table_name}"


def _bootstrap_resume_target(bootstrap_watermark: str | None) -> tuple[str | None, bool]:
    if not bootstrap_watermark:
        return None, False
    if bootstrap_watermark.startswith("next:"):
        return bootstrap_watermark.removeprefix("next:"), True
    try:
        last_completed_idx = INSERT_ORDER.index(bootstrap_watermark)
    except ValueError:
        return None, False
    next_idx = last_completed_idx + 1
    if next_idx >= len(INSERT_ORDER):
        return None, True
    return INSERT_ORDER[next_idx], True


def ensure_bootstrap_schema(conn: sqlite3.Connection) -> None:
    """Ensure bootstrap metadata columns and deferred table exist."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sync_state)").fetchall()}
    if "bootstrap_complete" not in cols:
        conn.execute(
            "ALTER TABLE sync_state ADD COLUMN bootstrap_complete INTEGER NOT NULL DEFAULT 0"
        )
    if "bootstrap_watermark" not in cols:
        conn.execute("ALTER TABLE sync_state ADD COLUMN bootstrap_watermark TEXT")

    conn.executescript(
        """
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

        CREATE INDEX IF NOT EXISTS idx_sync_deferred_peer
        ON sync_deferred_changes(peer_device_id);
        """
    )
    conn.commit()


def snapshot_for_bootstrap(conn: sqlite3.Connection, device_id: str) -> None:
    """Snapshot existing database state into sync_changelog if not already done."""
    ensure_bootstrap_schema(conn)

    # Check if bootstrap is already complete
    row = conn.execute(
        "SELECT bootstrap_complete, bootstrap_watermark FROM sync_state WHERE id = 1"
    ).fetchone()
    if not row:
        return

    bootstrap_complete = row["bootstrap_complete"]
    bootstrap_watermark = row["bootstrap_watermark"]

    if bootstrap_complete:
        return

    next_table, resumed = _bootstrap_resume_target(bootstrap_watermark)
    if resumed:
        log.info("Resuming bootstrap snapshot from table %s", next_table)
    else:
        log.info("Starting initial sync bootstrap snapshot...")

    resume_table_idx = 0
    if next_table:
        try:
            resume_table_idx = INSERT_ORDER.index(next_table)
        except ValueError:
            log.warning("Ignoring invalid bootstrap watermark %r", bootstrap_watermark)

    # Iterate through tables in dependency order
    pending_tables = [table for table in INSERT_ORDER if table in SYNCED_TABLES]
    for index, table in enumerate(pending_tables):
        if table not in SYNCED_TABLES:
            continue

        current_idx = INSERT_ORDER.index(table)
        if current_idx < resume_table_idx:
            continue

        # Suppress CDC so our own snapshot operations don't fire triggers
        # (Though we insert directly into sync_changelog, this ensures no other
        # sync activities interfere). We are inside a table-level transaction.
        _snapshot_table(conn, table, device_id)

        next_cursor = (
            _encode_bootstrap_cursor(pending_tables[index + 1])
            if index + 1 < len(pending_tables)
            else None
        )
        if index + 1 < len(pending_tables):
            conn.execute(
                "UPDATE sync_state SET bootstrap_watermark = ? WHERE id = 1", (next_cursor,)
            )
        else:
            conn.execute(
                "UPDATE sync_state SET bootstrap_complete = 1, bootstrap_watermark = NULL WHERE id = 1"
            )
        conn.commit()
        log.info("Bootstrap snapshot complete for table %s", table)

    if not pending_tables:
        conn.execute(
            "UPDATE sync_state SET bootstrap_complete = 1, bootstrap_watermark = NULL WHERE id = 1"
        )
        conn.commit()
    log.info("Bootstrap snapshot fully completed.")


def _snapshot_table(conn: sqlite3.Connection, table_name: str, device_id: str) -> None:
    """Snapshot a single table into sync_changelog."""
    rows = get_full_table_state(conn, table_name)
    if not rows:
        return

    # Batch insert into sync_changelog
    changelog_entries = []
    timestamp = conn.execute("SELECT strftime('%Y-%m-%dT%H:%M:%f', 'now', 'localtime')").fetchone()[
        0
    ]

    for r in rows:
        # Add bootstrap marker so we know this is a bootstrap event (for conflict resolution)
        payload = dict(r)
        payload["_bootstrap"] = True

        # Determine row_uuid. For tables without a 'uuid' column (like settings), use 'key'
        row_uuid = payload.get("key") if table_name in KEY_PK_TABLES else payload.get("uuid")

        if not row_uuid:
            continue  # Skip rows without identity

        changelog_entries.append(
            (device_id, table_name, row_uuid, "INSERT", json.dumps(payload), timestamp)
        )

    if changelog_entries:
        conn.executemany(
            """
            INSERT INTO sync_changelog
                (device_id, table_name, row_uuid, operation, payload, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            changelog_entries,
        )
