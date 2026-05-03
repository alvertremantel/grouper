"""
server.py — Async TCP sync server.

Listens for incoming peer connections, performs bidirectional sync
using the CDC changelog, then keeps the connection alive for
real-time change streaming.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sqlite3
import sys
from pathlib import Path

from . import protocol as proto
from .runtime import (
    SyncPhaseError,
    open_sync_connection,
    prepare_local_sync_database,
    wrap_sync_exception,
)
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


class SyncServerAlreadyRunning(RuntimeError):
    """Raised when a sync server is already running against this database."""


class SyncServer:
    """TCP server that handles peer sync connections."""

    def __init__(self, db_path: Path, host: str = "0.0.0.0", port: int = 0) -> None:
        self.db_path = db_path
        self.host = host
        self.port = port
        self._server: asyncio.Server | None = None
        self._device_id: str = ""
        self._lockfile: Path = db_path.parent / (db_path.name + ".sync.lock")

    @property
    def device_id(self) -> str:
        """The unique device identifier for this sync server."""
        return self._device_id

    @property
    def actual_port(self) -> int:
        """Port assigned by the OS (useful when port=0)."""
        if self._server and self._server.sockets:
            return self._server.sockets[0].getsockname()[1]
        return self.port

    async def start(self) -> None:
        """Initialize DB, install triggers, and start listening.

        Raises ``SyncServerAlreadyRunning`` if another sync server process
        holds the lockfile for this database.
        """
        try:
            self._acquire_lock()
            self._device_id = prepare_local_sync_database(
                self.db_path,
                logger=log,
                host=self.host,
                port=self.port,
            )

            log.debug(
                "Starting sync server listener db=%s host=%s port=%s",
                self.db_path,
                self.host,
                self.port,
            )
            self._server = await asyncio.start_server(
                self._handle_client,
                self.host,
                self.port,
                limit=_STREAM_LIMIT,
            )
        except SyncPhaseError:
            self._release_lock()
            raise
        except Exception as exc:
            self._release_lock()
            raise wrap_sync_exception(
                log,
                "server_start",
                exc,
                db_path=self.db_path,
                host=self.host,
                port=self.port,
            ) from exc
        addrs = [s.getsockname() for s in self._server.sockets]
        log.info("Sync server listening on %s (device %s)", addrs, self._device_id[:8])

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._release_lock()

    async def serve_forever(self) -> None:
        if self._server:
            async with self._server:
                await self._server.serve_forever()

    # ── Client handler ──────────────────────────────────────────────────

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        addr = writer.get_extra_info("peername")
        log.info("Peer connected from %s", addr)
        peer_device_id = ""

        try:
            # 1. Receive HELLO
            msg = await _read_message(
                reader,
                timeout=10,
                phase="handshake_receive",
                db_path=self.db_path,
                host=self.host,
                port=self.actual_port,
                empty_message=f"Peer {addr} closed the connection during handshake",
                invalid_message="Bad handshake from peer",
            )
            if not isinstance(msg, proto.Hello):
                await _write_message(
                    writer,
                    proto.Error(message="Expected hello"),
                    phase="handshake_send",
                    db_path=self.db_path,
                    host=self.host,
                    port=self.actual_port,
                )
                return

            # Protocol version check
            local_version = proto.Hello().protocol_version
            if msg.protocol_version != local_version:
                log.warning(
                    "Protocol version mismatch with %s: peer=%d local=%d",
                    addr,
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
                    db_path=self.db_path,
                    host=self.host,
                    port=self.actual_port,
                )
                return

            peer_device_id = msg.device_id
            peer_name = msg.device_name
            log.info("Peer identified: %s (%s)", peer_name, peer_device_id[:8])

            # 2. Send our HELLO back
            await _write_message(
                writer,
                proto.Hello(device_id=self._device_id, device_name=_get_hostname()),
                phase="handshake_send",
                db_path=self.db_path,
                host=self.host,
                port=self.actual_port,
            )

            # 3. Bidirectional sync loop
            await self._sync_with_peer(reader, writer, peer_device_id, peer_name)

        except SyncPhaseError as exc:
            log.warning("Peer %s sync failed: %s", addr, exc)
        except TimeoutError:
            log.warning("Peer %s timed out", addr)
        except ConnectionResetError:
            log.info("Peer %s disconnected", addr)
        except Exception:
            log.exception("Error handling peer %s", addr)
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _sync_with_peer(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        peer_device_id: str,
        peer_name: str,
    ) -> None:
        """Perform bidirectional sync: push our changes, pull theirs."""
        conn = self._connect()
        try:
            hwm = get_peer_hwm(conn, peer_device_id)

            # ── Pull peer's changes (paged loop) ─────────────────────────
            log.debug(
                "Requesting changes from %s since=%d db=%s host=%s port=%s",
                peer_name,
                hwm,
                self.db_path,
                self.host,
                self.actual_port,
            )
            await _write_message(
                writer,
                proto.SyncRequest(since_id=hwm),
                phase="sync_request_send",
                db_path=self.db_path,
                host=self.host,
                port=self.actual_port,
            )

            total_received = 0
            current_since_id = hwm
            while True:
                msg = await _read_message(
                    reader,
                    timeout=30,
                    phase="sync_response_read",
                    db_path=self.db_path,
                    host=self.host,
                    port=self.actual_port,
                    empty_message=f"Peer {peer_name} closed the connection during sync",
                    invalid_message="Bad sync response from peer",
                )
                if not isinstance(msg, proto.SyncResponse):
                    exc = ConnectionError(f"Expected sync_response, got {type(msg).__name__}")
                    raise wrap_sync_exception(
                        log,
                        "sync_response_read",
                        exc,
                        db_path=self.db_path,
                        host=self.host,
                        port=self.actual_port,
                    ) from exc

                try:
                    if msg.changes:
                        log.debug(
                            "Applying %d remote changes from %s (%s) db=%s",
                            len(msg.changes),
                            peer_name,
                            peer_device_id[:8],
                            self.db_path,
                        )
                        apply_result = apply_changes(
                            conn,
                            msg.changes,
                            peer_device_id,
                            auto_commit=False,
                        )
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
                        db_path=self.db_path,
                        host=self.host,
                        port=self.actual_port,
                    ) from exc

                await _write_message(
                    writer,
                    proto.SyncAck(last_applied_id=last_id),
                    phase="sync_ack_send",
                    db_path=self.db_path,
                    host=self.host,
                    port=self.actual_port,
                )

                if not msg.has_more:
                    break

                current_since_id = last_id
                await _write_message(
                    writer,
                    proto.SyncRequest(since_id=current_since_id),
                    phase="sync_request_send",
                    db_path=self.db_path,
                    host=self.host,
                    port=self.actual_port,
                )

            log.info("Applied %d total changes from %s", total_received, peer_name)

            # ── Push our changes (paged loop) ────────────────────────────
            msg = await _read_message(
                reader,
                timeout=10,
                phase="sync_request_read",
                db_path=self.db_path,
                host=self.host,
                port=self.actual_port,
                empty_message=f"Peer {peer_name} closed the connection before requesting local changes",
                invalid_message="Bad sync request from peer",
            )
            if not isinstance(msg, proto.SyncRequest):
                exc = ConnectionError(f"Expected sync_request, got {type(msg).__name__}")
                raise wrap_sync_exception(
                    log,
                    "sync_request_read",
                    exc,
                    db_path=self.db_path,
                    host=self.host,
                    port=self.actual_port,
                ) from exc

            total_sent = 0
            current_since_id = msg.since_id
            while True:
                outbound, has_more, next_since_id = prepare_outbound_paged(
                    conn,
                    self._device_id,
                    current_since_id,
                )
                log.debug(
                    "Sending %d local changes to %s db=%s host=%s port=%s",
                    len(outbound),
                    peer_name,
                    self.db_path,
                    self.host,
                    self.actual_port,
                )
                await _write_message(
                    writer,
                    proto.SyncResponse(
                        changes=outbound,
                        has_more=has_more,
                        next_since_id=next_since_id,
                    ),
                    phase="sync_response_send",
                    db_path=self.db_path,
                    host=self.host,
                    port=self.actual_port,
                )
                total_sent += len(outbound)

                line = await _read_line(
                    reader,
                    timeout=10,
                    phase="sync_ack_read",
                    db_path=self.db_path,
                    host=self.host,
                    port=self.actual_port,
                    empty_message=(
                        f"Peer {peer_name} closed the connection before acknowledging local changes"
                    ),
                )
                if line:
                    try:
                        ack = proto.decode(line)
                    except ValueError as exc:
                        log.warning("Bad ACK from %s: %s", peer_name, exc)
                        return
                    if isinstance(ack, proto.SyncAck):
                        log.debug(
                            "Peer %s acknowledged up to %d",
                            peer_name,
                            ack.last_applied_id,
                        )

                if not has_more:
                    break

                next_request = await _read_message(
                    reader,
                    timeout=10,
                    phase="sync_request_read",
                    db_path=self.db_path,
                    host=self.host,
                    port=self.actual_port,
                    empty_message=(
                        f"Peer {peer_name} closed the connection before requesting the next page"
                    ),
                    invalid_message="Bad sync request from peer",
                )
                if not isinstance(next_request, proto.SyncRequest):
                    exc = ConnectionError(
                        f"Expected sync_request after acknowledgement, got {type(next_request).__name__}"
                    )
                    raise wrap_sync_exception(
                        log,
                        "sync_request_read",
                        exc,
                        db_path=self.db_path,
                        host=self.host,
                        port=self.actual_port,
                    ) from exc

                current_since_id = next_request.since_id

            log.info("Sent %d total changes to %s", total_sent, peer_name)

        finally:
            conn.close()

    # ── Lockfile ─────────────────────────────────────────────────────────

    def _acquire_lock(self) -> None:
        """Create a PID lockfile. Raises if another live process holds it."""
        try:
            fd = os.open(str(self._lockfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return
        except FileExistsError:
            pass

        # File exists — check if the holder is still alive
        try:
            stale_pid = int(self._lockfile.read_text().strip())
            if _pid_alive(stale_pid):
                raise SyncServerAlreadyRunning(
                    f"Another sync server (PID {stale_pid}) is already "
                    f"running against {self.db_path}"
                )
            log.info("Removing stale lockfile (PID %d no longer running)", stale_pid)
        except (ValueError, OSError):
            log.info("Removing invalid lockfile")

        # Remove stale/invalid lockfile and retry atomically
        # Note: On network filesystems (NFS/CIFS), unlink + O_EXCL is not atomic.
        # The race is guarded by the except FileExistsError below — if another
        # process wins the race, we raise SyncServerAlreadyRunning rather than
        # proceeding with a duplicate lock. For a true filesystem lock on Windows,
        # consider msvcrt.locking in a future iteration.
        with contextlib.suppress(OSError):
            self._lockfile.unlink()
        try:
            fd = os.open(str(self._lockfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
        except FileExistsError as exc:
            raise SyncServerAlreadyRunning(
                f"Another sync server acquired the lock for {self.db_path} while we were checking"
            ) from exc

    def _release_lock(self) -> None:
        """Remove the lockfile if it belongs to us."""
        try:
            if self._lockfile.exists():
                pid_text = self._lockfile.read_text().strip()
                if pid_text == str(os.getpid()):
                    # Minor TOCTOU here if file is replaced after read,
                    # but unlinking a new process's lockfile is benign
                    # (it will just re-acquire if needed).
                    self._lockfile.unlink()
        except OSError:
            pass

    # ── DB helper ─────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        return open_sync_connection(
            self.db_path,
            logger=log,
            host=self.host,
            port=self.actual_port,
        )


# ── Helpers ─────────────────────────────────────────────────────────────


def _pid_alive(pid: int) -> bool:
    """Check whether a process with the given PID exists."""
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            pid,
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but we can't signal it
    return True


def _get_hostname() -> str:
    import socket as _socket

    return _socket.gethostname()


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
