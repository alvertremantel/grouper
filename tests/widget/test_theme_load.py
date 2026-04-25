"""Widget tests covering theme loading and switching."""

from __future__ import annotations

import pytest
from grouper.styles import _get_template, available_themes, load_theme

pytestmark = pytest.mark.widget


class TestLoadTheme:
    """Verify the QSS rendering pipeline and theme switching."""

    def test_load_theme_produces_nonempty_stylesheet(self, qapp) -> None:
        load_theme(qapp, "dark")
        assert qapp.styleSheet().strip()

    def test_load_theme_replaces_all_tokens(self, qapp) -> None:
        load_theme(qapp, "dark")
        assert "{{" not in qapp.styleSheet()
        assert "}}" not in qapp.styleSheet()

    @pytest.mark.parametrize("theme", available_themes())
    def test_every_theme_loads_without_error(self, qapp, theme: str) -> None:
        load_theme(qapp, theme)
        rendered = qapp.styleSheet()
        assert rendered.strip()
        assert rendered != _get_template()

    def test_theme_switch_changes_stylesheet(self, qapp) -> None:
        load_theme(qapp, "dark")
        dark = qapp.styleSheet()

        load_theme(qapp, "light")
        light = qapp.styleSheet()

        assert dark != light

    def test_theme_switch_preserves_window_visibility(self, main_window, qapp) -> None:
        main_window.show()
        load_theme(qapp, "dark")
        qapp.processEvents()

        load_theme(qapp, "light")
        qapp.processEvents()

        main_window._sidebar._buttons["About"].click()
        qapp.processEvents()

        assert main_window.isVisible()
        assert main_window._stack.currentIndex() == main_window.VIEW_MAP["About"]
