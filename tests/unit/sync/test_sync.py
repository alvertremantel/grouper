"""test_sync.py -- Tests for the grouper_server.sync package.

Covers protocol encoding/decoding, schema invariants, validation
functions, and device identity management.  No network access required.
"""

from __future__ import annotations

import json
import sqlite3
from typing import cast

import pytest

# ===========================================================================
# 1. Protocol — encode / decode round-trips
# ===========================================================================


class TestProtocolHello:
    def test_encode_hello_produces_bytes(self):
        from grouper_server.sync.protocol import Hello, encode

        msg = Hello(device_id="abc123", device_name="My PC", protocol_version=1)
        raw = encode(msg)
        assert isinstance(raw, bytes)
        assert raw.endswith(b"\n")

    def test_decode_hello_restores_fields(self):
        from grouper_server.sync.protocol import Hello, decode, encode

        original = Hello(device_id="abc123", device_name="My PC", protocol_version=1)
        raw = encode(original)
        restored = decode(raw)
        assert isinstance(restored, Hello)
        assert restored.device_id == "abc123"
        assert restored.device_name == "My PC"
        assert restored.protocol_version == 1

    def test_hello_round_trip(self):
        from grouper_server.sync.protocol import Hello, decode, encode

        original = Hello(device_id="dev-42", device_name="Laptop", protocol_version=2)
        restored = decode(encode(original))
        assert isinstance(restored, Hello)
        assert restored.device_id == original.device_id
        assert restored.device_name == original.device_name
        assert restored.protocol_version == original.protocol_version


class TestProtocolSyncResponse:
    def test_encode_sync_response_with_changes(self):
        from grouper_server.sync.protocol import SyncResponse, encode

        changes = [
            {"id": 1, "table_name": "tasks", "operation": "INSERT", "payload": {"title": "Do it"}},
            {"id": 2, "table_name": "tasks", "operation": "UPDATE", "payload": {"title": "Done"}},
        ]
        msg = SyncResponse(changes=changes)
        raw = encode(msg)
        assert isinstance(raw, bytes)
        parsed = json.loads(raw)
        assert parsed["type"] == "sync_response"
        assert len(parsed["changes"]) == 2

    def test_decode_sync_response_preserves_changes(self):
        from grouper_server.sync.protocol import SyncResponse, decode, encode

        changes = [{"id": 10, "table_name": "boards", "operation": "DELETE"}]
        original = SyncResponse(changes=changes)
        restored = decode(encode(original))
        assert isinstance(restored, SyncResponse)
        assert len(restored.changes) == 1
        assert restored.changes[0]["id"] == 10

    def test_empty_sync_response_round_trip(self):
        from grouper_server.sync.protocol import SyncResponse, decode, encode

        original = SyncResponse(changes=[])
        restored = decode(encode(original))
        assert isinstance(restored, SyncResponse)
        assert restored.changes == []

    def test_paged_sync_response_round_trip(self):
        from grouper_server.sync.protocol import SyncResponse, decode, encode

        changes = [{"id": 1, "table_name": "tasks", "operation": "INSERT"}]
        original = SyncResponse(
            changes=changes,
            has_more=True,
            next_since_id=100,
        )
        restored = decode(encode(original))
        assert isinstance(restored, SyncResponse)
        assert restored.has_more is True
        assert restored.next_since_id == 100
        assert len(restored.changes) == 1

    def test_paged_sync_response_final_page(self):
        from grouper_server.sync.protocol import SyncResponse, decode, encode

        original = SyncResponse(
            changes=[{"id": 999, "table_name": "tasks", "operation": "UPDATE"}],
            has_more=False,
            next_since_id=999,
        )
        restored = decode(encode(original))
        assert isinstance(restored, SyncResponse)
        assert restored.has_more is False
        assert restored.next_since_id == 999

    def test_decode_backward_compat_missing_paging_fields(self):
        from grouper_server.sync.protocol import SyncResponse, decode

        raw = b'{"type":"sync_response","changes":[{"id":1}]}'
        restored = decode(raw)
        assert isinstance(restored, SyncResponse)
        assert restored.has_more is False
        assert restored.next_since_id == 0


class TestProtocolSyncRequest:
    def test_sync_request_round_trip(self):
        from grouper_server.sync.protocol import SyncRequest, decode, encode

        original = SyncRequest(since_id=42)
        restored = decode(encode(original))
        assert isinstance(restored, SyncRequest)
        assert restored.since_id == 42


class TestProtocolSyncAck:
    def test_sync_ack_round_trip(self):
        from grouper_server.sync.protocol import SyncAck, decode, encode

        original = SyncAck(last_applied_id=99)
        restored = decode(encode(original))
        assert isinstance(restored, SyncAck)
        assert restored.last_applied_id == 99


class TestProtocolError:
    def test_error_round_trip(self):
        from grouper_server.sync.protocol import Error, decode, encode

        original = Error(message="something went wrong")
        restored = decode(encode(original))
        assert isinstance(restored, Error)
        assert restored.message == "something went wrong"


class TestProtocolDecodeErrors:
    def test_invalid_json_raises_valueerror(self):
        from grouper_server.sync.protocol import decode

        with pytest.raises(ValueError, match="Malformed NDJSON"):
            decode(b"not valid json\n")

    def test_unknown_type_raises(self):
        from grouper_server.sync.protocol import decode

        with pytest.raises(ValueError, match="Unknown message type"):
            decode(b'{"type": "bogus"}\n')

    def test_missing_type_raises(self):
        from grouper_server.sync.protocol import decode

        with pytest.raises(ValueError, match="Unknown message type"):
            decode(b'{"foo": "bar"}\n')


# ===========================================================================
# 2. Schema — structural invariants
# ===========================================================================


class TestSchemaInvariants:
    def test_synced_tables_non_empty(self):
        from grouper_server.sync.schema import SYNCED_TABLES

        assert len(SYNCED_TABLES) > 0

    def test_insert_order_covers_all_synced_tables(self):
        from grouper_server.sync.schema import INSERT_ORDER, SYNCED_TABLES

        assert set(INSERT_ORDER) == set(SYNCED_TABLES)

    def test_delete_order_covers_all_synced_tables(self):
        from grouper_server.sync.schema import DELETE_ORDER, SYNCED_TABLES

        assert set(DELETE_ORDER) == set(SYNCED_TABLES)

    def test_delete_order_is_reverse_of_insert_order(self):
        from grouper_server.sync.schema import DELETE_ORDER, INSERT_ORDER

        assert list(reversed(INSERT_ORDER)) == DELETE_ORDER

    def test_fk_map_keys_in_synced_tables(self):
        from grouper_server.sync.schema import FK_MAP, SYNCED_TABLES

        synced = set(SYNCED_TABLES)
        for table in FK_MAP:
            assert table in synced, f"FK_MAP key {table!r} not in SYNCED_TABLES"

    def test_fk_map_values_reference_synced_tables(self):
        from grouper_server.sync.schema import FK_MAP, SYNCED_TABLES

        synced = set(SYNCED_TABLES)
        for table, fk_defs in FK_MAP.items():
            for fk_col, ref_table in fk_defs.items():
                assert ref_table in synced, (
                    f"FK_MAP[{table!r}][{fk_col!r}] references {ref_table!r} "
                    f"which is not in SYNCED_TABLES"
                )

    def test_insert_order_has_no_duplicates(self):
        from grouper_server.sync.schema import INSERT_ORDER

        assert len(INSERT_ORDER) == len(set(INSERT_ORDER))

    def test_composite_pk_tables_in_synced(self):
        from grouper_server.sync.schema import COMPOSITE_PK_TABLES, SYNCED_TABLES

        synced = set(SYNCED_TABLES)
        for table in COMPOSITE_PK_TABLES:
            assert table in synced

    def test_key_pk_tables_in_synced(self):
        from grouper_server.sync.schema import KEY_PK_TABLES, SYNCED_TABLES

        synced = set(SYNCED_TABLES)
        for table in KEY_PK_TABLES:
            assert table in synced


# ===========================================================================
# 3. Validation — _validate_table and _validate_columns
# ===========================================================================


class TestValidateTable:
    def test_valid_table_returns_name(self):
        from grouper_server.sync.changelog import _validate_table

        assert _validate_table("activities") == "activities"

    def test_valid_table_settings(self):
        from grouper_server.sync.changelog import _validate_table

        assert _validate_table("settings") == "settings"

    def test_invalid_table_raises(self):
        from grouper_server.sync.changelog import _validate_table

        with pytest.raises(ValueError, match="Invalid sync table"):
            _validate_table("evil_table")

    def test_sql_injection_attempt_raises(self):
        from grouper_server.sync.changelog import _validate_table

        with pytest.raises(ValueError, match="Invalid sync table"):
            _validate_table("'; DROP TABLE --")

    def test_empty_string_raises(self):
        from grouper_server.sync.changelog import _validate_table

        with pytest.raises(ValueError, match="Invalid sync table"):
            _validate_table("")

    def test_every_synced_table_passes(self):
        from grouper_server.sync.changelog import _validate_table
        from grouper_server.sync.schema import SYNCED_TABLES

        for table in SYNCED_TABLES:
            assert _validate_table(table) == table


class TestValidateColumns:
    def test_valid_columns_pass(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import _validate_columns

        with get_connection() as conn:
            result = _validate_columns(conn, "activities", ["name"])
            assert result == ["name"]

    def test_invalid_column_raises(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import _validate_columns

        with get_connection() as conn, pytest.raises(ValueError, match="Invalid columns"):
            _validate_columns(conn, "activities", ["nonexistent_col"])

    def test_mixed_valid_invalid_raises(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import _validate_columns

        with get_connection() as conn, pytest.raises(ValueError, match="Invalid columns"):
            _validate_columns(conn, "activities", ["name", "fake_col"])


# ===========================================================================
# 4. Device — identity management
# ===========================================================================


class TestDeviceId:
    def test_get_or_create_returns_nonempty_string(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            device_id = get_or_create_device_id(conn)
            assert isinstance(device_id, str)
            assert len(device_id) > 0

    def test_get_or_create_is_stable(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            first = get_or_create_device_id(conn)
            second = get_or_create_device_id(conn)
            assert first == second

    def test_device_id_is_hex_uuid(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            device_id = get_or_create_device_id(conn)
            assert len(device_id) == 32
            int(device_id, 16)  # should not raise — valid hex


class TestCdcSuppression:
    def test_suppress_sets_syncing_flag(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.device import get_or_create_device_id, suppress_cdc

        with get_connection() as conn:
            get_or_create_device_id(conn)  # ensure row exists
            suppress_cdc(conn)
            row = conn.execute("SELECT syncing FROM sync_state WHERE id = 1").fetchone()
            assert row["syncing"] == 1

    def test_unsuppress_clears_syncing_flag(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.device import get_or_create_device_id, suppress_cdc, unsuppress_cdc

        with get_connection() as conn:
            get_or_create_device_id(conn)
            suppress_cdc(conn)
            unsuppress_cdc(conn)
            row = conn.execute("SELECT syncing FROM sync_state WHERE id = 1").fetchone()
            assert row["syncing"] == 0


class TestBootstrapAndApplyTransactions:
    def test_apply_changes_auto_commit_false_leaves_changes_uncommitted_until_finalize(self):
        from desktop.database.connection import get_connection, get_database_path
        from grouper_server.sync.changelog import ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id
        from grouper_server.sync.sync_ops import apply_changes, finish_apply_changes, set_peer_hwm

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)

            apply_result = apply_changes(
                conn,
                [
                    {
                        "id": 7,
                        "table_name": "activities",
                        "row_uuid": "remote-activity-uuid",
                        "operation": "INSERT",
                        "payload": {
                            "name": "Remote Activity",
                            "uuid": "remote-activity-uuid",
                            "sync_version": 3,
                            "sync_updated_by": "peer-b",
                        },
                    }
                ],
                "peer-b",
                auto_commit=False,
            )

            assert apply_result.applied_count == 1

            observer = sqlite3.connect(get_database_path())
            observer.row_factory = sqlite3.Row
            try:
                row = observer.execute(
                    "SELECT 1 FROM activities WHERE uuid = ?",
                    ("remote-activity-uuid",),
                ).fetchone()
                assert row is None
                peer = observer.execute(
                    "SELECT last_changelog_id FROM sync_peers WHERE peer_device_id = ?",
                    ("peer-b",),
                ).fetchone()
                assert peer is None
            finally:
                observer.close()

            set_peer_hwm(conn, "peer-b", "Peer B", apply_result.last_durable_change_id)
            finish_apply_changes(conn)

            observer = sqlite3.connect(get_database_path())
            observer.row_factory = sqlite3.Row
            try:
                row = observer.execute(
                    "SELECT name FROM activities WHERE uuid = ?",
                    ("remote-activity-uuid",),
                ).fetchone()
                assert row is not None
                assert row["name"] == "Remote Activity"
                peer = observer.execute(
                    "SELECT last_changelog_id FROM sync_peers WHERE peer_device_id = ?",
                    ("peer-b",),
                ).fetchone()
                assert peer is not None
                assert peer["last_changelog_id"] == 7
            finally:
                observer.close()

    def test_bootstrap_marks_complete_in_final_table_commit(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.bootstrap import snapshot_for_bootstrap
        from grouper_server.sync.device import get_or_create_device_id
        from grouper_server.sync.schema import INSERT_ORDER, SYNCED_TABLES

        class _CrashAfterFinalBootstrapCommit:
            def __init__(self, conn, *, fail_on_commit: int) -> None:
                self._conn = conn
                self._fail_on_commit = fail_on_commit
                self._commit_count = 0

            def commit(self) -> None:
                self._commit_count += 1
                self._conn.commit()
                if self._commit_count == self._fail_on_commit:
                    raise RuntimeError("simulated crash after commit")

            def __getattr__(self, name: str):
                return getattr(self._conn, name)

        pending_tables = [table for table in INSERT_ORDER if table in SYNCED_TABLES]
        fail_on_commit = 1 + len(pending_tables)

        with get_connection() as conn:
            device_id = get_or_create_device_id(conn)
            conn.execute(
                "INSERT INTO activities (name, uuid) VALUES (?, ?)", ("Bootstrap Me", "boot-uuid")
            )
            conn.commit()

            wrapped = _CrashAfterFinalBootstrapCommit(conn, fail_on_commit=fail_on_commit)
            with pytest.raises(RuntimeError, match="simulated crash after commit"):
                snapshot_for_bootstrap(cast(sqlite3.Connection, wrapped), device_id)

        with get_connection() as conn:
            state = conn.execute(
                "SELECT bootstrap_complete, bootstrap_watermark FROM sync_state WHERE id = 1"
            ).fetchone()
            assert state is not None
            assert state["bootstrap_complete"] == 1
            assert state["bootstrap_watermark"] is None

            before = conn.execute("SELECT COUNT(*) FROM sync_changelog").fetchone()[0]
            snapshot_for_bootstrap(conn, device_id)
            after = conn.execute("SELECT COUNT(*) FROM sync_changelog").fetchone()[0]

            assert before == after


class TestDeviceName:
    def test_get_device_name_returns_string(self):
        from grouper_server.sync.device import get_device_name

        name = get_device_name()
        assert isinstance(name, str)
        assert len(name) > 0


# ===========================================================================
# 5. CDC triggers — ensure_triggers installs working triggers
# ===========================================================================


class TestCdcTriggerInsert:
    def test_insert_creates_changelog_entry(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute(
                "INSERT INTO activities (name) VALUES (?)",
                ("trigger_insert_test",),
            )
            conn.commit()
            rows = conn.execute(
                "SELECT * FROM sync_changelog WHERE table_name = 'activities' "
                "AND operation IN ('INSERT', 'UPDATE')"
            ).fetchall()
            payloads = [r["payload"] for r in rows]
            assert any("trigger_insert_test" in p for p in payloads)


class TestCdcTriggerUpdate:
    def test_update_creates_changelog_entry(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute(
                "INSERT INTO activities (name) VALUES (?)",
                ("trigger_update_orig",),
            )
            conn.commit()
            # Clear changelog so we only see the UPDATE
            conn.execute("DELETE FROM sync_changelog")
            conn.commit()
            conn.execute(
                "UPDATE activities SET name = ? WHERE name = ?",
                ("trigger_update_new", "trigger_update_orig"),
            )
            conn.commit()
            rows = conn.execute(
                "SELECT * FROM sync_changelog WHERE table_name = 'activities' "
                "AND operation = 'UPDATE'"
            ).fetchall()
            assert len(rows) >= 1
            payloads = [r["payload"] for r in rows]
            assert any("trigger_update_new" in p for p in payloads)


class TestCdcTriggerDelete:
    def test_delete_creates_changelog_entry(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute(
                "INSERT INTO activities (name) VALUES (?)",
                ("trigger_delete_test",),
            )
            conn.commit()
            conn.execute("DELETE FROM sync_changelog")
            conn.commit()
            conn.execute(
                "DELETE FROM activities WHERE name = ?",
                ("trigger_delete_test",),
            )
            conn.commit()
            rows = conn.execute(
                "SELECT * FROM sync_changelog WHERE table_name = 'activities' "
                "AND operation = 'DELETE'"
            ).fetchall()
            assert len(rows) == 1
            assert "trigger_delete_test" in rows[0]["payload"]


class TestCdcSuppressTriggers:
    def test_suppressed_changes_do_not_create_changelog(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id, suppress_cdc

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute("DELETE FROM sync_changelog")
            conn.commit()
            suppress_cdc(conn)
            conn.commit()
            conn.execute(
                "INSERT INTO activities (name) VALUES (?)",
                ("suppressed_test",),
            )
            conn.commit()
            rows = conn.execute("SELECT * FROM sync_changelog").fetchall()
            assert len(rows) == 0

    def test_unsuppress_restores_changelog_recording(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import ensure_triggers
        from grouper_server.sync.device import (
            get_or_create_device_id,
            suppress_cdc,
            unsuppress_cdc,
        )

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            suppress_cdc(conn)
            conn.commit()
            conn.execute(
                "INSERT INTO activities (name) VALUES (?)",
                ("during_suppress",),
            )
            conn.commit()
            conn.execute("DELETE FROM sync_changelog")
            conn.commit()
            unsuppress_cdc(conn)
            conn.commit()
            conn.execute(
                "INSERT INTO activities (name) VALUES (?)",
                ("after_unsuppress",),
            )
            conn.commit()
            rows = conn.execute("SELECT * FROM sync_changelog").fetchall()
            payloads = [r["payload"] for r in rows]
            assert any("after_unsuppress" in p for p in payloads)


# ===========================================================================
# 6. FK resolution — resolve_fks_to_uuids / resolve_uuids_to_fks
# ===========================================================================


def _setup_fk_test_data(conn):
    """Insert boards, projects, activities, and tasks with known UUIDs.

    Returns a dict of {table: {name: (id, uuid)}} for assertions.
    """
    from grouper_server.sync.changelog import ensure_triggers
    from grouper_server.sync.device import get_or_create_device_id

    get_or_create_device_id(conn)
    ensure_triggers(conn)

    conn.execute(
        "INSERT INTO boards (name, uuid) VALUES (?, ?)",
        ("Test Board", "board_uuid_aaa"),
    )
    conn.commit()
    board = conn.execute(
        "SELECT id, uuid FROM boards WHERE uuid = ?", ("board_uuid_aaa",)
    ).fetchone()

    conn.execute(
        "INSERT INTO projects (board_id, name, uuid) VALUES (?, ?, ?)",
        (board["id"], "Test Project", "proj_uuid_bbb"),
    )
    conn.commit()
    project = conn.execute(
        "SELECT id, uuid FROM projects WHERE uuid = ?", ("proj_uuid_bbb",)
    ).fetchone()

    conn.execute(
        "INSERT INTO activities (name, uuid) VALUES (?, ?)",
        ("Test Activity", "act_uuid_ccc"),
    )
    conn.commit()
    activity = conn.execute(
        "SELECT id, uuid FROM activities WHERE uuid = ?", ("act_uuid_ccc",)
    ).fetchone()

    conn.execute(
        "INSERT INTO tasks (project_id, title, uuid) VALUES (?, ?, ?)",
        (project["id"], "Test Task", "task_uuid_ddd"),
    )
    conn.commit()
    task = conn.execute("SELECT id, uuid FROM tasks WHERE uuid = ?", ("task_uuid_ddd",)).fetchone()

    return {
        "board": {"id": board["id"], "uuid": board["uuid"]},
        "project": {"id": project["id"], "uuid": project["uuid"]},
        "activity": {"id": activity["id"], "uuid": activity["uuid"]},
        "task": {"id": task["id"], "uuid": task["uuid"]},
    }


class TestResolveFksToUuids:
    def test_session_activity_name_unchanged(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import resolve_fks_to_uuids

        with get_connection() as conn:
            data = _setup_fk_test_data(conn)
            payload = {
                "id": 1,
                "activity_name": "Test Activity",
                "start_time": "2026-01-01T00:00:00",
                "task_id": data["task"]["id"],
                "uuid": "some_session_uuid",
            }
            result = resolve_fks_to_uuids(conn, "sessions", payload)
            assert result["activity_name"] == "Test Activity"
            assert "activity_name_uuid" not in result

    def test_task_project_id_resolved_to_uuid(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import resolve_fks_to_uuids

        with get_connection() as conn:
            data = _setup_fk_test_data(conn)
            payload = {
                "id": 10,
                "project_id": data["project"]["id"],
                "title": "Test Task",
                "uuid": "task_uuid_ddd",
            }
            result = resolve_fks_to_uuids(conn, "tasks", payload)
            assert "project_id" not in result
            assert result["project_id_uuid"] == "proj_uuid_bbb"

    def test_fk_target_missing_sets_uuid_to_none(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import resolve_fks_to_uuids

        with get_connection() as conn:
            _setup_fk_test_data(conn)
            payload = {
                "id": 99,
                "project_id": 99999,
                "title": "Orphan Task",
                "uuid": "orphan_uuid",
            }
            result = resolve_fks_to_uuids(conn, "tasks", payload)
            assert "project_id" not in result
            assert result["project_id_uuid"] is None

    def test_empty_payload_returns_empty(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import resolve_fks_to_uuids

        with get_connection() as conn:
            _setup_fk_test_data(conn)
            result = resolve_fks_to_uuids(conn, "tasks", {})
            assert result["project_id_uuid"] is None
            assert "project_id" not in result


class TestResolveUuidsToFks:
    def test_project_id_uuid_mapped_to_integer(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import resolve_uuids_to_fks

        with get_connection() as conn:
            data = _setup_fk_test_data(conn)
            payload = {
                "id": 10,
                "project_id_uuid": "proj_uuid_bbb",
                "title": "Test Task",
                "uuid": "task_uuid_ddd",
            }
            result = resolve_uuids_to_fks(conn, "tasks", payload)
            assert "project_id_uuid" not in result
            assert result["project_id"] == data["project"]["id"]

    def test_nonexistent_uuid_raises_missing_parent(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import MissingParentError, resolve_uuids_to_fks

        with get_connection() as conn:
            _setup_fk_test_data(conn)
            payload = {
                "id": 10,
                "project_id_uuid": "nonexistent_uuid_xyz",
                "title": "Orphan Task",
                "uuid": "orphan_uuid",
            }
            with pytest.raises(MissingParentError):
                resolve_uuids_to_fks(conn, "tasks", payload)

    def test_no_fk_fields_returns_unchanged(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import resolve_uuids_to_fks

        with get_connection() as conn:
            _setup_fk_test_data(conn)
            payload = {
                "id": 1,
                "name": "Test Activity",
                "uuid": "act_uuid_ccc",
            }
            result = resolve_uuids_to_fks(conn, "activities", payload)
            assert result == payload


class TestFkResolutionRoundTrip:
    def test_fks_to_uuids_to_fks_preserves_values(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import resolve_fks_to_uuids, resolve_uuids_to_fks

        with get_connection() as conn:
            data = _setup_fk_test_data(conn)
            original_payload = {
                "id": 10,
                "project_id": data["project"]["id"],
                "title": "Round Trip Task",
                "uuid": "roundtrip_uuid",
            }
            with_uuids = resolve_fks_to_uuids(conn, "tasks", original_payload)
            assert "project_id" not in with_uuids
            assert "project_id_uuid" in with_uuids
            restored = resolve_uuids_to_fks(conn, "tasks", with_uuids)
            assert "project_id_uuid" not in restored
            assert restored["project_id"] == original_payload["project_id"]
            assert restored["title"] == original_payload["title"]
            assert restored["uuid"] == original_payload["uuid"]


# ===========================================================================
# 7. SQL injection prevention — end-to-end tests
# ===========================================================================


class TestApplyRemoteChangeTableInjection:
    def test_drop_table_injection_rejected(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import apply_remote_change, ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute(
                "INSERT INTO sessions (activity_name, start_time, uuid) VALUES (?, ?, ?)",
                ("sentinel", "2026-01-01T00:00:00", "sentinel_uuid_001"),
            )
            conn.commit()
            result = apply_remote_change(
                conn,
                "activities; DROP TABLE sessions; --",
                "injected_uuid",
                "INSERT",
                {"name": "evil"},
            )
            assert result is False
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM sessions WHERE uuid = ?",
                ("sentinel_uuid_001",),
            ).fetchone()
            assert row["cnt"] == 1

    def test_or_injection_rejected(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import apply_remote_change, ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute(
                "INSERT INTO sessions (activity_name, start_time, uuid) VALUES (?, ?, ?)",
                ("sentinel", "2026-01-01T00:00:00", "sentinel_uuid_002"),
            )
            conn.commit()
            result = apply_remote_change(
                conn,
                "' OR '1'='1",
                "injected_uuid",
                "INSERT",
                {"name": "evil"},
            )
            assert result is False
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM sessions WHERE uuid = ?",
                ("sentinel_uuid_002",),
            ).fetchone()
            assert row["cnt"] == 1

    def test_database_intact_after_injection_attempts(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import apply_remote_change, ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute(
                "INSERT INTO activities (name, uuid) VALUES (?, ?)",
                ("preserve_me", "preserve_uuid_001"),
            )
            conn.commit()
            injections = [
                "activities; DROP TABLE sessions; --",
                "' OR '1'='1",
                "activities UNION SELECT * FROM sessions --",
                'activities"; DROP TABLE activities; --',
            ]
            for malicious_name in injections:
                apply_remote_change(
                    conn,
                    malicious_name,
                    "bad_uuid",
                    "INSERT",
                    {"name": "x"},
                )
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "sessions" in tables
            assert "activities" in tables
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM activities WHERE uuid = ?",
                ("preserve_uuid_001",),
            ).fetchone()
            assert row["cnt"] == 1


class TestGetFullTableStateInjection:
    def test_invalid_table_raises_valueerror(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import get_full_table_state

        with get_connection() as conn, pytest.raises(ValueError, match="Invalid sync table"):
            get_full_table_state(conn, "activities; DROP TABLE sessions; --")

    def test_or_injection_raises_valueerror(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import get_full_table_state

        with get_connection() as conn, pytest.raises(ValueError, match="Invalid sync table"):
            get_full_table_state(conn, "' OR '1'='1")


class TestColumnInjectionPrevention:
    def test_malicious_column_name_rejected(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import apply_remote_change, ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            result = apply_remote_change(
                conn,
                "activities",
                "col_inject_uuid",
                "INSERT",
                {
                    "name": "legit",
                    "uuid": "col_inject_uuid",
                    "evil_col; DROP TABLE sessions": "payload",
                },
            )
            assert result is False
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM activities WHERE uuid = ?",
                ("col_inject_uuid",),
            ).fetchone()
            assert row["cnt"] == 0

    def test_column_with_sql_comment_rejected(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import apply_remote_change, ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            result = apply_remote_change(
                conn,
                "activities",
                "col_comment_uuid",
                "INSERT",
                {
                    "name": "legit",
                    "uuid": "col_comment_uuid",
                    "name --": "injected",
                },
            )
            assert result is False
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM activities WHERE uuid = ?",
                ("col_comment_uuid",),
            ).fetchone()
            assert row["cnt"] == 0


class TestValidOperationsStillWork:
    def test_apply_remote_insert_activities(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import apply_remote_change, ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            result = apply_remote_change(
                conn,
                "activities",
                "valid_insert_uuid",
                "INSERT",
                {"name": "Valid Activity", "uuid": "valid_insert_uuid"},
            )
            assert result is True
            conn.commit()
            row = conn.execute(
                "SELECT name FROM activities WHERE uuid = ?",
                ("valid_insert_uuid",),
            ).fetchone()
            assert row is not None
            assert row["name"] == "Valid Activity"

    def test_get_full_table_state_activities(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import (
            apply_remote_change,
            ensure_triggers,
            get_full_table_state,
        )
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            apply_remote_change(
                conn,
                "activities",
                "state_check_uuid",
                "INSERT",
                {"name": "State Check", "uuid": "state_check_uuid"},
            )
            conn.commit()
            rows = get_full_table_state(conn, "activities")
            assert isinstance(rows, list)
            uuids = [r["uuid"] for r in rows]
            assert "state_check_uuid" in uuids


# ===========================================================================
# 8. Paged changelog queries
# ===========================================================================


class TestGetChangesSincePaged:
    def test_returns_page_within_limit(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import ensure_triggers, get_changes_since_paged
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute("DELETE FROM sync_changelog")
            conn.commit()
            for i in range(5):
                conn.execute(
                    "INSERT INTO activities (name, uuid) VALUES (?, ?)",
                    (f"paged_{i}", f"paged_uuid_{i}"),
                )
                conn.commit()

            changes, has_more, next_id = get_changes_since_paged(conn, since_id=0, page_size=3)
            assert len(changes) == 3
            assert has_more is True
            assert next_id == changes[-1]["id"]

    def test_returns_all_when_within_page(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import ensure_triggers, get_changes_since_paged
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute("DELETE FROM sync_changelog")
            conn.commit()
            conn.execute(
                "INSERT INTO activities (name, uuid) VALUES (?, ?)",
                ("small_page", "small_uuid"),
            )
            conn.commit()

            changes, has_more, _next_id = get_changes_since_paged(conn, since_id=0, page_size=100)
            assert len(changes) >= 1
            assert has_more is False

    def test_empty_result(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import ensure_triggers, get_changes_since_paged
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute("DELETE FROM sync_changelog")
            conn.commit()

            changes, has_more, next_id = get_changes_since_paged(conn, since_id=999999)
            assert changes == []
            assert has_more is False
            assert next_id == 999999

    def test_second_page_picks_up_after_first(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import ensure_triggers, get_changes_since_paged
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute("DELETE FROM sync_changelog")
            conn.commit()
            for i in range(10):
                conn.execute(
                    "INSERT INTO activities (name, uuid) VALUES (?, ?)",
                    (f"multi_{i}", f"multi_uuid_{i}"),
                )
                conn.commit()

            page1, has_more1, next1 = get_changes_since_paged(conn, since_id=0, page_size=4)
            assert len(page1) == 4
            assert has_more1 is True

            page2, has_more2, next2 = get_changes_since_paged(conn, since_id=next1, page_size=4)
            assert len(page2) == 4
            assert has_more2 is True

            page3, has_more3, _ = get_changes_since_paged(conn, since_id=next2, page_size=4)
            assert has_more3 is False

            all_ids = [c["id"] for c in page1 + page2 + page3]
            assert len(all_ids) == len(set(all_ids)), "No duplicate IDs across pages"

    def test_byte_budget_cap(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import ensure_triggers, get_changes_since_paged
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute("DELETE FROM sync_changelog")
            conn.commit()
            for i in range(50):
                conn.execute(
                    "INSERT INTO activities (name, uuid) VALUES (?, ?)",
                    (f"budget_{i}", f"budget_uuid_{i}"),
                )
                conn.commit()

            changes, _has_more, _next_id = get_changes_since_paged(
                conn,
                since_id=0,
                page_size=100,
            )
            import json as _json

            total_bytes = sum(len(_json.dumps(c, separators=(",", ":")).encode()) for c in changes)
            assert total_bytes <= 8 * 1024 * 1024

    def test_device_id_filter(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import ensure_triggers, get_changes_since_paged
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            device_id = get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute("DELETE FROM sync_changelog")
            conn.commit()
            conn.execute(
                "INSERT INTO activities (name, uuid) VALUES (?, ?)",
                ("filtered", "filtered_uuid"),
            )
            conn.commit()

            changes, _, _ = get_changes_since_paged(
                conn,
                since_id=0,
                device_id=device_id,
                page_size=100,
            )
            assert len(changes) >= 1
            for c in changes:
                assert c["device_id"] == device_id


# ===========================================================================
# 9. Protocol version
# ===========================================================================


class TestProtocolVersion:
    def test_hello_default_version_is_2(self):
        from grouper_server.sync.protocol import Hello

        msg = Hello()
        assert msg.protocol_version == 2


class TestConflictConvergence:
    def test_newer_same_uuid_update_wins(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import apply_remote_change, ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute(
                "INSERT INTO activities (name, uuid) VALUES (?, ?)",
                ("Local Activity", "conflict_uuid_1"),
            )
            conn.commit()

            local = conn.execute(
                "SELECT sync_version, sync_updated_by FROM activities WHERE uuid = ?",
                ("conflict_uuid_1",),
            ).fetchone()
            assert local is not None

            applied = apply_remote_change(
                conn,
                "activities",
                "conflict_uuid_1",
                "UPDATE",
                {
                    "name": "Remote Winner",
                    "uuid": "conflict_uuid_1",
                    "sync_version": local["sync_version"] + 1,
                    "sync_updated_by": "peer-b",
                },
                peer_device_id="peer-b",
            )

            assert applied is True
            row = conn.execute(
                "SELECT name, sync_version, sync_updated_by FROM activities WHERE uuid = ?",
                ("conflict_uuid_1",),
            ).fetchone()
            assert row["name"] == "Remote Winner"
            assert row["sync_version"] == local["sync_version"] + 1
            assert row["sync_updated_by"] == "peer-b"

    def test_newer_tombstone_blocks_stale_resurrection(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import apply_remote_change, ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute(
                "INSERT INTO activities (name, uuid) VALUES (?, ?)",
                ("Delete Me", "conflict_uuid_2"),
            )
            conn.commit()

            deleted = apply_remote_change(
                conn,
                "activities",
                "conflict_uuid_2",
                "DELETE",
                {
                    "name": "Delete Me",
                    "uuid": "conflict_uuid_2",
                    "sync_version": 5,
                    "sync_updated_by": "peer-b",
                },
                peer_device_id="peer-b",
            )
            stale_update = apply_remote_change(
                conn,
                "activities",
                "conflict_uuid_2",
                "UPDATE",
                {
                    "name": "Too Old",
                    "uuid": "conflict_uuid_2",
                    "sync_version": 4,
                    "sync_updated_by": "peer-a",
                },
                peer_device_id="peer-a",
            )

            assert deleted is True
            assert stale_update is False
            assert (
                conn.execute(
                    "SELECT 1 FROM activities WHERE uuid = ?",
                    ("conflict_uuid_2",),
                ).fetchone()
                is None
            )
            tombstone = conn.execute(
                "SELECT sync_version, sync_updated_by FROM sync_tombstones WHERE table_name = 'activities' AND row_uuid = ?",
                ("conflict_uuid_2",),
            ).fetchone()
            assert tombstone is not None
            assert tombstone["sync_version"] == 5
            assert tombstone["sync_updated_by"] == "peer-b"

    def test_duplicate_tag_merges_and_aliases_future_references(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import (
            apply_remote_change,
            ensure_triggers,
            resolve_uuids_to_fks,
        )
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            data = _setup_fk_test_data(conn)
            conn.execute(
                "INSERT INTO tags (name, uuid) VALUES (?, ?)",
                ("Urgent", "local_tag_uuid"),
            )
            conn.commit()

            merged = apply_remote_change(
                conn,
                "tags",
                "remote_tag_uuid",
                "INSERT",
                {
                    "name": "urgent",
                    "uuid": "remote_tag_uuid",
                    "sync_version": 8,
                    "sync_updated_by": "peer-b",
                },
                peer_device_id="peer-b",
            )
            resolved = resolve_uuids_to_fks(
                conn,
                "project_tags",
                {
                    "project_id_uuid": data["project"]["uuid"],
                    "tag_id_uuid": "remote_tag_uuid",
                    "uuid": "project_tag_uuid_1",
                },
            )

            assert merged is True
            alias = conn.execute(
                "SELECT target_uuid FROM sync_uuid_aliases WHERE table_name = 'tags' AND source_uuid = ?",
                ("remote_tag_uuid",),
            ).fetchone()
            assert alias is not None
            assert alias["target_uuid"] == "local_tag_uuid"
            tag_id = conn.execute(
                "SELECT id FROM tags WHERE uuid = ?",
                ("local_tag_uuid",),
            ).fetchone()["id"]
            assert resolved["project_id"] == data["project"]["id"]
            assert resolved["tag_id"] == tag_id

    def test_duplicate_project_records_conflict_without_abort(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id
        from grouper_server.sync.sync_ops import apply_changes

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            data = _setup_fk_test_data(conn)

            applied = apply_changes(
                conn,
                [
                    {
                        "id": 1,
                        "table_name": "projects",
                        "row_uuid": "remote_project_uuid",
                        "operation": "INSERT",
                        "payload": {
                            "board_id_uuid": data["board"]["uuid"],
                            "name": "Test Project",
                            "uuid": "remote_project_uuid",
                            "sync_version": 9,
                            "sync_updated_by": "peer-b",
                        },
                    },
                    {
                        "id": 2,
                        "table_name": "activities",
                        "row_uuid": "survivor_uuid",
                        "operation": "INSERT",
                        "payload": {
                            "name": "Survivor",
                            "uuid": "survivor_uuid",
                            "sync_version": 10,
                            "sync_updated_by": "peer-b",
                        },
                    },
                ],
                "peer-b",
            )

            assert applied.applied_count == 1
            conflict = conn.execute(
                "SELECT conflict_type, natural_key FROM sync_conflicts WHERE table_name = 'projects' AND row_uuid = ?",
                ("remote_project_uuid",),
            ).fetchone()
            assert conflict is not None
            assert conflict["conflict_type"] == "natural_key_conflict"
            assert conflict["natural_key"] == "test project"
            survivor = conn.execute(
                "SELECT name FROM activities WHERE uuid = ?",
                ("survivor_uuid",),
            ).fetchone()
            assert survivor is not None
            assert survivor["name"] == "Survivor"

    def test_remote_apply_advances_logical_clock_for_next_local_write(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import apply_remote_change, ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)

            applied = apply_remote_change(
                conn,
                "activities",
                "clock_remote_uuid",
                "INSERT",
                {
                    "name": "Remote Clock",
                    "uuid": "clock_remote_uuid",
                    "sync_version": 50,
                    "sync_updated_by": "peer-b",
                },
                peer_device_id="peer-b",
            )
            assert applied is True

            logical_clock = conn.execute(
                "SELECT logical_clock FROM sync_state WHERE id = 1"
            ).fetchone()["logical_clock"]
            assert logical_clock == 50

            conn.execute(
                "INSERT INTO activities (name, uuid) VALUES (?, ?)",
                ("Local After Remote", "clock_local_uuid"),
            )
            conn.commit()

            row = conn.execute(
                "SELECT sync_version FROM activities WHERE uuid = ?",
                ("clock_local_uuid",),
            ).fetchone()
            assert row is not None
            assert row["sync_version"] > 50

    def test_alias_delete_uses_canonical_tombstone_uuid(self):
        from desktop.database.connection import get_connection
        from grouper_server.sync.changelog import apply_remote_change, ensure_triggers
        from grouper_server.sync.device import get_or_create_device_id

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute(
                "INSERT INTO tags (name, uuid) VALUES (?, ?)",
                ("Urgent", "canonical_tag_uuid"),
            )
            conn.commit()

            merged = apply_remote_change(
                conn,
                "tags",
                "alias_tag_uuid",
                "INSERT",
                {
                    "name": "urgent",
                    "uuid": "alias_tag_uuid",
                    "sync_version": 7,
                    "sync_updated_by": "peer-a",
                },
                peer_device_id="peer-a",
            )
            deleted = apply_remote_change(
                conn,
                "tags",
                "alias_tag_uuid",
                "DELETE",
                {
                    "name": "Urgent",
                    "uuid": "alias_tag_uuid",
                    "sync_version": 8,
                    "sync_updated_by": "peer-a",
                },
                peer_device_id="peer-a",
            )

            assert merged is True
            assert deleted is True
            assert (
                conn.execute(
                    "SELECT 1 FROM tags WHERE uuid = ?",
                    ("canonical_tag_uuid",),
                ).fetchone()
                is None
            )
            assert (
                conn.execute(
                    "SELECT 1 FROM sync_tombstones WHERE table_name = 'tags' AND row_uuid = ?",
                    ("alias_tag_uuid",),
                ).fetchone()
                is None
            )
            tombstone = conn.execute(
                "SELECT sync_version, sync_updated_by FROM sync_tombstones WHERE table_name = 'tags' AND row_uuid = ?",
                ("canonical_tag_uuid",),
            ).fetchone()
            assert tombstone is not None
            assert tombstone["sync_version"] == 8

    def test_oversized_first_row_is_rejected(self, monkeypatch):
        from desktop.database.connection import get_connection
        from grouper_server.sync import changelog as changelog_mod
        from grouper_server.sync.changelog import (
            OversizedChangeError,
            ensure_triggers,
            get_changes_since_paged,
        )
        from grouper_server.sync.device import get_or_create_device_id

        monkeypatch.setattr(changelog_mod, "_BYTE_BUDGET", 256)

        with get_connection() as conn:
            get_or_create_device_id(conn)
            ensure_triggers(conn)
            conn.execute(
                "INSERT INTO activities (name, uuid, description) VALUES (?, ?, ?)",
                ("Oversized", "oversized_uuid", "x" * 2048),
            )
            conn.commit()

            with pytest.raises(OversizedChangeError):
                get_changes_since_paged(conn, since_id=0, page_size=10)
