"""Widget tests covering MainWindow construction."""

from __future__ import annotations

import pytest
from desktop.app import MainWindow, _BorderedCentral
from desktop.ui.shared.animated_stack import AnimatedViewStack
from desktop.ui.shared.title_bar import TitleBar
from desktop.ui.views.sidebar import Sidebar

pytestmark = pytest.mark.widget


class TestMainWindowConstruction:
    """Replace coarse launch checks with direct widget assertions."""

    def test_window_title_contains_grouper(self, main_window) -> None:
        assert "Grouper" in main_window.windowTitle()

    def test_central_widget_exists(self, main_window) -> None:
        assert isinstance(main_window.centralWidget(), _BorderedCentral)

    def test_stack_widget_exists(self, main_window) -> None:
        assert isinstance(main_window._stack, AnimatedViewStack)

    def test_sidebar_exists(self, main_window) -> None:
        assert isinstance(main_window._sidebar, Sidebar)

    def test_title_bar_exists(self, main_window) -> None:
        assert isinstance(main_window._title_bar, TitleBar)

    def test_stack_has_expected_view_count(self, main_window) -> None:
        assert main_window._stack.count() == len(MainWindow.VIEW_MAP)
