"""
changelog.py — CDC trigger management and changelog queries.

Triggers record every INSERT/UPDATE/DELETE on synced tables into
sync_changelog.  They are dormant until a row exists in sync_state
(i.e., until the user enables sync).

Triggers are created dynamically from PRAGMA table_info so they always
match the current schema — safe across migrations.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass

from grouper_core.database.connection import register_sqlite_functions

from .device import suppress_cdc, unsuppress_cdc
from .schema import (
    FK_MAP,
    KEY_PK_TABLES,
    NATURAL_KEY_POLICIES,
    SYNCED_TABLES,
)

log = logging.getLogger(__name__)

_SYNCED_TABLES_SET: set[str] = set(SYNCED_TABLES)
_MERGE_POLICY = "merge"
_REJECT_POLICY = "reject"


@dataclass(frozen=True)
class RemoteApplyResult:
    status: str
    canonical_row_uuid: str
    observed_version: int

    @property
    def applied(self) -> bool:
        return self.status in {"applied", "aliased"}

    @property
    def durable(self) -> bool:
        return self.status in {"applied", "skipped", "aliased", "conflict"}


def _version_tuple(sync_version: int | None, sync_updated_by: str | None) -> tuple[int, str]:
    return (int(sync_version or 0), str(sync_updated_by or ""))


def _compare_versions(
    incoming_version: int | None,
    incoming_updated_by: str | None,
    current_version: int | None,
    current_updated_by: str | None,
) -> int:
    incoming = _version_tuple(incoming_version, incoming_updated_by)
    current = _version_tuple(current_version, current_updated_by)
    return (incoming > current) - (incoming < current)


def _normalize_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized.lower() if normalized else None


def _ensure_sync_schema(conn: sqlite3.Connection) -> None:
    for table_name in SYNCED_TABLES:
        cols = _valid_columns(conn, table_name)
        if "sync_version" not in cols:
            conn.execute(
                f'ALTER TABLE "{table_name}" ADD COLUMN sync_version INTEGER NOT NULL DEFAULT 0'
            )
        if "sync_updated_by" not in cols:
            conn.execute(
                f'ALTER TABLE "{table_name}" ADD COLUMN sync_updated_by TEXT NOT NULL DEFAULT ""'
            )

    sync_state_cols = {r[1] for r in conn.execute("PRAGMA table_info(sync_state)").fetchall()}
    if "logical_clock" not in sync_state_cols:
        conn.execute("ALTER TABLE sync_state ADD COLUMN logical_clock INTEGER NOT NULL DEFAULT 0")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sync_tombstones (
            table_name      TEXT NOT NULL,
            row_uuid        TEXT NOT NULL,
            sync_version    INTEGER NOT NULL,
            sync_updated_by TEXT NOT NULL,
            deleted_payload TEXT NOT NULL DEFAULT '{}',
            created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY (table_name, row_uuid)
        );

        CREATE TABLE IF NOT EXISTS sync_uuid_aliases (
            table_name   TEXT NOT NULL,
            source_uuid  TEXT NOT NULL,
            target_uuid  TEXT NOT NULL,
            created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY (table_name, source_uuid)
        );

        CREATE TABLE IF NOT EXISTS sync_conflicts (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            peer_device_id TEXT NOT NULL DEFAULT '',
            table_name     TEXT NOT NULL,
            row_uuid       TEXT NOT NULL,
            conflict_type  TEXT NOT NULL,
            natural_key    TEXT,
            payload        TEXT NOT NULL DEFAULT '{}',
            created_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        """
    )


def _row_json_select(cols: list[str], table_alias: str) -> str:
    parts: list[str] = []
    for c in cols:
        parts.append(f"'{c}'")
        parts.append(f'{table_alias}."{c}"')
    return f"json_object({', '.join(parts)})"


def _register_uuid_alias(
    conn: sqlite3.Connection,
    table_name: str,
    source_uuid: str,
    target_uuid: str,
) -> None:
    if source_uuid == target_uuid:
        return
    conn.execute(
        "INSERT INTO sync_uuid_aliases (table_name, source_uuid, target_uuid) VALUES (?, ?, ?) "
        "ON CONFLICT(table_name, source_uuid) DO UPDATE SET target_uuid = excluded.target_uuid",
        (table_name, source_uuid, target_uuid),
    )


def resolve_uuid_alias(
    conn: sqlite3.Connection, table_name: str, row_uuid: str | None
) -> str | None:
    if row_uuid is None:
        return None
    seen: set[str] = set()
    current = row_uuid
    while current not in seen:
        seen.add(current)
        row = conn.execute(
            "SELECT target_uuid FROM sync_uuid_aliases WHERE table_name = ? AND source_uuid = ?",
            (table_name, current),
        ).fetchone()
        if row is None:
            return current
        current = row[0] if isinstance(row, tuple) else row["target_uuid"]
    return current


def _get_tombstone(conn: sqlite3.Connection, table_name: str, row_uuid: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM sync_tombstones WHERE table_name = ? AND row_uuid = ?",
        (table_name, row_uuid),
    ).fetchone()


def _upsert_tombstone(
    conn: sqlite3.Connection,
    table_name: str,
    row_uuid: str,
    sync_version: int,
    sync_updated_by: str,
    payload: dict,
) -> None:
    conn.execute(
        "INSERT INTO sync_tombstones "
        "(table_name, row_uuid, sync_version, sync_updated_by, deleted_payload) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(table_name, row_uuid) DO UPDATE SET "
        "sync_version = excluded.sync_version, "
        "sync_updated_by = excluded.sync_updated_by, "
        "deleted_payload = excluded.deleted_payload, "
        "created_at = datetime('now', 'localtime')",
        (table_name, row_uuid, sync_version, sync_updated_by, json.dumps(payload, sort_keys=True)),
    )


def _delete_tombstone(conn: sqlite3.Connection, table_name: str, row_uuid: str) -> None:
    conn.execute(
        "DELETE FROM sync_tombstones WHERE table_name = ? AND row_uuid = ?",
        (table_name, row_uuid),
    )


def observe_remote_version(conn: sqlite3.Connection, sync_version: int | None) -> None:
    observed_version = int(sync_version or 0)
    conn.execute(
        "INSERT OR IGNORE INTO sync_state (id, device_id, syncing, logical_clock) "
        "VALUES (1, lower(hex(randomblob(16))), 0, 0)"
    )
    conn.execute(
        "UPDATE sync_state SET logical_clock = MAX(logical_clock, ?) WHERE id = 1",
        (observed_version,),
    )


def repair_legacy_sync_metadata(conn: sqlite3.Connection, device_id: str) -> bool:
    if not device_id:
        return False

    _ensure_sync_schema(conn)
    original_syncing_row = conn.execute("SELECT syncing FROM sync_state WHERE id = 1").fetchone()
    original_syncing = int(original_syncing_row[0] if original_syncing_row is not None else 0)

    suppress_cdc(conn)
    conn.commit()
    try:
        max_version = int(
            conn.execute("SELECT COALESCE(MAX(sync_version), 0) FROM sync_tombstones").fetchone()[0]
            or 0
        )
        changed = False

        for table_name in SYNCED_TABLES:
            identity_column = "key" if table_name in KEY_PK_TABLES else "uuid"
            rows = conn.execute(
                f'SELECT rowid AS row_id, sync_version, sync_updated_by FROM "{table_name}" '
                f'WHERE COALESCE(sync_version, 0) <= 0 OR COALESCE(sync_updated_by, "") = "" '
                f'ORDER BY "{identity_column}", rowid'
            ).fetchall()
            for row in rows:
                sync_version = int(row["sync_version"] or 0)
                sync_updated_by = str(row["sync_updated_by"] or "")
                if sync_version <= 0:
                    max_version += 1
                    sync_version = max_version
                if not sync_updated_by:
                    sync_updated_by = device_id
                conn.execute(
                    f'UPDATE "{table_name}" SET sync_version = ?, sync_updated_by = ? WHERE rowid = ?',
                    (sync_version, sync_updated_by, row["row_id"]),
                )
                changed = True

        for table_name in SYNCED_TABLES:
            row = conn.execute(
                f'SELECT COALESCE(MAX(sync_version), 0) FROM "{table_name}"'
            ).fetchone()
            max_version = max(max_version, int(row[0] or 0))

        conn.execute(
            "UPDATE sync_state SET logical_clock = MAX(logical_clock, ?) WHERE id = 1",
            (max_version,),
        )
        conn.commit()
        return changed
    finally:
        if original_syncing == 0:
            unsuppress_cdc(conn)
        else:
            conn.execute("UPDATE sync_state SET syncing = 1 WHERE id = 1")
        conn.commit()


def _normalize_live_payload_identity(
    table_name: str, payload: dict, canonical_row_uuid: str
) -> dict:
    normalized = dict(payload)
    if table_name not in KEY_PK_TABLES:
        normalized["uuid"] = canonical_row_uuid
    return normalized


def _finalize_remote_result(
    conn: sqlite3.Connection,
    *,
    status: str,
    canonical_row_uuid: str,
    observed_version: int,
) -> RemoteApplyResult:
    result = RemoteApplyResult(status, canonical_row_uuid, observed_version)
    if result.durable:
        observe_remote_version(conn, observed_version)
    return result


def _coalesce_alias_tombstone(
    conn: sqlite3.Connection,
    table_name: str,
    source_uuid: str,
    canonical_uuid: str,
    payload: dict,
    incoming_version: int,
    incoming_updated_by: str,
) -> None:
    if source_uuid == canonical_uuid:
        return

    source_tombstone = _get_tombstone(conn, table_name, source_uuid)
    canonical_tombstone = _get_tombstone(conn, table_name, canonical_uuid)
    winning_version = incoming_version
    winning_updated_by = incoming_updated_by
    winning_payload = _normalize_live_payload_identity(table_name, payload, canonical_uuid)

    if (
        source_tombstone is not None
        and _compare_versions(
            source_tombstone["sync_version"],
            source_tombstone["sync_updated_by"],
            winning_version,
            winning_updated_by,
        )
        > 0
    ):
        winning_version = int(source_tombstone["sync_version"])
        winning_updated_by = str(source_tombstone["sync_updated_by"])
        winning_payload = json.loads(source_tombstone["deleted_payload"])
        if table_name not in KEY_PK_TABLES:
            winning_payload["uuid"] = canonical_uuid

    if (
        canonical_tombstone is None
        or _compare_versions(
            winning_version,
            winning_updated_by,
            canonical_tombstone["sync_version"],
            canonical_tombstone["sync_updated_by"],
        )
        >= 0
    ):
        _upsert_tombstone(
            conn,
            table_name,
            canonical_uuid,
            winning_version,
            winning_updated_by,
            winning_payload,
        )

    _delete_tombstone(conn, table_name, source_uuid)


def _record_conflict(
    conn: sqlite3.Connection,
    peer_device_id: str,
    table_name: str,
    row_uuid: str,
    conflict_type: str,
    natural_key: str | None,
    payload: dict,
) -> None:
    conn.execute(
        "INSERT INTO sync_conflicts "
        "(peer_device_id, table_name, row_uuid, conflict_type, natural_key, payload) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            peer_device_id,
            table_name,
            row_uuid,
            conflict_type,
            natural_key,
            json.dumps(payload, sort_keys=True),
        ),
    )


def _find_natural_key_match(
    conn: sqlite3.Connection,
    table_name: str,
    payload: dict,
) -> tuple[str, sqlite3.Row] | None:
    policy = NATURAL_KEY_POLICIES.get(table_name)
    if policy is None:
        return None
    _, column_name = policy
    normalized = _normalize_name(payload.get(column_name))
    if normalized is None:
        return None
    row = conn.execute(
        f'SELECT * FROM "{table_name}" WHERE "{column_name}" = ? COLLATE NOCASE LIMIT 1',
        (payload[column_name],),
    ).fetchone()
    if row is None:
        return None
    return normalized, row


DEFAULT_PAGE_SIZE = 1_000
_MAX_PAGE_SIZE = 9_000
_BYTE_BUDGET = 8 * 1024 * 1024  # 8 MB


def _validate_table(table_name: str) -> str:
    if table_name not in _SYNCED_TABLES_SET:
        raise ValueError(f"Invalid sync table: {table_name!r}")
    return table_name


def _validate_columns(
    conn: sqlite3.Connection,
    table_name: str,
    columns: list[str],
) -> list[str]:
    valid = _valid_columns(conn, table_name)
    bad = set(columns) - valid
    if bad:
        raise ValueError(f"Invalid columns for {table_name!r}: {bad!r}")
    return columns


# ── Trigger creation ────────────────────────────────────────────────────


def _col_names(conn: sqlite3.Connection, table: str) -> list[str]:
    """Return all column names for *table*."""
    _validate_table(table)
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [r[1] for r in rows]


def _json_obj_expr(cols: list[str], prefix: str) -> str:
    """Build a SQLite json_object() expression for the given columns.

    Example: json_object('id', NEW.id, 'name', NEW.name)
    """
    parts: list[str] = []
    for c in cols:
        parts.append(f"'{c}'")
        parts.append(f"{prefix}.{c}")
    return f"json_object({', '.join(parts)})"


def ensure_triggers(conn: sqlite3.Connection) -> None:
    """Create (or replace) CDC triggers for every synced table.

    Also installs BEFORE INSERT triggers to auto-generate UUIDs for
    tables whose uuid column was added via ALTER TABLE (which can't
    carry a DEFAULT expression with randomblob).

    Safe to call repeatedly — drops existing triggers first.
    """
    register_sqlite_functions(conn)
    suppress_cdc(conn)
    conn.commit()
    _ensure_sync_schema(conn)

    try:
        for table in SYNCED_TABLES:
            if table in KEY_PK_TABLES:
                _ensure_triggers_key_pk(conn, table)
                continue

            cols = _col_names(conn, table)
            if "uuid" not in cols:
                log.warning("Table %s has no uuid column — skipping triggers", table)
                continue

            payload_cols = cols
            gate = (
                "(SELECT COUNT(*) FROM sync_state) = 1 "
                "AND (SELECT syncing FROM sync_state WHERE id = 1) = 0"
            )

            for old_op in ("insert", "update", "delete"):
                conn.execute(f"DROP TRIGGER IF EXISTS cdc_{table}_{old_op}")

            conn.execute(f"""
                CREATE TRIGGER cdc_{table}_insert
                AFTER INSERT ON {table}
                WHEN {gate}
                BEGIN
                    SELECT next_sync_version();
                    UPDATE {table}
                    SET uuid = COALESCE(uuid, lower(hex(randomblob(16)))),
                        sync_version = (SELECT logical_clock FROM sync_state WHERE id = 1),
                        sync_updated_by = current_device_id()
                    WHERE rowid = NEW.rowid;
                    INSERT INTO sync_changelog
                        (device_id, table_name, row_uuid, operation, payload, timestamp)
                    SELECT
                        current_device_id(),
                        '{table}',
                        t.uuid,
                        'INSERT',
                        {_row_json_select(payload_cols, "t")},
                        strftime('%Y-%m-%dT%H:%M:%f', 'now', 'localtime')
                    FROM {table} AS t
                    WHERE t.rowid = NEW.rowid;
                END
            """)

            conn.execute(f"""
                CREATE TRIGGER cdc_{table}_update
                AFTER UPDATE ON {table}
                WHEN {gate}
                  AND NEW.sync_version = OLD.sync_version
                  AND NEW.sync_updated_by = OLD.sync_updated_by
                BEGIN
                    SELECT next_sync_version();
                    UPDATE {table}
                    SET sync_version = (SELECT logical_clock FROM sync_state WHERE id = 1),
                        sync_updated_by = current_device_id()
                    WHERE rowid = NEW.rowid;
                    INSERT INTO sync_changelog
                        (device_id, table_name, row_uuid, operation, payload, timestamp)
                    SELECT
                        current_device_id(),
                        '{table}',
                        t.uuid,
                        'UPDATE',
                        {_row_json_select(payload_cols, "t")},
                        strftime('%Y-%m-%dT%H:%M:%f', 'now', 'localtime')
                    FROM {table} AS t
                    WHERE t.rowid = NEW.rowid;
                END
            """)

            conn.execute(f"""
                CREATE TRIGGER cdc_{table}_delete
                AFTER DELETE ON {table}
                WHEN {gate}
                BEGIN
                    SELECT next_sync_version();
                    INSERT INTO sync_tombstones
                        (table_name, row_uuid, sync_version, sync_updated_by, deleted_payload)
                    VALUES (
                        '{table}',
                        OLD.uuid,
                        (SELECT logical_clock FROM sync_state WHERE id = 1),
                        current_device_id(),
                        json_set(
                            {_json_obj_expr(payload_cols, "OLD")},
                            '$.sync_version', (SELECT logical_clock FROM sync_state WHERE id = 1),
                            '$.sync_updated_by', current_device_id()
                        )
                    )
                    ON CONFLICT(table_name, row_uuid) DO UPDATE SET
                        sync_version = excluded.sync_version,
                        sync_updated_by = excluded.sync_updated_by,
                        deleted_payload = excluded.deleted_payload,
                        created_at = datetime('now', 'localtime');
                    INSERT INTO sync_changelog
                        (device_id, table_name, row_uuid, operation, payload, timestamp)
                    VALUES (
                        current_device_id(),
                        '{table}',
                        OLD.uuid,
                        'DELETE',
                        json_set(
                            {_json_obj_expr(payload_cols, "OLD")},
                            '$.sync_version', (SELECT logical_clock FROM sync_state WHERE id = 1),
                            '$.sync_updated_by', current_device_id()
                        ),
                        strftime('%Y-%m-%dT%H:%M:%f', 'now', 'localtime')
                    );
                END
            """)

        unsuppress_cdc(conn)
        conn.commit()
        log.info("CDC triggers installed for %d tables", len(SYNCED_TABLES))
    except Exception:
        unsuppress_cdc(conn)
        conn.commit()
        raise


def _ensure_triggers_key_pk(conn: sqlite3.Connection, table: str) -> None:
    """Special-case triggers for tables with a TEXT PK (e.g. settings)."""
    cols = _col_names(conn, table)
    gate = (
        "(SELECT COUNT(*) FROM sync_state) = 1 "
        "AND (SELECT syncing FROM sync_state WHERE id = 1) = 0"
    )
    pk = "key"  # settings table PK

    for old_op in ("insert", "update", "delete"):
        conn.execute(f"DROP TRIGGER IF EXISTS cdc_{table}_{old_op}")

    cols = _col_names(conn, table)

    conn.execute(f"""
        CREATE TRIGGER cdc_{table}_insert
        AFTER INSERT ON {table}
        WHEN {gate}
        BEGIN
            SELECT next_sync_version();
            UPDATE {table}
            SET sync_version = (SELECT logical_clock FROM sync_state WHERE id = 1),
                sync_updated_by = current_device_id()
            WHERE rowid = NEW.rowid;
            INSERT INTO sync_changelog
                (device_id, table_name, row_uuid, operation, payload, timestamp)
            SELECT
                current_device_id(),
                '{table}',
                t.{pk},
                'INSERT',
                {_row_json_select(cols, "t")},
                strftime('%Y-%m-%dT%H:%M:%f', 'now', 'localtime')
            FROM {table} AS t
            WHERE t.rowid = NEW.rowid;
        END
    """)

    conn.execute(f"""
        CREATE TRIGGER cdc_{table}_update
        AFTER UPDATE ON {table}
        WHEN {gate}
          AND NEW.sync_version = OLD.sync_version
          AND NEW.sync_updated_by = OLD.sync_updated_by
        BEGIN
            SELECT next_sync_version();
            UPDATE {table}
            SET sync_version = (SELECT logical_clock FROM sync_state WHERE id = 1),
                sync_updated_by = current_device_id()
            WHERE rowid = NEW.rowid;
            INSERT INTO sync_changelog
                (device_id, table_name, row_uuid, operation, payload, timestamp)
            SELECT
                current_device_id(),
                '{table}',
                t.{pk},
                'UPDATE',
                {_row_json_select(cols, "t")},
                strftime('%Y-%m-%dT%H:%M:%f', 'now', 'localtime')
            FROM {table} AS t
            WHERE t.rowid = NEW.rowid;
        END
    """)

    conn.execute(f"""
        CREATE TRIGGER cdc_{table}_delete
        AFTER DELETE ON {table}
        WHEN {gate}
        BEGIN
            SELECT next_sync_version();
            INSERT INTO sync_tombstones
                (table_name, row_uuid, sync_version, sync_updated_by, deleted_payload)
            VALUES (
                '{table}',
                OLD.{pk},
                (SELECT logical_clock FROM sync_state WHERE id = 1),
                current_device_id(),
                json_set(
                    {_json_obj_expr(cols, "OLD")},
                    '$.sync_version', (SELECT logical_clock FROM sync_state WHERE id = 1),
                    '$.sync_updated_by', current_device_id()
                )
            )
            ON CONFLICT(table_name, row_uuid) DO UPDATE SET
                sync_version = excluded.sync_version,
                sync_updated_by = excluded.sync_updated_by,
                deleted_payload = excluded.deleted_payload,
                created_at = datetime('now', 'localtime');
            INSERT INTO sync_changelog
                (device_id, table_name, row_uuid, operation, payload, timestamp)
            VALUES (
                current_device_id(),
                '{table}',
                OLD.{pk},
                'DELETE',
                json_set(
                    {_json_obj_expr(cols, "OLD")},
                    '$.sync_version', (SELECT logical_clock FROM sync_state WHERE id = 1),
                    '$.sync_updated_by', current_device_id()
                ),
                strftime('%Y-%m-%dT%H:%M:%f', 'now', 'localtime')
            );
        END
    """)


# ── Changelog queries ───────────────────────────────────────────────────


def get_changes_since(
    conn: sqlite3.Connection,
    since_id: int = 0,
    device_id: str | None = None,
) -> list[dict]:
    """Return changelog entries after *since_id*.

    If *device_id* is given, only return entries originating from that device.
    """
    if device_id:
        rows = conn.execute(
            "SELECT * FROM sync_changelog WHERE id > ? AND device_id = ? ORDER BY id",
            (since_id, device_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sync_changelog WHERE id > ? ORDER BY id",
            (since_id,),
        ).fetchall()

    return [_row_to_dict(r) for r in rows]


def get_local_changes_since(
    conn: sqlite3.Connection,
    local_device_id: str,
    since_id: int = 0,
) -> list[dict]:
    """Return changes made by the local device since *since_id*."""
    return get_changes_since(conn, since_id, device_id=local_device_id)


def get_changes_since_paged(
    conn: sqlite3.Connection,
    since_id: int = 0,
    device_id: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[dict], bool, int]:
    """Return at most *page_size* changelog entries after *since_id*.

    Also enforces a byte-budget cap on the total encoded payload so that
    large individual rows cannot still exceed transport limits.

    Returns:
        (changes, has_more, next_since_id)
        - *changes*: list of changelog row dicts for this page
        - *has_more*: True if more rows exist beyond this page
        - *next_since_id*: the changelog id to pass as since_id for the
          next page (highest id in this page, or *since_id* if empty)
    """
    page_size = max(1, min(page_size, _MAX_PAGE_SIZE))
    limit = page_size + 1  # fetch one extra to detect has_more

    if device_id:
        rows = conn.execute(
            "SELECT * FROM sync_changelog WHERE id > ? AND device_id = ? ORDER BY id LIMIT ?",
            (since_id, device_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sync_changelog WHERE id > ? ORDER BY id LIMIT ?",
            (since_id, limit),
        ).fetchall()

    has_more = len(rows) > page_size
    if has_more:
        rows = rows[:page_size]

    result: list[dict] = []
    total_bytes = 0
    next_since_id = since_id

    for r in rows:
        d = _row_to_dict(r)
        row_bytes = len(json.dumps(d, separators=(",", ":")).encode())
        if row_bytes > _BYTE_BUDGET and not result:
            log.error(
                "Rejecting oversized sync row change_id=%s table=%s encoded_size=%s budget=%s",
                d["id"],
                d["table_name"],
                row_bytes,
                _BYTE_BUDGET,
            )
            raise OversizedChangeError(d["id"], d["table_name"], row_bytes, _BYTE_BUDGET)
        if total_bytes + row_bytes > _BYTE_BUDGET and result:
            has_more = True
            break
        result.append(d)
        total_bytes += row_bytes
        next_since_id = d["id"]

    return result, has_more, next_since_id


def resolve_fks_to_uuids(
    conn: sqlite3.Connection,
    table_name: str,
    payload: dict,
) -> dict:
    """Replace integer FK values with the UUID of the referenced row.

    Adds '{fk_col}_uuid' keys and removes the original integer keys.
    """
    _validate_table(table_name)
    fk_defs = FK_MAP.get(table_name, {})
    resolved = dict(payload)
    for fk_col, ref_table in fk_defs.items():
        _validate_table(ref_table)
        local_id = resolved.get(fk_col)
        if local_id is None:
            resolved[f"{fk_col}_uuid"] = None
            resolved.pop(fk_col, None)
            continue
        if ref_table in KEY_PK_TABLES:
            resolved[f"{fk_col}_uuid"] = local_id  # already a text key
            del resolved[fk_col]
            continue
        row = conn.execute(f'SELECT uuid FROM "{ref_table}" WHERE id = ?', (local_id,)).fetchone()
        resolved[f"{fk_col}_uuid"] = row[0] if row else None
        del resolved[fk_col]
    return resolved


class MissingParentError(Exception):
    """Raised when a remote payload references a UUID that does not exist locally."""

    def __init__(self, table_name: str, missing_uuids: dict[str, str]):
        super().__init__(f"Missing parents for {table_name}: {missing_uuids}")
        self.table_name = table_name
        self.missing_uuids = missing_uuids


class OversizedChangeError(RuntimeError):
    def __init__(
        self, change_id: int, table_name: str, encoded_size: int, byte_budget: int
    ) -> None:
        self.change_id = change_id
        self.table_name = table_name
        self.encoded_size = encoded_size
        self.byte_budget = byte_budget
        super().__init__(
            "Sync change exceeds page byte budget: "
            f"change_id={change_id} table={table_name} encoded_size={encoded_size} budget={byte_budget}"
        )


def resolve_uuids_to_fks(
    conn: sqlite3.Connection,
    table_name: str,
    payload: dict,
) -> dict:
    """Replace '{fk_col}_uuid' keys with local integer IDs.

    Raises MissingParentError if any non-null FK references a UUID that doesn't exist locally.
    """
    _validate_table(table_name)
    fk_defs = FK_MAP.get(table_name, {})
    resolved = dict(payload)
    missing = {}

    for fk_col, ref_table in fk_defs.items():
        _validate_table(ref_table)
        uuid_key = f"{fk_col}_uuid"
        ref_uuid = resolved.pop(uuid_key, None)
        if ref_uuid is None:
            resolved[fk_col] = None
            continue
        if ref_table in KEY_PK_TABLES:
            resolved[fk_col] = resolve_uuid_alias(conn, ref_table, ref_uuid)
            continue
        canonical_uuid = resolve_uuid_alias(conn, ref_table, ref_uuid) or ref_uuid
        row = conn.execute(
            f'SELECT id FROM "{ref_table}" WHERE uuid = ?', (canonical_uuid,)
        ).fetchone()
        if row:
            resolved[fk_col] = row[0]
        else:
            missing[fk_col] = canonical_uuid

    if missing:
        raise MissingParentError(table_name, missing)

    return resolved


# ── Apply remote changes ────────────────────────────────────────────────


def _valid_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """Return the set of valid column names for *table_name*."""
    _validate_table(table_name)
    rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return {r[1] for r in rows}


def apply_remote_change(
    conn: sqlite3.Connection,
    table_name: str,
    row_uuid: str,
    operation: str,
    payload: dict,
    peer_device_id: str = "",
) -> bool:
    """Apply a single remote change to the local database."""
    return apply_remote_change_result(
        conn,
        table_name,
        row_uuid,
        operation,
        payload,
        peer_device_id=peer_device_id,
    ).applied


def apply_remote_change_result(
    conn: sqlite3.Connection,
    table_name: str,
    row_uuid: str,
    operation: str,
    payload: dict,
    peer_device_id: str = "",
) -> RemoteApplyResult:
    """Apply a remote change and return its durable outcome."""
    try:
        _validate_table(table_name)
    except ValueError:
        log.warning("Rejecting change for unknown table %r", table_name)
        return RemoteApplyResult("invalid", row_uuid, 0)

    _ensure_sync_schema(conn)

    if table_name in KEY_PK_TABLES:
        return _apply_key_pk_change_result(
            conn,
            table_name,
            row_uuid,
            operation,
            payload,
            peer_device_id=peer_device_id,
        )

    incoming_uuid = row_uuid
    canonical_uuid = resolve_uuid_alias(conn, table_name, row_uuid) or row_uuid

    # Resolve FK UUIDs → local integer IDs
    resolved = resolve_uuids_to_fks(conn, table_name, payload)
    resolved = _normalize_live_payload_identity(table_name, resolved, canonical_uuid)

    # Remove 'id' from payload — we use our own local autoincrement IDs
    resolved.pop("id", None)

    # Validate column names against the actual schema
    valid_cols = _valid_columns(conn, table_name)
    # Ignore keys starting with '_' (e.g. '_bootstrap')
    resolved_cols = {k for k in resolved if not k.startswith("_")}
    bad_cols = resolved_cols - valid_cols
    if bad_cols:
        log.warning("Rejecting change: invalid columns %s for table %r", bad_cols, table_name)
        return RemoteApplyResult("invalid", canonical_uuid, 0)

    incoming_version = int(resolved.get("sync_version") or 0)
    incoming_updated_by = str(resolved.get("sync_updated_by") or "")
    canonical_payload = _normalize_live_payload_identity(table_name, payload, canonical_uuid)

    if operation == "DELETE":
        tombstone = _get_tombstone(conn, table_name, canonical_uuid)
        if canonical_uuid != incoming_uuid:
            _register_uuid_alias(conn, table_name, incoming_uuid, canonical_uuid)
            _coalesce_alias_tombstone(
                conn,
                table_name,
                incoming_uuid,
                canonical_uuid,
                payload,
                incoming_version,
                incoming_updated_by,
            )

        existing = conn.execute(
            f'SELECT * FROM "{table_name}" WHERE uuid = ?', (canonical_uuid,)
        ).fetchone()
        if (
            existing is not None
            and _compare_versions(
                incoming_version,
                incoming_updated_by,
                existing["sync_version"],
                existing["sync_updated_by"],
            )
            < 0
        ):
            return _finalize_remote_result(
                conn,
                status="skipped",
                canonical_row_uuid=canonical_uuid,
                observed_version=incoming_version,
            )
        if (
            tombstone is not None
            and _compare_versions(
                incoming_version,
                incoming_updated_by,
                tombstone["sync_version"],
                tombstone["sync_updated_by"],
            )
            <= 0
        ):
            return _finalize_remote_result(
                conn,
                status="skipped",
                canonical_row_uuid=canonical_uuid,
                observed_version=incoming_version,
            )
        if existing is not None:
            conn.execute(f'DELETE FROM "{table_name}" WHERE uuid = ?', (canonical_uuid,))
        _upsert_tombstone(
            conn,
            table_name,
            canonical_uuid,
            incoming_version,
            incoming_updated_by,
            canonical_payload,
        )
        return _finalize_remote_result(
            conn,
            status="applied",
            canonical_row_uuid=canonical_uuid,
            observed_version=incoming_version,
        )

    # Check if row already exists locally
    existing = conn.execute(
        f'SELECT * FROM "{table_name}" WHERE uuid = ?', (canonical_uuid,)
    ).fetchone()
    tombstone = _get_tombstone(conn, table_name, canonical_uuid)

    natural_key_match = _find_natural_key_match(conn, table_name, resolved)
    if natural_key_match is not None:
        natural_key, natural_row = natural_key_match
        if natural_row["uuid"] != canonical_uuid and existing is None:
            policy, _ = NATURAL_KEY_POLICIES[table_name]
            if policy == _MERGE_POLICY:
                _register_uuid_alias(conn, table_name, incoming_uuid, natural_row["uuid"])
                _coalesce_alias_tombstone(
                    conn,
                    table_name,
                    incoming_uuid,
                    natural_row["uuid"],
                    payload,
                    incoming_version,
                    incoming_updated_by,
                )
                return _finalize_remote_result(
                    conn,
                    status="aliased",
                    canonical_row_uuid=natural_row["uuid"],
                    observed_version=incoming_version,
                )
            if policy == _REJECT_POLICY:
                _record_conflict(
                    conn,
                    peer_device_id,
                    table_name,
                    incoming_uuid,
                    "natural_key_conflict",
                    natural_key,
                    payload,
                )
                return _finalize_remote_result(
                    conn,
                    status="conflict",
                    canonical_row_uuid=canonical_uuid,
                    observed_version=incoming_version,
                )

    # Build column list (exclude 'id', include everything else that's valid)
    cols = [c for c in resolved if c != "id" and not c.startswith("_")]
    _validate_columns(conn, table_name, cols)

    if existing is None and operation in ("INSERT", "UPDATE"):
        if (
            tombstone is not None
            and _compare_versions(
                incoming_version,
                incoming_updated_by,
                tombstone["sync_version"],
                tombstone["sync_updated_by"],
            )
            <= 0
        ):
            return _finalize_remote_result(
                conn,
                status="skipped",
                canonical_row_uuid=canonical_uuid,
                observed_version=incoming_version,
            )
        # New row — INSERT
        placeholders = ", ".join("?" for _ in cols)
        col_str = ", ".join(f'"{c}"' for c in cols)
        vals = [resolved[c] for c in cols]
        conn.execute(
            f'INSERT INTO "{table_name}" ({col_str}) VALUES ({placeholders})',
            vals,
        )
        _delete_tombstone(conn, table_name, canonical_uuid)
        if incoming_uuid != canonical_uuid:
            _delete_tombstone(conn, table_name, incoming_uuid)
        return _finalize_remote_result(
            conn,
            status="applied",
            canonical_row_uuid=canonical_uuid,
            observed_version=incoming_version,
        )

    if existing is not None and operation in ("INSERT", "UPDATE"):
        if (
            _compare_versions(
                incoming_version,
                incoming_updated_by,
                existing["sync_version"],
                existing["sync_updated_by"],
            )
            < 0
        ):
            return _finalize_remote_result(
                conn,
                status="skipped",
                canonical_row_uuid=canonical_uuid,
                observed_version=incoming_version,
            )
        # Existing row — UPDATE
        set_clause = ", ".join(f'"{c}" = ?' for c in cols if c != "uuid")
        vals = [resolved[c] for c in cols if c != "uuid"]
        vals.append(canonical_uuid)
        conn.execute(
            f'UPDATE "{table_name}" SET {set_clause} WHERE uuid = ?',
            vals,
        )
        _delete_tombstone(conn, table_name, canonical_uuid)
        if incoming_uuid != canonical_uuid:
            _delete_tombstone(conn, table_name, incoming_uuid)
        return _finalize_remote_result(
            conn,
            status="applied",
            canonical_row_uuid=canonical_uuid,
            observed_version=incoming_version,
        )

    return RemoteApplyResult("invalid", canonical_uuid, incoming_version)


def _apply_key_pk_change(
    conn: sqlite3.Connection,
    table_name: str,
    row_key: str,
    operation: str,
    payload: dict,
    *,
    peer_device_id: str,
) -> bool:
    return _apply_key_pk_change_result(
        conn,
        table_name,
        row_key,
        operation,
        payload,
        peer_device_id=peer_device_id,
    ).applied


def _apply_key_pk_change_result(
    conn: sqlite3.Connection,
    table_name: str,
    row_key: str,
    operation: str,
    payload: dict,
    *,
    peer_device_id: str,
) -> RemoteApplyResult:
    """Apply change for a table with a text PK (e.g. settings)."""
    try:
        _validate_table(table_name)
    except ValueError:
        log.warning("Rejecting change for unknown table %r", table_name)
        return RemoteApplyResult("invalid", row_key, 0)

    # Validate column names against the actual schema
    valid_cols = _valid_columns(conn, table_name)
    payload_cols = {k for k in payload if not k.startswith("_")}
    bad_cols = payload_cols - valid_cols
    if bad_cols:
        log.warning("Rejecting change: invalid columns %s for table %r", bad_cols, table_name)
        return RemoteApplyResult("invalid", row_key, 0)

    incoming_version = int(payload.get("sync_version") or 0)
    incoming_updated_by = str(payload.get("sync_updated_by") or "")
    tombstone = _get_tombstone(conn, table_name, row_key)
    existing = conn.execute(f'SELECT * FROM "{table_name}" WHERE key = ?', (row_key,)).fetchone()

    if operation == "DELETE":
        if (
            existing is not None
            and _compare_versions(
                incoming_version,
                incoming_updated_by,
                existing["sync_version"],
                existing["sync_updated_by"],
            )
            < 0
        ):
            return _finalize_remote_result(
                conn,
                status="skipped",
                canonical_row_uuid=row_key,
                observed_version=incoming_version,
            )
        if (
            tombstone is not None
            and _compare_versions(
                incoming_version,
                incoming_updated_by,
                tombstone["sync_version"],
                tombstone["sync_updated_by"],
            )
            <= 0
        ):
            return _finalize_remote_result(
                conn,
                status="skipped",
                canonical_row_uuid=row_key,
                observed_version=incoming_version,
            )
        conn.execute(f'DELETE FROM "{table_name}" WHERE key = ?', (row_key,))
        _upsert_tombstone(conn, table_name, row_key, incoming_version, incoming_updated_by, payload)
        return _finalize_remote_result(
            conn,
            status="applied",
            canonical_row_uuid=row_key,
            observed_version=incoming_version,
        )

    if operation in ("INSERT", "UPDATE"):
        natural_key_match = _find_natural_key_match(conn, table_name, payload)
        if natural_key_match is not None:
            natural_key, _ = natural_key_match
            _record_conflict(
                conn,
                peer_device_id,
                table_name,
                row_key,
                "natural_key_conflict",
                natural_key,
                payload,
            )
            return _finalize_remote_result(
                conn,
                status="conflict",
                canonical_row_uuid=row_key,
                observed_version=incoming_version,
            )
        if (
            existing is None
            and tombstone is not None
            and _compare_versions(
                incoming_version,
                incoming_updated_by,
                tombstone["sync_version"],
                tombstone["sync_updated_by"],
            )
            <= 0
        ):
            return _finalize_remote_result(
                conn,
                status="skipped",
                canonical_row_uuid=row_key,
                observed_version=incoming_version,
            )
        if (
            existing is not None
            and _compare_versions(
                incoming_version,
                incoming_updated_by,
                existing["sync_version"],
                existing["sync_updated_by"],
            )
            < 0
        ):
            return _finalize_remote_result(
                conn,
                status="skipped",
                canonical_row_uuid=row_key,
                observed_version=incoming_version,
            )
        cols = list(payload_cols)
        _validate_columns(conn, table_name, cols)
        placeholders = ", ".join("?" for _ in cols)
        col_str = ", ".join(f'"{c}"' for c in cols)
        vals = [payload[c] for c in cols]

        conn.execute(
            f'INSERT OR REPLACE INTO "{table_name}" ({col_str}) VALUES ({placeholders})',
            vals,
        )
        _delete_tombstone(conn, table_name, row_key)
        return _finalize_remote_result(
            conn,
            status="applied",
            canonical_row_uuid=row_key,
            observed_version=incoming_version,
        )

    return RemoteApplyResult("invalid", row_key, incoming_version)


def get_full_table_state(
    conn: sqlite3.Connection,
    table_name: str,
) -> list[dict]:
    """Dump every row from *table_name* as a list of dicts.

    Used for initial full-state sync when no prior CDC history exists.
    """
    _validate_table(table_name)
    rows = conn.execute(f'SELECT * FROM "{table_name}"').fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return {k: row[k] for k in row.keys()}  # noqa: SIM118 — sqlite3.Row requires .keys() to iterate column names
