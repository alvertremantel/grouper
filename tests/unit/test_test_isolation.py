"""Regression tests ensuring test runs stay fully sandboxed.

These tests verify that the root autouse fixture in conftest.py
successfully isolates both database and config artifacts so tests
never write to the user's real ~/.grouper/ directory.
"""

from __future__ import annotations

from pathlib import Path

import desktop.config as _app_cfg
import grouper_core.config as _cfg
from grouper_core.config import ConfigManager, get_config
from grouper_core.database import connection


def test_config_file_path_is_under_tmp():
    get_config()
    assert not _cfg.CONFIG_FILE.is_relative_to(Path.home() / ".grouper")
    assert _cfg.CONFIG_FILE.parent.exists()


def test_app_dir_is_under_tmp():
    assert not _cfg.APP_DIR.is_relative_to(Path.home() / ".grouper")


def test_reexported_app_config_paths_are_under_tmp():
    assert _app_cfg.APP_DIR == _cfg.APP_DIR
    assert _app_cfg.CONFIG_FILE == _cfg.CONFIG_FILE
    assert not _app_cfg.APP_DIR.is_relative_to(Path.home() / ".grouper")


def test_config_manager_creates_no_real_home_artifacts():
    real_config = Path.home() / ".grouper" / "config.json"
    existed_before = real_config.exists()

    mgr = ConfigManager()
    assert mgr.config is not None

    if not existed_before:
        assert not real_config.exists()


def test_set_data_directory_persists_to_tmp_config(tmp_path: Path):
    real_db_path_config = Path.home() / ".grouper" / "db_path.txt"
    existed_before = real_db_path_config.exists()
    new_data_dir = tmp_path / "new-data-dir"

    assert connection.set_data_directory(new_data_dir)

    isolated_db_path_config = _cfg.APP_DIR / "db_path.txt"
    assert isolated_db_path_config.read_text(encoding="utf-8") == str(new_data_dir)
    assert not isolated_db_path_config.is_relative_to(Path.home() / ".grouper")
    if not existed_before:
        assert not real_db_path_config.exists()
