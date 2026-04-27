"""conftest.py -- Widget test fixtures.

Provides a session-scoped QApplication plus a lightweight MainWindow fixture
that reuses the existing isolated test database instead of touching user data.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Ensure a single QApplication exists for the entire widget test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def main_window(qapp: QApplication):
    """Create a MainWindow with a small mocked config surface."""
    cfg = MagicMock()
    cfg.theme = "dark"
    cfg.window_width = 1000
    cfg.window_height = 600
    cfg.animations_enabled = False

    with (
        patch("desktop.app.get_config", return_value=cfg),
        patch("desktop.app.theme_colors", return_value={"window-border": "#7aa2f7"}),
        patch("desktop.ui.views.sidebar.get_config", return_value=cfg),
        patch("desktop.ui.shared.animated_stack.get_config", return_value=cfg),
    ):
        from desktop.app import MainWindow

        win = MainWindow()
        yield win
        win.close()
        win.deleteLater()
        qapp.processEvents()
