"""Regression tests ensuring test runs stay fully sandboxed.

These tests verify that the root autouse fixture in conftest.py
successfully isolates both database and config artifacts so tests
never write to the user's real ~/.grouper/ directory.
"""

from __future__ import annotations

from pathlib import Path

import grouper_core.config as _cfg
from grouper_core.config import ConfigManager, get_config


def test_config_file_path_is_under_tmp():
    get_config()
    assert not _cfg.CONFIG_FILE.is_relative_to(Path.home() / ".grouper")
    assert _cfg.CONFIG_FILE.parent.exists()


def test_app_dir_is_under_tmp():
    assert not _cfg.APP_DIR.is_relative_to(Path.home() / ".grouper")


def test_config_manager_creates_no_real_home_artifacts():
    real_config = Path.home() / ".grouper" / "config.json"
    existed_before = real_config.exists()

    mgr = ConfigManager()
    assert mgr.config is not None

    if not existed_before:
        assert not real_config.exists()
