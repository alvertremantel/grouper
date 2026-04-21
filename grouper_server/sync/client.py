"""
client.py — Sync client that connects to a peer's sync server.

Initiates a TCP connection, performs the handshake, and exchanges
changelog entries bidirectionally.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import sqlite3
from pathlib import Path

from . import protocol as proto
from .device import get_or_create_device_id
from .runtime import open_sync_connection, wrap_sync_exception
from .sync_ops import (
    abort_apply_changes,
    apply_changes,
    finish_apply_changes,
    get_peer_hwm,
    prepare_outbound_paged,
    set_peer_hwm,
)

log = logging.getLogger(__name__)

_STREAM_LIMIT = 10 * 1024 * 1024  # 10 MB


async def sync_with_peer(
    db_path: Path,
    host: str,
    port: int,
    timeout: float = 30,
) -> dict[str, int]:
    """Connect to a peer sync server and perform bidirectional sync.

    Returns a summary dict with counts of changes sent and received.
    """
    log.debug("Starting sync host=%s port=%s db=%s", host, port, db_path)
    conn = open_sync_connection(db_path, logger=log, host=host, port=port)

    try:
        try:
            device_id = get_or_create_device_id(conn)
        except Exception as exc:
            raise wrap_sync_exception(
                log,
                "local_database_open",
                exc,
                db_path=db_path,
                host=host,
                port=port,
            ) from exc

        log.debug("Connecting to peer host=%s port=%s db=%s", host, port, db_path)
        await _log_peer_resolution(host, port)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host,
                    port,
                    limit=_STREAM_LIMIT,
                    happy_eyeballs_delay=0.25,
                    interleave=1,
                ),
                timeout=timeout,
            )
        except Exception as exc:
            raise wrap_sync_exception(
                log,
                "connect",
                exc,
                db_path=db_path,
                host=host,
                port=port,
            ) from exc

        try:
            return await _do_sync(reader, writer, conn, device_id, db_path, host, port, timeout)
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
    finally:
        conn.close()


async def _do_sync(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    conn: sqlite3.Connection,
    device_id: str,
    db_path: Path,
    host: str,
    port: int,
    timeout: float = 30,
) -> dict[str, int]:
    """Execute the sync protocol as the connecting (client) side."""
    import socket

    # 1. Send HELLO
    log.debug("Sending handshake host=%s port=%s db=%s", host, port, db_path)
    await _write_message(
        writer,
        proto.Hello(device_id=device_id, device_name=socket.gethostname()),
        phase="handshake_send",
        db_path=db_path,
        host=host,
        port=port,
    )

    # 2. Receive server's HELLO
    log.debug("Waiting for handshake response host=%s port=%s db=%s", host, port, db_path)
    msg = await _read_message(
        reader,
        timeout=10,
        phase="handshake_receive",
        db_path=db_path,
        host=host,
        port=port,
        empty_message="Server closed connection during handshake",
        invalid_message="Bad handshake from server",
    )
    if not isinstance(msg, proto.Hello):
        exc = ConnectionError(f"Expected hello, got {type(msg).__name__}")
        raise wrap_sync_exception(
            log,
            "handshake_receive",
            exc,
            db_path=db_path,
            host=host,
            port=port,
        ) from exc

    # Protocol version check
    local_version = proto.Hello().protocol_version
    if msg.protocol_version != local_version:
        log.warning(
            "Protocol version mismatch: peer=%d local=%d",
            msg.protocol_version,
            local_version,
        )
        await _write_message(
            writer,
            proto.Error(
                message=(
                    "Sync protocol mismatch. Both peers must be upgraded to the same sync version "
                    f"(local={local_version}, peer={msg.protocol_version})."
                )
            ),
            phase="handshake_send",
            db_path=db_path,
            host=host,
            port=port,
        )
        exc = ConnectionError(
            "Sync protocol mismatch. Both peers must be upgraded to the same sync version "
            f"(local={local_version}, peer={msg.protocol_version})."
        )
        raise wrap_sync_exception(
            log,
            "handshake_receive",
            exc,
            db_path=db_path,
            host=host,
            port=port,
        ) from exc

    peer_device_id = msg.device_id
    peer_name = msg.device_name
    log.info("Connected to %s (%s)", peer_name, peer_device_id[:8])

    # 3. Receive server's sync request (server asks for our changes first)
    log.debug("Waiting for peer sync request host=%s port=%s db=%s", host, port, db_path)
    msg = await _read_message(
        reader,
        timeout=10,
        phase="sync_request_read",
        db_path=db_path,
        host=host,
        port=port,
        empty_message="Server closed connection",
        invalid_message="Bad sync request from server",
    )

    changes_sent = 0
    changes_received = 0

    if isinstance(msg, proto.SyncRequest):
        # ── Push our changes to server (paged loop) ─────────────────────
        total_sent = 0
        current_since_id = msg.since_id
        while True:
            outbound, has_more, next_since_id = prepare_outbound_paged(
                conn,
                device_id,
                current_since_id,
            )
            log.debug(
                "Sending %d local changes host=%s port=%s db=%s",
                len(outbound),
                host,
                port,
                db_path,
            )
            await _write_message(
                writer,
                proto.SyncResponse(
                    changes=outbound,
                    has_more=has_more,
                    next_since_id=next_since_id,
                ),
                phase="sync_response_send",
                db_path=db_path,
                host=host,
                port=port,
            )
            total_sent += len(outbound)

            line = await _read_line(
                reader,
                timeout=10,
                phase="sync_ack_read",
                db_path=db_path,
                host=host,
                port=port,
                empty_message="Server closed connection before acknowledging local changes",
            )
            if line:
                try:
                    ack = proto.decode(line)
                except ValueError as exc:
                    log.warning("Bad ACK from server: %s", exc)
                    ack = None
                if isinstance(ack, proto.SyncAck):
                    log.debug("Server acknowledged up to %d", ack.last_applied_id)

            if not has_more:
                break

            next_request = await _read_message(
                reader,
                timeout=10,
                phase="sync_request_read",
                db_path=db_path,
                host=host,
                port=port,
                empty_message="Server closed connection before requesting the next page",
                invalid_message="Bad sync request from server",
            )
            if not isinstance(next_request, proto.SyncRequest):
                exc = ConnectionError(
                    f"Expected sync_request after acknowledgement, got {type(next_request).__name__}"
                )
                raise wrap_sync_exception(
                    log,
                    "sync_request_read",
                    exc,
                    db_path=db_path,
                    host=host,
                    port=port,
                ) from exc
            current_since_id = next_request.since_id

        changes_sent = total_sent
        log.info("Sent %d total changes to server", changes_sent)
    else:
        exc = ConnectionError(f"Expected sync_request, got {type(msg).__name__}")
        raise wrap_sync_exception(
            log,
            "sync_request_read",
            exc,
            db_path=db_path,
            host=host,
            port=port,
        ) from exc

    # 4. Now request the server's changes (paged loop)
    hwm = get_peer_hwm(conn, peer_device_id)
    current_since_id = hwm
    log.debug("Requesting remote changes since=%d host=%s port=%s db=%s", hwm, host, port, db_path)
    await _write_message(
        writer,
        proto.SyncRequest(since_id=current_since_id),
        phase="sync_request_send",
        db_path=db_path,
        host=host,
        port=port,
    )

    total_received = 0
    page_timeout = max(30, timeout * 0.5)
    while True:
        msg = await _read_message(
            reader,
            timeout=page_timeout,
            phase="sync_response_read",
            db_path=db_path,
            host=host,
            port=port,
            empty_message="Server closed connection during sync",
            invalid_message="Bad sync response from server",
        )

        if not isinstance(msg, proto.SyncResponse):
            exc = ConnectionError(f"Expected sync_response, got {type(msg).__name__}")
            raise wrap_sync_exception(
                log,
                "sync_response_read",
                exc,
                db_path=db_path,
                host=host,
                port=port,
            ) from exc

        try:
            if msg.changes:
                log.debug(
                    "Applying %d remote changes from %s (%s) db=%s",
                    len(msg.changes),
                    peer_name,
                    peer_device_id[:8],
                    db_path,
                )
                apply_result = apply_changes(conn, msg.changes, peer_device_id, auto_commit=False)
                last_id = apply_result.last_durable_change_id or current_since_id
                try:
                    set_peer_hwm(conn, peer_device_id, peer_name, last_id)
                    finish_apply_changes(conn)
                except Exception:
                    abort_apply_changes(conn)
                    raise
                total_received += apply_result.applied_count
            else:
                last_id = current_since_id
        except Exception as exc:
            raise wrap_sync_exception(
                log,
                "apply_changes",
                exc,
                db_path=db_path,
                host=host,
                port=port,
            ) from exc

        await _write_message(
            writer,
            proto.SyncAck(last_applied_id=last_id),
            phase="sync_ack_send",
            db_path=db_path,
            host=host,
            port=port,
        )

        if not msg.has_more:
            break

        current_since_id = last_id
        await _write_message(
            writer,
            proto.SyncRequest(since_id=current_since_id),
            phase="sync_request_send",
            db_path=db_path,
            host=host,
            port=port,
        )

    changes_received = total_received
    log.info("Applied %d total changes from server", changes_received)

    return {"sent": changes_sent, "received": changes_received}


async def _write_message(
    writer: asyncio.StreamWriter,
    message: proto.Hello | proto.SyncRequest | proto.SyncResponse | proto.SyncAck | proto.Error,
    *,
    phase: str,
    db_path: Path,
    host: str,
    port: int,
) -> None:
    try:
        writer.write(proto.encode(message))
        await writer.drain()
    except Exception as exc:
        raise wrap_sync_exception(
            log,
            phase,
            exc,
            db_path=db_path,
            host=host,
            port=port,
        ) from exc


async def _log_peer_resolution(host: str, port: int) -> None:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
            family=socket.AF_UNSPEC,
        )
    except Exception:
        log.debug("Peer address resolution failed host=%s port=%s", host, port, exc_info=True)
        return

    resolved = []
    for family, socktype, protocol, _, sockaddr in infos:
        if socktype != socket.SOCK_STREAM:
            continue
        resolved.append(
            {
                "family": socket.AddressFamily(family).name,
                "proto": protocol,
                "address": sockaddr,
            }
        )
    log.debug("Resolved peer addresses host=%s port=%s addresses=%s", host, port, resolved)


async def _read_line(
    reader: asyncio.StreamReader,
    *,
    timeout: float,
    phase: str,
    db_path: Path,
    host: str,
    port: int,
    empty_message: str,
) -> bytes:
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=timeout)
    except Exception as exc:
        raise wrap_sync_exception(
            log,
            phase,
            exc,
            db_path=db_path,
            host=host,
            port=port,
        ) from exc

    if not line:
        exc = ConnectionError(empty_message)
        raise wrap_sync_exception(
            log,
            phase,
            exc,
            db_path=db_path,
            host=host,
            port=port,
        ) from exc
    return line


async def _read_message(
    reader: asyncio.StreamReader,
    *,
    timeout: float,
    phase: str,
    db_path: Path,
    host: str,
    port: int,
    empty_message: str,
    invalid_message: str,
) -> proto.Hello | proto.SyncRequest | proto.SyncResponse | proto.SyncAck | proto.Error:
    line = await _read_line(
        reader,
        timeout=timeout,
        phase=phase,
        db_path=db_path,
        host=host,
        port=port,
        empty_message=empty_message,
    )
    try:
        return proto.decode(line)
    except ValueError as exc:
        error = ConnectionError(f"{invalid_message}: {exc}")
        raise wrap_sync_exception(
            log,
            phase,
            error,
            db_path=db_path,
            host=host,
            port=port,
        ) from exc
