"""Integration coverage for a full client/server sync round trip."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path


def test_sync_round_trip_converges_two_databases(tmp_path: Path) -> None:
    from grouper_sync.client import sync_with_peer
    from grouper_sync.server import SyncServer

    server_db = tmp_path / "server.db"
    client_db = tmp_path / "client.db"

    _init_sync_database(server_db)
    _init_sync_database(client_db)

    _insert_activity(server_db, name="Server Activity", row_uuid="server-activity-uuid")
    _insert_activity(client_db, name="Client Activity", row_uuid="client-activity-uuid")

    async def _run_round_trip() -> dict[str, int]:
        server = SyncServer(server_db, host="127.0.0.1", port=0)
        await server.start()
        try:
            return await sync_with_peer(client_db, "127.0.0.1", server.actual_port)
        finally:
            await server.stop()

    result = asyncio.run(_run_round_trip())

    assert result["sent"] == 1
    assert result["received"] >= 1
    assert _activity_names(server_db) == ["Client Activity", "Server Activity"]
    assert _activity_names(client_db) == ["Client Activity", "Server Activity"]


def test_large_batch_sync_over_10000_changes(tmp_path: Path) -> None:
    from grouper_sync.changelog import DEFAULT_PAGE_SIZE
    from grouper_sync.client import sync_with_peer
    from grouper_sync.server import SyncServer

    server_db = tmp_path / "server.db"
    client_db = tmp_path / "client.db"

    _init_sync_database(server_db)
    _init_sync_database(client_db)

    num_changes = DEFAULT_PAGE_SIZE * 2 + 100
    for i in range(num_changes):
        _insert_activity(server_db, name=f"Server Activity {i}", row_uuid=f"server-act-{i}")
    _insert_activity(client_db, name="Client Activity", row_uuid="client-activity-uuid")

    async def _run_round_trip() -> dict[str, int]:
        server = SyncServer(server_db, host="127.0.0.1", port=0)
        await server.start()
        try:
            return await sync_with_peer(client_db, "127.0.0.1", server.actual_port, timeout=120)
        finally:
            await server.stop()

    result = asyncio.run(_run_round_trip())

    assert result["sent"] == 1
    assert result["received"] >= num_changes

    client_names = _activity_names(client_db)
    assert len(client_names) == num_changes + 1
    assert "Client Activity" in client_names

    server_names = _activity_names(server_db)
    assert "Client Activity" in server_names


def test_sync_resume_after_partial_catchup(tmp_path: Path) -> None:
    from grouper_sync.changelog import DEFAULT_PAGE_SIZE
    from grouper_sync.client import sync_with_peer
    from grouper_sync.server import SyncServer

    server_db = tmp_path / "server.db"
    client_db = tmp_path / "client.db"

    _init_sync_database(server_db)
    _init_sync_database(client_db)

    num_changes = DEFAULT_PAGE_SIZE * 3
    for i in range(num_changes):
        _insert_activity(server_db, name=f"Resume Activity {i}", row_uuid=f"resume-act-{i}")

    server = SyncServer(server_db, host="127.0.0.1", port=0)

    async def _partial_then_resume() -> tuple[dict[str, int], dict[str, int]]:
        await server.start()
        try:
            first = await sync_with_peer(client_db, "127.0.0.1", server.actual_port, timeout=120)
            second = await sync_with_peer(client_db, "127.0.0.1", server.actual_port, timeout=120)
            return first, second
        finally:
            await server.stop()

    first_result, second_result = asyncio.run(_partial_then_resume())

    total_received = first_result["received"] + second_result["received"]
    assert total_received >= num_changes

    client_names = _activity_names(client_db)
    assert len(client_names) == num_changes

    second_received = second_result["received"]
    assert second_received == 0, "Resume sync should receive nothing new"


def _init_sync_database(db_path: Path) -> None:
    import grouper_core.database.connection as conn_mod
    from grouper_core.database.connection import register_sqlite_functions
    from grouper_sync.changelog import ensure_triggers
    from grouper_sync.device import enable_cdc

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        register_sqlite_functions(conn)
        conn.executescript(conn_mod._INITIAL_SCHEMA)
        conn.commit()
        enable_cdc(conn)
        ensure_triggers(conn)
    finally:
        conn.close()


def _insert_activity(db_path: Path, *, name: str, row_uuid: str) -> None:
    from grouper_core.database.connection import register_sqlite_functions

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        register_sqlite_functions(conn)
        conn.execute("INSERT INTO activities (name, uuid) VALUES (?, ?)", (name, row_uuid))
        conn.commit()
    finally:
        conn.close()


def _activity_names(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT name FROM activities ORDER BY name").fetchall()
        return [row["name"] for row in rows]
    finally:
        conn.close()
