"""Widget tests covering MainWindow construction."""

from __future__ import annotations

import pytest
from grouper.app import MainWindow, _BorderedCentral
from grouper.ui.animated_stack import AnimatedViewStack
from grouper.ui.sidebar import Sidebar
from grouper.ui.title_bar import TitleBar

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
