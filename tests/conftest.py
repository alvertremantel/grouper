"""conftest.py -- Root fixtures shared by all Grouper tests.

Provides only DB isolation. No GUI or pywinauto imports here so that
unit tests never pull in heavyweight dependencies.
"""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point Grouper at a fresh temp database for every test.

    Sets GROUPER_DATA_DIR, re-initialises paths, and creates
    the schema so each test is fully isolated from the user's real data.

    Individual test files may override this fixture if they need different
    setup (e.g. migration tests that don't want init_database called).
    """
    data_dir = tmp_path / "grouper_test"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GROUPER_DATA_DIR", str(data_dir))

    from grouper.database import connection as _conn

    _conn._init_paths()
    _conn.init_database()

    return data_dir


@pytest.fixture
def test_data_dir(isolated_db: Path) -> Path:
    """Return the isolated temp directory for the test database."""
    return isolated_db
