"""test_migrations.py -- Tests for the file-based migration system.

Tests cover: fresh DB, legacy bootstrap, partial upgrade, backup naming,
backup retention, discovery, and individual migration idempotency.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Override the root conftest's isolated_db: migration tests must NOT call
# init_database() because they test the migration machinery itself.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect Grouper's database to an isolated temp directory.

    Unlike the root conftest's version, this does NOT call init_database()
    because migration tests need to control schema creation themselves.
    """
    data_dir = tmp_path / "grouper_test"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GROUPER_DATA_DIR", str(data_dir))

    import grouper.database.connection as conn_mod

    conn_mod._init_paths()

    return data_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_schema_only() -> None:
    """Run _INITIAL_SCHEMA without migrations (simulates a fresh DB before runner)."""
    import grouper.database.connection as conn_mod

    with conn_mod.get_connection() as conn:
        conn.executescript(conn_mod._INITIAL_SCHEMA)
        conn.commit()


def _set_version(version: int) -> None:
    """Set schema_version directly, bypassing the migration runner."""
    import grouper.database.connection as conn_mod

    with conn_mod.get_connection() as conn:
        conn_mod._set_schema_version(conn.raw_connection, version)
        conn.raw_connection.commit()


def _get_version() -> int:
    import grouper.database.connection as conn_mod

    with conn_mod.get_connection() as conn:
        return conn_mod._get_schema_version(conn.raw_connection)


def _get_migration_rows() -> list[dict]:
    import grouper.database.connection as conn_mod

    with conn_mod.get_connection() as conn:
        try:
            rows = conn.execute(
                "SELECT version, description FROM _migrations ORDER BY version"
            ).fetchall()
            return [{"version": r["version"], "description": r["description"]} for r in rows]
        except sqlite3.OperationalError:
            return []


def _table_exists(name: str) -> bool:
    import grouper.database.connection as conn_mod

    with conn_mod.get_connection() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        return row is not None


def _get_backup_dir() -> Path:
    import grouper.database.connection as conn_mod

    return conn_mod.DATA_DIR / "backups"


# ===========================================================================
# Discovery
# ===========================================================================


class TestDiscovery:
    def test_discovers_all_migrations(self) -> None:
        from grouper.database.migrations import _discover_migrations

        mods = _discover_migrations()
        assert len(mods) == 23
        assert [m.VERSION for m in mods] == list(range(1, 24))

    def test_all_have_required_attributes(self) -> None:
        from grouper.database.migrations import _discover_migrations

        for mod in _discover_migrations():
            assert hasattr(mod, "VERSION")
            assert hasattr(mod, "DESCRIPTION")
            assert hasattr(mod, "upgrade")
            assert callable(mod.upgrade)


# ===========================================================================
# Fresh database
# ===========================================================================


class TestFreshDatabase:
    def test_init_database_sets_version_15(self) -> None:
        import grouper.database.connection as conn_mod

        conn_mod.init_database()
        assert _get_version() == 23

    def test_all_migrations_recorded(self) -> None:
        import grouper.database.connection as conn_mod

        conn_mod.init_database()
        rows = _get_migration_rows()
        assert len(rows) == 23
        assert rows[0]["version"] == 1
        assert rows[22]["version"] == 23

    def test_all_tables_created(self) -> None:
        import grouper.database.connection as conn_mod

        conn_mod.init_database()
        expected = [
            "activities",
            "boards",
            "projects",
            "sessions",
            "pause_events",
            "tasks",
            "tags",
            "project_tags",
            "settings",
            "groups",
            "activity_groups",
            "calendars",
            "events",
            "event_exceptions",
            "task_links",
            "schema_version",
            "_migrations",
        ]
        for table in expected:
            assert _table_exists(table), f"Table {table} should exist"


# ===========================================================================
# Legacy bootstrap (existing v7 DB, no _migrations table)
# ===========================================================================


class TestLegacyBootstrap:
    def test_existing_v7_no_additional_backup(self, tmp_path: Path) -> None:
        import grouper.database.connection as conn_mod

        # Simulate a v7 database without _migrations
        conn_mod.init_database()
        # Drop the _migrations table to simulate legacy
        with conn_mod.get_connection() as conn:
            conn.execute("DROP TABLE IF EXISTS _migrations")
            conn.commit()

        # Count backups before second init
        backup_dir = _get_backup_dir()
        before = (
            len(list(backup_dir.glob("grouper_pre_migration_v*"))) if backup_dir.exists() else 0
        )

        # Re-run init — should bootstrap history, not re-run migrations
        conn_mod.init_database()

        rows = _get_migration_rows()
        assert len(rows) == 23
        # No additional backup should be created (no pending migrations)
        after = len(list(backup_dir.glob("grouper_pre_migration_v*"))) if backup_dir.exists() else 0
        assert after == before

    def test_bootstrap_uses_correct_descriptions(self) -> None:
        import grouper.database.connection as conn_mod

        conn_mod.init_database()
        with conn_mod.get_connection() as conn:
            conn.execute("DROP TABLE IF EXISTS _migrations")
            conn.commit()

        conn_mod.init_database()
        rows = _get_migration_rows()
        assert rows[0]["description"] == "Stamp initial schema version"
        assert rows[1]["description"] == "Add boards table and board_id to projects"


# ===========================================================================
# Partial upgrade
# ===========================================================================


class TestPartialUpgrade:
    def test_v5_to_v7_applies_missing(self) -> None:
        import grouper.database.connection as conn_mod

        # Create a fresh DB at v5
        _init_schema_only()
        with conn_mod.get_connection() as conn:
            raw = conn.raw_connection
            from grouper.database.migrations import (
                _discover_migrations,
                _ensure_migrations_table,
                run_pending_migrations,
            )

            _ensure_migrations_table(raw)
            # Apply v1-v5 manually
            mods = _discover_migrations()
            for m in mods[:5]:
                m.upgrade(raw)
                raw.execute(
                    "INSERT INTO _migrations (version, description) VALUES (?, ?)",
                    (m.VERSION, m.DESCRIPTION),
                )
                conn_mod._set_schema_version(raw, m.VERSION)
                raw.commit()

        assert _get_version() == 5

        # Now run the full runner - should apply v6-v16
        with conn_mod.get_connection() as conn:
            run_pending_migrations(conn.raw_connection)

        assert _get_version() == 23
        rows = _get_migration_rows()
        assert len(rows) == 23

    def test_partial_upgrade_creates_backup(self, tmp_path: Path) -> None:
        import grouper.database.connection as conn_mod

        # Create a DB at v5
        _init_schema_only()
        with conn_mod.get_connection() as conn:
            raw = conn.raw_connection
            from grouper.database.migrations import (
                _discover_migrations,
                _ensure_migrations_table,
                run_pending_migrations,
            )

            _ensure_migrations_table(raw)
            mods = _discover_migrations()
            for m in mods[:5]:
                m.upgrade(raw)
                raw.execute(
                    "INSERT INTO _migrations (version, description) VALUES (?, ?)",
                    (m.VERSION, m.DESCRIPTION),
                )
                conn_mod._set_schema_version(raw, m.VERSION)
                raw.commit()

        # Run the rest — should create backup
        with conn_mod.get_connection() as conn:
            run_pending_migrations(conn.raw_connection)

        backup_dir = _get_backup_dir()
        backups = list(backup_dir.glob("grouper_pre_migration_v5_to_v23_*"))
        assert len(backups) == 1


# ===========================================================================
# Backup naming and retention
# ===========================================================================


class TestBackup:
    def test_backup_filename_pattern(self) -> None:
        import grouper.database.connection as conn_mod
        from grouper.database.migrations import _backup_before_migration

        # Create the DB file first
        conn_mod.init_database()
        _backup_before_migration(5, 7)

        backup_dir = _get_backup_dir()
        backups = list(backup_dir.glob("grouper_pre_migration_v5_to_v7_*"))
        assert len(backups) == 1
        assert backups[0].suffix == ".db"

    def test_retention_keeps_only_3(self, tmp_path: Path) -> None:
        from grouper.database.migrations import _cleanup_migration_backups

        # isolated_db already points DATA_DIR at a temp directory
        backup_dir = _get_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Remove any backups created by prior init_database calls
        for f in backup_dir.glob("grouper_pre_migration_v*"):
            f.unlink()

        # Create 5 fake migration backups
        for i in range(5):
            p = backup_dir / f"grouper_pre_migration_v{i}_to_v{i + 1}_2026010{i}_120000.db"
            p.write_text("fake")

        _cleanup_migration_backups(keep=3)

        remaining = list(backup_dir.glob("grouper_pre_migration_v*"))
        assert len(remaining) == 3


# ===========================================================================
# Individual migration idempotency on fresh schema
# ===========================================================================


class TestMigrationIdempotency:
    def test_each_migration_runs_on_fresh_schema(self) -> None:
        """Each migration's upgrade() should run cleanly on a DB that already
        has all tables from _INITIAL_SCHEMA (fresh install scenario)."""
        import grouper.database.connection as conn_mod
        from grouper.database.migrations import _discover_migrations

        _init_schema_only()
        mods = _discover_migrations()

        with conn_mod.get_connection() as conn:
            raw = conn.raw_connection
            for mod in mods:
                # Should not raise — all use CREATE IF NOT EXISTS / PRAGMA checks
                mod.upgrade(raw)
