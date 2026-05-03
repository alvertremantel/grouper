"""Widget tests covering sidebar navigation."""

from __future__ import annotations

import pytest
from desktop.app import MainWindow

pytestmark = pytest.mark.widget


class TestSidebarNavigation:
    """Replace the old sidebar E2E coverage with direct widget tests."""

    def test_sidebar_has_all_view_buttons(self, main_window) -> None:
        assert set(main_window._sidebar._buttons) == set(MainWindow.VIEW_MAP)

    def test_view_names_match_stack_indices(self, main_window) -> None:
        assert main_window._stack.count() == len(MainWindow.VIEW_MAP)
        for name, index in MainWindow.VIEW_MAP.items():
            assert name in main_window._sidebar._buttons
            assert main_window._stack.widget(index) is not None

    def test_clicking_sidebar_button_switches_stack(self, main_window, qapp) -> None:
        target_name = "Settings"
        target_index = MainWindow.VIEW_MAP[target_name]

        main_window.show()
        qapp.processEvents()

        main_window._sidebar._buttons[target_name].click()
        qapp.processEvents()

        assert main_window._stack.currentIndex() == target_index
        assert main_window._sidebar._buttons[target_name].isChecked()
