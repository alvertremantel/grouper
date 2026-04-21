"""Tests for sync runtime diagnostics and failure classification."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from typing import cast

import pytest


class _FakeCursor:
    def __init__(self, row: tuple[object, ...] | None = None) -> None:
        self._row = row

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row


class _FakeConnection:
    def __init__(self, *, wal_exc: BaseException | None = None) -> None:
        self.row_factory = None
        self._wal_exc = wal_exc

    def execute(self, sql: str) -> _FakeCursor:
        if sql == "PRAGMA journal_mode = WAL" and self._wal_exc is not None:
            raise self._wal_exc
        if sql == "PRAGMA journal_mode = WAL":
            return _FakeCursor(("wal",))
        return _FakeCursor((1,))

    def create_function(self, _name: str, _num_args: int, _fn) -> None:
        return None

    def close(self) -> None:
        return None


class _SequenceReader:
    def __init__(self, items: list[bytes | BaseException]) -> None:
        self._items = list(items)

    async def readline(self) -> bytes:
        item = self._items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class _Writer:
    def __init__(self) -> None:
        self.messages: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.messages.append(data)

    async def drain(self) -> None:
        return None


def test_open_sync_connection_classifies_database_open_failure(monkeypatch, tmp_path):
    from grouper_server.sync.runtime import SyncPhaseError, open_sync_connection

    def _fail_connect(_db_path: str) -> sqlite3.Connection:
        raise OSError(121, "The semaphore timeout period has expired")

    monkeypatch.setattr(sqlite3, "connect", _fail_connect)

    with pytest.raises(SyncPhaseError, match="Failed during local database setup") as exc_info:
        open_sync_connection(tmp_path / "sync.db", logger=logging.getLogger(__name__))

    assert "semaphore timeout" in str(exc_info.value).lower()


def test_open_sync_connection_classifies_wal_failure(monkeypatch, tmp_path):
    from grouper_server.sync.runtime import SyncPhaseError, format_sync_error, open_sync_connection

    def _connect(_db_path: str) -> _FakeConnection:
        return _FakeConnection(wal_exc=OSError(121, "The semaphore timeout period has expired"))

    monkeypatch.setattr(sqlite3, "connect", _connect)

    with pytest.raises(SyncPhaseError) as exc_info:
        open_sync_connection(tmp_path / "sync.db", logger=logging.getLogger(__name__))

    message = format_sync_error(exc_info.value)
    assert message.startswith("Failed during local database setup")
    assert "semaphore timeout" in message.lower()


def test_sync_with_peer_classifies_connect_failure(monkeypatch):
    from grouper.database.connection import get_database_path
    from grouper_server.sync.client import sync_with_peer
    from grouper_server.sync.runtime import SyncPhaseError, format_sync_error

    async def _fail_open_connection(*args, **kwargs):
        _ = args, kwargs
        raise OSError(121, "The semaphore timeout period has expired")

    monkeypatch.setattr(asyncio, "open_connection", _fail_open_connection)

    with pytest.raises(SyncPhaseError) as exc_info:
        asyncio.run(sync_with_peer(get_database_path(), "127.0.0.1", 53987))

    message = format_sync_error(exc_info.value)
    assert message.startswith("Failed while connecting to peer")
    assert "semaphore timeout" in message.lower()


def test_sync_with_peer_uses_happy_eyeballs_for_hostname(monkeypatch):
    from grouper.database.connection import get_database_path
    from grouper_server.sync.client import sync_with_peer

    captured_args: tuple[object, ...] | None = None
    captured_kwargs: dict[str, object] | None = None

    async def _fake_open_connection(*args, **kwargs):
        nonlocal captured_args, captured_kwargs
        captured_args = args
        captured_kwargs = kwargs
        raise ConnectionRefusedError("expected test failure")

    async def _fake_getaddrinfo(*args, **kwargs):
        _ = args, kwargs
        return []

    async def _run() -> None:
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(loop, "getaddrinfo", _fake_getaddrinfo)
        monkeypatch.setattr(asyncio, "open_connection", _fake_open_connection)
        await sync_with_peer(get_database_path(), "peer.example.ts.net", 53987)

    with pytest.raises(Exception, match="Failed while connecting to peer"):
        asyncio.run(_run())

    assert captured_args == ("peer.example.ts.net", 53987)
    assert captured_kwargs is not None
    assert captured_kwargs["happy_eyeballs_delay"] == 0.25
    assert captured_kwargs["interleave"] == 1


def test_do_sync_classifies_stream_read_failure():
    from grouper.database.connection import get_connection, get_database_path
    from grouper_server.sync import protocol as proto
    from grouper_server.sync.client import _do_sync
    from grouper_server.sync.device import get_or_create_device_id
    from grouper_server.sync.runtime import SyncPhaseError

    with get_connection() as conn:
        device_id = get_or_create_device_id(conn)
        reader = _SequenceReader(
            [
                proto.encode(proto.Hello(device_id="peer-device", device_name="Peer")),
                proto.encode(proto.SyncRequest(since_id=0)),
                proto.encode(proto.SyncAck(last_applied_id=0)),
                OSError(121, "The semaphore timeout period has expired"),
            ]
        )
        writer = _Writer()

        with pytest.raises(SyncPhaseError, match="Failed while reading sync response"):
            asyncio.run(
                _do_sync(
                    cast(asyncio.StreamReader, reader),
                    cast(asyncio.StreamWriter, writer),
                    conn,
                    device_id,
                    get_database_path(),
                    "127.0.0.1",
                    53987,
                )
            )


def test_do_sync_classifies_apply_failure(monkeypatch):
    from grouper.database.connection import get_connection, get_database_path
    from grouper_server.sync import protocol as proto
    from grouper_server.sync.client import _do_sync
    from grouper_server.sync.device import get_or_create_device_id
    from grouper_server.sync.runtime import SyncPhaseError

    def _fail_apply(*args, **kwargs):
        _ = args, kwargs
        raise OSError(121, "The semaphore timeout period has expired")

    monkeypatch.setattr("grouper_server.sync.client.apply_changes", _fail_apply)

    with get_connection() as conn:
        device_id = get_or_create_device_id(conn)
        reader = _SequenceReader(
            [
                proto.encode(proto.Hello(device_id="peer-device", device_name="Peer")),
                proto.encode(proto.SyncRequest(since_id=0)),
                proto.encode(proto.SyncAck(last_applied_id=0)),
                proto.encode(
                    proto.SyncResponse(
                        changes=[
                            {
                                "id": 1,
                                "device_id": "peer-device",
                                "table_name": "activities",
                                "row_uuid": "remote-activity-uuid",
                                "operation": "INSERT",
                                "payload": {
                                    "name": "Remote Activity",
                                    "uuid": "remote-activity-uuid",
                                },
                                "timestamp": "2026-01-01T00:00:00",
                            }
                        ]
                    )
                ),
            ]
        )
        writer = _Writer()

        with pytest.raises(SyncPhaseError, match="Failed while applying remote changes"):
            asyncio.run(
                _do_sync(
                    cast(asyncio.StreamReader, reader),
                    cast(asyncio.StreamWriter, writer),
                    conn,
                    device_id,
                    get_database_path(),
                    "127.0.0.1",
                    53987,
                )
            )
