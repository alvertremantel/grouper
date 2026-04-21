"""
device.py — Device identity management.

Each Grouper installation gets a stable UUID the first time sync is
enabled.  Stored in the sync_state table (single row, id=1).
"""

from __future__ import annotations

import socket
import sqlite3
import uuid


def get_device_name() -> str:
    """Best-effort human-readable device name."""
    return socket.gethostname()


def get_or_create_device_id(conn: sqlite3.Connection) -> str:
    """Return the local device UUID, creating one if this is the first run."""
    row = conn.execute("SELECT device_id FROM sync_state WHERE id = 1").fetchone()
    if row:
        return row[0] if isinstance(row, tuple) else row["device_id"]

    device_id = uuid.uuid4().hex
    conn.execute(
        "INSERT OR IGNORE INTO sync_state (id, device_id, syncing, logical_clock) VALUES (1, ?, 0, 0)",
        (device_id,),
    )
    conn.commit()
    return device_id


def enable_cdc(conn: sqlite3.Connection) -> None:
    """Flip the syncing flag so CDC triggers start recording."""
    get_or_create_device_id(conn)  # ensure row exists
    conn.execute("UPDATE sync_state SET syncing = 0 WHERE id = 1")
    conn.commit()


def suppress_cdc(conn: sqlite3.Connection) -> None:
    """Temporarily suppress triggers while applying remote changes."""
    conn.execute("UPDATE sync_state SET syncing = 1 WHERE id = 1")
    # no commit — caller controls the transaction


def unsuppress_cdc(conn: sqlite3.Connection) -> None:
    """Re-enable triggers after applying remote changes."""
    conn.execute("UPDATE sync_state SET syncing = 0 WHERE id = 1")
    # no commit — caller controls the transaction
