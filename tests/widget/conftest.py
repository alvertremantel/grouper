"""conftest.py -- Widget test fixtures.

Provides a session-scoped QApplication so all widget tests share one instance.
PySide6 allows only one QApplication per process.
"""

import sys

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Ensure a single QApplication exists for the entire widget test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app
