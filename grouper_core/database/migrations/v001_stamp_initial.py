"""v001_stamp_initial.py — Stamp initial schema version."""

import sqlite3

VERSION = 1
DESCRIPTION = "Stamp initial schema version"


def upgrade(conn: sqlite3.Connection) -> None:
    # Initial schema is created by _INITIAL_SCHEMA in connection.py.
    # This migration just records that we're at version 1.
    conn.commit()
