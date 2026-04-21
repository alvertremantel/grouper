"""test_core_standalone.py — Verify grouper_core works without PySide6.

These tests ensure the shared data layer can be imported and used on a
headless machine where PySide6 is not installed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point Grouper at a fresh temp database (no init_database — we test that)."""
    data_dir = tmp_path / "grouper_test"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GROUPER_DATA_DIR", str(data_dir))

    from grouper_core.database import connection as conn

    conn._init_paths()
    return data_dir


class TestCoreImportsWithoutPySide6:
    """Verify grouper_core never touches PySide6."""

    def test_database_connection_import(self):
        from grouper_core.database.connection import (
            init_database,
            register_data_changed_callback,
        )

        assert callable(init_database)
        assert callable(register_data_changed_callback)

    def test_models_import(self):
        from grouper_core.models import Task

        assert Task is not None

    def test_config_import(self):
        from grouper_core.config import get_config

        assert callable(get_config)

    def test_colors_import(self):
        from grouper_core.colors import theme_colors

        colors = theme_colors("dark")
        assert isinstance(colors, dict)

    def test_formatting_import(self):
        from grouper_core.formatting import format_duration

        assert format_duration(3661) == "1h 01m 01s"

    def test_operations_import(self):
        from grouper_core.operations import sync_task_tags

        assert callable(sync_task_tags)


class TestCoreDatabase:
    """Verify init_database and basic CRUD via grouper_core."""

    def test_init_database_creates_db(self, isolated_db: Path):
        from grouper_core.database.connection import get_database_path, init_database

        init_database()
        assert get_database_path().exists()

    def test_crud_via_core(self, isolated_db: Path):
        from grouper_core.database.boards import create_board, list_boards
        from grouper_core.database.connection import init_database

        init_database()
        create_board("Test Board")
        boards = list_boards()
        assert any(b.name == "Test Board" for b in boards)


class TestCallbackNotification:
    """Verify the callback system replaces PySide6 signals."""

    def test_callback_fires_on_bump(self, isolated_db: Path):
        from grouper_core.database.connection import (
            bump_version,
            register_data_changed_callback,
            unregister_data_changed_callback,
        )

        cb = MagicMock()
        register_data_changed_callback(cb)
        try:
            bump_version()
            assert cb.call_count == 1

            bump_version()
            assert cb.call_count == 2
        finally:
            unregister_data_changed_callback(cb)

    def test_unregister_stops_calls(self, isolated_db: Path):
        from grouper_core.database.connection import (
            bump_version,
            register_data_changed_callback,
            unregister_data_changed_callback,
        )

        cb = MagicMock()
        register_data_changed_callback(cb)
        unregister_data_changed_callback(cb)

        bump_version()
        assert cb.call_count == 0
