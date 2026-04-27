"""Tests for the centralised SVG icon cache (desktop.ui.shared.icons)."""

from __future__ import annotations

import pytest
from desktop.ui.shared.icons import _cache, clear_cache, get_icon
from PySide6.QtGui import QIcon

pytestmark = pytest.mark.usefixtures("qapp")


class TestGetIcon:
    """get_icon returns cached QIcon instances."""

    def test_returns_qicon(self) -> None:
        icon = get_icon("edit", "#ff0000")
        assert isinstance(icon, QIcon)

    def test_cache_hit(self) -> None:
        clear_cache()
        a = get_icon("trash", "#00ff00")
        b = get_icon("trash", "#00ff00")
        assert a is b

    def test_different_color_is_different_entry(self) -> None:
        clear_cache()
        a = get_icon("edit", "#ff0000")
        b = get_icon("edit", "#0000ff")
        assert a is not b

    def test_different_size_is_different_entry(self) -> None:
        clear_cache()
        a = get_icon("edit", "#ff0000", size=16)
        b = get_icon("edit", "#ff0000", size=24)
        assert a is not b

    def test_unknown_name_raises(self) -> None:
        with pytest.raises(KeyError, match="no_such_icon"):
            get_icon("no_such_icon", "#000000")

    def test_all_registered_names(self) -> None:
        clear_cache()
        names = (
            "settings",
            "edit",
            "trash",
            "move",
            "copy",
            "nav_prev",
            "nav_next",
            "home",
            "clock",
            "grid",
            "list",
            "calendar",
            "history",
            "chart",
            "info",
        )
        for name in names:
            icon = get_icon(name, "#aaaaaa")
            assert isinstance(icon, QIcon), f"{name} did not return QIcon"


class TestClearCache:
    """clear_cache empties the icon cache."""

    def test_clear(self) -> None:
        get_icon("edit", "#ff0000")
        assert len(_cache) > 0
        clear_cache()
        assert len(_cache) == 0

    def test_fresh_icon_after_clear(self) -> None:
        a = get_icon("edit", "#ff0000")
        clear_cache()
        b = get_icon("edit", "#ff0000")
        # Same logical icon but different object after cache clear
        assert a is not b
