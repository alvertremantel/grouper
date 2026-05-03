"""
sync_ops.py — Shared sync helpers used by both server and client.

Functions for applying remote changes, tracking peer high-water marks,
and preparing outbound change payloads.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass

from .changelog import (
    DEFAULT_PAGE_SIZE,
    MissingParentError,
    RemoteApplyResult,
    apply_remote_change_result,
    get_changes_since_paged,
    observe_remote_version,
    resolve_fks_to_uuids,
    resolve_uuid_alias,
)
from .device import suppress_cdc, unsuppress_cdc
from .schema import DELETE_ORDER, INSERT_ORDER, KEY_PK_TABLES

log = logging.getLogger(__name__)


@dataclass
class ApplyChangesResult:
    applied_count: int = 0
    skipped_count: int = 0
    deferred_count: int = 0
    conflict_count: int = 0
    last_durable_change_id: int = 0

    def record_result(self, change_id: int, result: RemoteApplyResult) -> None:
        if result.applied:
            self.applied_count += 1
        elif result.status == "conflict":
            self.conflict_count += 1
        elif result.status in {"skipped", "aliased"}:
            self.skipped_count += 1
        if result.durable:
            self.last_durable_change_id = change_id


def get_peer_hwm(conn: sqlite3.Connection, peer_device_id: str) -> int:
    """Return the last changelog ID received from *peer_device_id*."""
    row = conn.execute(
        "SELECT last_changelog_id FROM sync_peers WHERE peer_device_id = ?",
        (peer_device_id,),
    ).fetchone()
    return row[0] if row else 0


def set_peer_hwm(
    conn: sqlite3.Connection,
    peer_device_id: str,
    peer_name: str,
    last_id: int,
) -> None:
    """Record the last changelog ID received from a peer."""
    from datetime import datetime

    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO sync_peers (peer_device_id, peer_name, last_changelog_id, last_sync_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(peer_device_id) DO UPDATE SET "
        "last_changelog_id = excluded.last_changelog_id, "
        "peer_name = excluded.peer_name, "
        "last_sync_at = excluded.last_sync_at",
        (peer_device_id, peer_name, last_id, now),
    )


def prepare_outbound(
    conn: sqlite3.Connection,
    changes: list[dict],
) -> list[dict]:
    """Resolve FK integers to UUIDs in change payloads for transit."""
    result = []
    for change in changes:
        payload = (
            json.loads(change["payload"])
            if isinstance(change["payload"], str)
            else change["payload"]
        )
        resolved = resolve_fks_to_uuids(conn, change["table_name"], payload)
        result.append(
            {
                "id": change["id"],
                "device_id": change["device_id"],
                "table_name": change["table_name"],
                "row_uuid": change["row_uuid"],
                "operation": change["operation"],
                "payload": resolved,
                "timestamp": change["timestamp"],
            }
        )
    return result


def prepare_outbound_paged(
    conn: sqlite3.Connection,
    local_device_id: str,
    since_id: int,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[dict], bool, int]:
    """Fetch one page of local changes and resolve FKs for transit.

    Returns:
        (outbound, has_more, next_since_id)
    """
    changes, has_more, next_since_id = get_changes_since_paged(
        conn,
        since_id,
        device_id=local_device_id,
        page_size=page_size,
    )
    outbound = prepare_outbound(conn, changes)
    return outbound, has_more, next_since_id


def _normalize_deferred_identity(conn: sqlite3.Connection, table_name: str, row_uuid: str) -> str:
    if table_name in KEY_PK_TABLES:
        return row_uuid
    return resolve_uuid_alias(conn, table_name, row_uuid) or row_uuid


def _change_version(operation: str, payload: dict) -> tuple[int, str]:
    return int(payload.get("sync_version") or 0), str(payload.get("sync_updated_by") or "")


def _compare_versions(left: tuple[int, str], right: tuple[int, str]) -> int:
    return (left > right) - (left < right)


def _store_deferred_change(
    conn: sqlite3.Connection,
    peer_device_id: str,
    change: dict,
    payload: dict,
    error: MissingParentError,
) -> None:
    canonical_row_uuid = _normalize_deferred_identity(
        conn, change["table_name"], change["row_uuid"]
    )
    canonical_payload = dict(payload)
    if change["table_name"] not in KEY_PK_TABLES:
        canonical_payload["uuid"] = canonical_row_uuid

    incoming_version = _change_version(change["operation"], canonical_payload)
    existing_rows = conn.execute(
        "SELECT id, operation, payload FROM sync_deferred_changes "
        "WHERE peer_device_id = ? AND table_name = ? AND row_uuid = ? ORDER BY id ASC",
        (peer_device_id, change["table_name"], canonical_row_uuid),
    ).fetchall()

    should_insert = True
    for existing in existing_rows:
        existing_payload = json.loads(existing["payload"])
        existing_version = _change_version(existing["operation"], existing_payload)
        if _compare_versions(incoming_version, existing_version) < 0:
            should_insert = False
            break

    if not should_insert:
        observe_remote_version(conn, incoming_version[0])
        return

    conn.execute(
        "DELETE FROM sync_deferred_changes WHERE peer_device_id = ? AND table_name = ? AND row_uuid = ?",
        (peer_device_id, change["table_name"], canonical_row_uuid),
    )
    conn.execute(
        """
        INSERT INTO sync_deferred_changes
        (peer_device_id, change_id, table_name, row_uuid, operation, payload, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            peer_device_id,
            change["id"],
            change["table_name"],
            canonical_row_uuid,
            change["operation"],
            json.dumps(canonical_payload, sort_keys=True),
            str(error),
        ),
    )
    observe_remote_version(conn, incoming_version[0])
    log.info(
        "Deferred change %s for %s row=%s due to missing parents",
        change["id"],
        change["table_name"],
        canonical_row_uuid,
    )


def apply_changes(
    conn: sqlite3.Connection,
    changes: list[dict],
    peer_device_id: str,
    *,
    auto_commit: bool = True,
) -> ApplyChangesResult:
    """Apply a batch of remote changes, respecting insert/delete ordering.

    Wraps the entire batch in an explicit transaction for atomicity.

    When *auto_commit* is ``False`` the data transaction is left open so
    the caller can bundle additional writes (e.g. a HWM update) into
    the same atomic commit. The caller must then explicitly finish or
    abort the batch to restore CDC state.
    """
    # Commit CDC suppression immediately so a data rollback cannot undo it.
    from .bootstrap import ensure_bootstrap_schema

    ensure_bootstrap_schema(conn)
    suppress_cdc(conn)
    conn.commit()
    try:
        # Start an explicit transaction if one is not already active
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")

        # Sort by dependency order
        inserts_updates = [c for c in changes if c["operation"] != "DELETE"]
        deletes = [c for c in changes if c["operation"] == "DELETE"]

        order_map = {t: i for i, t in enumerate(INSERT_ORDER)}
        inserts_updates.sort(key=lambda c: order_map.get(c["table_name"], 999))

        delete_order_map = {t: i for i, t in enumerate(DELETE_ORDER)}
        deletes.sort(key=lambda c: delete_order_map.get(c["table_name"], 999))

        result = ApplyChangesResult()
        for change in inserts_updates + deletes:
            payload = change.get("payload", {})
            if isinstance(payload, str):
                payload = json.loads(payload)
            try:
                change_result = apply_remote_change_result(
                    conn,
                    change["table_name"],
                    change["row_uuid"],
                    change["operation"],
                    payload,
                    peer_device_id=peer_device_id,
                )
                result.record_result(change["id"], change_result)
            except MissingParentError as e:
                _store_deferred_change(conn, peer_device_id, change, payload, e)
                result.deferred_count += 1
                result.last_durable_change_id = change["id"]

        # Retry any deferred changes that might now be unblocked
        result.applied_count += retry_deferred_changes(conn)

        if auto_commit:
            conn.commit()
        return result
    except Exception:
        abort_apply_changes(conn)
        raise
    finally:
        if auto_commit:
            finish_apply_changes(conn)


def finish_apply_changes(conn: sqlite3.Connection) -> None:
    """Commit a remote-apply batch and re-enable CDC atomically."""
    unsuppress_cdc(conn)
    conn.commit()


def abort_apply_changes(conn: sqlite3.Connection) -> None:
    """Abort a remote-apply batch and restore CDC state."""
    if conn.in_transaction:
        conn.rollback()
    unsuppress_cdc(conn)
    conn.commit()


def retry_deferred_changes(conn: sqlite3.Connection) -> int:
    """Retry deferred changes until no more progress can be made."""
    total_applied = 0
    while True:
        # Fetch all deferred changes, ordered by creation (id ascending)
        rows = conn.execute(
            """
            SELECT id, change_id, table_name, row_uuid, operation, payload, peer_device_id
            FROM sync_deferred_changes
            ORDER BY id ASC
            """
        ).fetchall()

        if not rows:
            break

        progress = False
        for row in rows:
            payload = json.loads(row["payload"])
            try:
                result = apply_remote_change_result(
                    conn,
                    row["table_name"],
                    row["row_uuid"],
                    row["operation"],
                    payload,
                    peer_device_id=row["peer_device_id"],
                )
                if result.applied:
                    total_applied += 1

                # Whether it applied successfully or was skipped,
                # it's no longer blocked by missing parents, so we remove it.
                conn.execute("DELETE FROM sync_deferred_changes WHERE id = ?", (row["id"],))
                progress = True
                if result.status == "skipped":
                    log.info(
                        "Discarded deferred change %s from %s after newer local state won",
                        row["change_id"],
                        row["peer_device_id"],
                    )
                log.info(
                    "Successfully processed previously deferred change %s from %s",
                    row["change_id"],
                    row["peer_device_id"],
                )
            except MissingParentError:
                # Still missing parents, leave it in the queue
                pass

        if not progress:
            # We made a full pass without applying anything, we're stuck until more data arrives
            break

    return total_applied
