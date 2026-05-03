"""Runtime helpers for sync diagnostics, DB setup, and user-facing errors."""

from __future__ import annotations

import logging
import sqlite3
import sys
from contextlib import suppress
from pathlib import Path

from grouper_core.database.connection import register_sqlite_functions

_PHASE_LABELS: dict[str, str] = {
    "local_database_open": "Failed during local database setup",
    "wal_mode": "Failed during local database setup",
    "cdc_setup": "Failed during local database setup",
    "connect": "Failed while connecting to peer",
    "handshake_send": "Failed during sync handshake",
    "handshake_receive": "Failed during sync handshake",
    "sync_request_send": "Failed while sending sync request",
    "sync_request_read": "Failed while reading sync request",
    "sync_response_send": "Failed while sending sync response",
    "sync_response_read": "Failed while reading sync response",
    "sync_ack_send": "Failed while sending sync acknowledgement",
    "sync_ack_read": "Failed while reading sync acknowledgement",
    "apply_changes": "Failed while applying remote changes",
    "server_start": "Failed while starting sync server",
}

_WINDOWS_DRIVE_REMOVABLE = 2
_WINDOWS_DRIVE_REMOTE = 4


class SyncPhaseError(RuntimeError):
    """A sync failure annotated with the phase where it occurred."""

    def __init__(
        self,
        phase: str,
        *,
        cause: BaseException | None = None,
        detail: str | None = None,
        db_path: Path | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        self.phase = phase
        self.cause = cause
        self.db_path = db_path
        self.host = host
        self.port = port

        message = _PHASE_LABELS.get(phase, "Sync failed")
        detail_text = detail or _describe_exception(cause)
        if detail_text:
            message = f"{message}: {detail_text}"
        super().__init__(message)


def format_sync_error(exc: BaseException) -> str:
    """Return a stable user-facing sync error message."""
    if isinstance(exc, SyncPhaseError):
        return str(exc)

    detail = str(exc).strip()
    if not detail:
        detail = type(exc).__name__
    return f"Unexpected sync error: {detail}"


def wrap_sync_exception(
    logger: logging.Logger,
    phase: str,
    exc: BaseException,
    *,
    db_path: Path | None,
    host: str | None = None,
    port: int | None = None,
) -> SyncPhaseError:
    """Log a sync failure with context and convert it to SyncPhaseError."""
    _log_sync_failure(logger, phase, exc, db_path=db_path, host=host, port=port)
    return SyncPhaseError(phase, cause=exc, db_path=db_path, host=host, port=port)


def prepare_local_sync_database(
    db_path: Path,
    *,
    logger: logging.Logger,
    host: str | None = None,
    port: int | None = None,
    busy_timeout_ms: int = 10_000,
) -> str:
    """Validate and initialize the local database for syncing."""
    conn = open_sync_connection(
        db_path,
        logger=logger,
        host=host,
        port=port,
        busy_timeout_ms=busy_timeout_ms,
    )
    try:
        return initialize_sync_metadata(
            conn,
            logger=logger,
            db_path=db_path,
            host=host,
            port=port,
        )
    finally:
        conn.close()


def open_sync_connection(
    db_path: Path,
    *,
    logger: logging.Logger,
    host: str | None = None,
    port: int | None = None,
    busy_timeout_ms: int = 10_000,
) -> sqlite3.Connection:
    """Open a SQLite connection configured for sync work."""
    db_path = Path(db_path)
    _validate_sync_database_path(db_path, logger=logger, host=host, port=port)

    logger.debug("Opening sync database db=%s host=%s port=%s", db_path, host, port)
    try:
        conn = sqlite3.connect(db_path)
    except Exception as exc:
        raise wrap_sync_exception(
            logger,
            "local_database_open",
            exc,
            db_path=db_path,
            host=host,
            port=port,
        ) from exc

    conn.row_factory = sqlite3.Row
    register_sqlite_functions(conn)
    try:
        logger.debug("Enabling WAL mode db=%s host=%s port=%s", db_path, host, port)
        row = conn.execute("PRAGMA journal_mode = WAL").fetchone()
        journal_mode = str(row[0]).lower() if row else ""
        if journal_mode != "wal":
            raise sqlite3.OperationalError(
                f"SQLite reported journal mode {journal_mode or 'unknown'!r} instead of 'wal'"
            )
    except Exception as exc:
        with suppress(Exception):
            conn.close()
        raise wrap_sync_exception(
            logger,
            "wal_mode",
            exc,
            db_path=db_path,
            host=host,
            port=port,
        ) from exc

    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
        return conn
    except Exception as exc:
        with suppress(Exception):
            conn.close()
        raise wrap_sync_exception(
            logger,
            "local_database_open",
            exc,
            db_path=db_path,
            host=host,
            port=port,
        ) from exc


def initialize_sync_metadata(
    conn: sqlite3.Connection,
    *,
    logger: logging.Logger,
    db_path: Path,
    host: str | None = None,
    port: int | None = None,
) -> str:
    """Ensure sync tables, device identity, and CDC triggers are ready."""
    from .bootstrap import ensure_bootstrap_schema, snapshot_for_bootstrap
    from .changelog import ensure_triggers, repair_legacy_sync_metadata
    from .device import enable_cdc, get_or_create_device_id

    logger.debug("Preparing CDC metadata db=%s host=%s port=%s", db_path, host, port)
    try:
        device_id = get_or_create_device_id(conn)
        ensure_bootstrap_schema(conn)
        ensure_triggers(conn)
        if repair_legacy_sync_metadata(conn, device_id):
            logger.info(
                "Normalized legacy sync metadata db=%s host=%s port=%s", db_path, host, port
            )
        # Snapshot existing data before enabling CDC to avoid triggering on our own snapshot
        snapshot_for_bootstrap(conn, device_id)
        enable_cdc(conn)
        return device_id
    except Exception as exc:
        raise wrap_sync_exception(
            logger,
            "cdc_setup",
            exc,
            db_path=db_path,
            host=host,
            port=port,
        ) from exc


def _validate_sync_database_path(
    db_path: Path,
    *,
    logger: logging.Logger,
    host: str | None,
    port: int | None,
) -> None:
    if sys.platform != "win32":
        return

    db_path_str = str(db_path)
    if db_path_str.startswith("\\\\"):
        logger.error(
            "Sync database path is unsupported db=%s host=%s port=%s reason=windows-network-share",
            db_path,
            host,
            port,
        )
        raise SyncPhaseError(
            "local_database_open",
            detail=(
                "SQLite sync is not supported for databases stored on Windows network shares "
                f"({db_path})"
            ),
            db_path=db_path,
            host=host,
            port=port,
        )

    drive_type = _windows_drive_type(db_path)
    if drive_type == _WINDOWS_DRIVE_REMOTE:
        logger.error(
            "Sync database path is unsupported db=%s host=%s port=%s reason=windows-network-drive",
            db_path,
            host,
            port,
        )
        raise SyncPhaseError(
            "local_database_open",
            detail=(
                "SQLite sync is not supported for databases stored on Windows network drives "
                f"({db_path})"
            ),
            db_path=db_path,
            host=host,
            port=port,
        )
    if drive_type == _WINDOWS_DRIVE_REMOVABLE:
        logger.error(
            "Sync database path is unsupported db=%s host=%s port=%s reason=windows-removable-drive",
            db_path,
            host,
            port,
        )
        raise SyncPhaseError(
            "local_database_open",
            detail=(
                "SQLite sync is not supported for databases stored on removable Windows drives "
                f"({db_path})"
            ),
            db_path=db_path,
            host=host,
            port=port,
        )


def _windows_drive_type(db_path: Path) -> int | None:
    if sys.platform != "win32":
        return None

    anchor = db_path.anchor
    if not anchor:
        return None

    try:
        import ctypes

        return int(ctypes.windll.kernel32.GetDriveTypeW(str(anchor)))
    except Exception:
        return None


def _log_sync_failure(
    logger: logging.Logger,
    phase: str,
    exc: BaseException,
    *,
    db_path: Path | None,
    host: str | None,
    port: int | None,
) -> None:
    logger.exception(
        "Sync phase failed phase=%s db=%s host=%s port=%s exc=%s errno=%s winerror=%s",
        phase,
        db_path,
        host,
        port,
        type(exc).__name__,
        getattr(exc, "errno", None),
        getattr(exc, "winerror", None),
    )


def _describe_exception(exc: BaseException | None) -> str:
    if exc is None:
        return ""

    detail = str(exc).strip()
    error_marker = _error_marker(exc)
    if error_marker and error_marker not in detail:
        if detail:
            return f"{error_marker}: {detail}"
        return error_marker
    if detail:
        return detail
    return type(exc).__name__


def _error_marker(exc: BaseException) -> str:
    winerror = getattr(exc, "winerror", None)
    if winerror is not None:
        return f"WinError {winerror}"

    errno = getattr(exc, "errno", None)
    if errno is not None:
        return f"Errno {errno}"

    return ""
