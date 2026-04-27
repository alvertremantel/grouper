"""conftest.py -- Root fixtures shared by all Grouper tests.

Provides DB and config isolation so tests never touch the user's real
Grouper data or config home directory. No GUI or pywinauto imports here
so that unit tests never pull in heavyweight dependencies.
"""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point Grouper at a fresh temp database for every test.

    Sets GROUPER_DATA_DIR, re-initialises paths, and creates
    the schema so each test is fully isolated from the user's real data.

    Also isolates config paths (APP_DIR / CONFIG_FILE) so no config.json
    artifacts are written to the user's real home directory, and resets
    the ConfigManager singleton so each test starts with a clean instance.

    Individual test files may override this fixture if they need different
    setup (e.g. migration tests that don't want init_database called).
    """
    data_dir = tmp_path / "grouper_test"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GROUPER_DATA_DIR", str(data_dir))

    import desktop.config as _app_cfg
    import grouper_core.config as _cfg

    fake_app_dir = tmp_path / "grouper_config"
    fake_config_file = fake_app_dir / "config.json"
    monkeypatch.setattr(_cfg, "APP_DIR", fake_app_dir)
    monkeypatch.setattr(_cfg, "CONFIG_FILE", fake_config_file)
    monkeypatch.setattr(_app_cfg, "APP_DIR", fake_app_dir)
    monkeypatch.setattr(_app_cfg, "CONFIG_FILE", fake_config_file)
    _cfg.ConfigManager._instance = None

    from desktop.database import connection as _conn

    _conn._init_paths()
    _conn.init_database()

    return data_dir


@pytest.fixture
def test_data_dir(isolated_db: Path) -> Path:
    """Return the isolated temp directory for the test database."""
    return isolated_db
