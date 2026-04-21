"""
sidebar.py — Vertical navigation sidebar for Grouper.
"""

from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from ..config import get_config
from ..styles import theme_colors
from .icons import clear_cache, get_icon


class SidebarButton(QPushButton):
    """A checkable navigation button for the sidebar with dual-color SVG icon."""

    def __init__(self, text: str, icon_name: str, parent=None) -> None:
        super().__init__(" " + text, parent)
        self._icon_name = icon_name
        self._muted_icon: QIcon | None = None
        self._accent_icon: QIcon | None = None
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def load_icons(self, muted: str, accent: str, size: int = 20) -> None:
        """Fetch muted + accent icons from the cache and apply current check state."""
        self._muted_icon = get_icon(self._icon_name, muted, size)
        self._accent_icon = get_icon(self._icon_name, accent, size)
        self.setIconSize(QSize(size, size))
        self._apply_icon()

    def setChecked(self, checked: bool) -> None:  # type: ignore[override]
        super().setChecked(checked)
        self._apply_icon()

    def _apply_icon(self) -> None:
        icon = self._accent_icon if self.isChecked() else self._muted_icon
        if icon is not None:
            self.setIcon(icon)


class Sidebar(QFrame):
    """Vertical sidebar with navigation buttons."""

    navigation_changed = Signal(str)  # emits the view name

    ITEMS: ClassVar[list[tuple[str, str]]] = [
        ("Dashboard", "home"),
        ("Time Tracker", "clock"),
        ("Task Board", "grid"),
        ("Task List", "list"),
        ("Calendar", "calendar"),
        ("History", "history"),
        ("Summary", "chart"),
        ("Sync", "sync"),
        ("Settings", "settings"),
        ("About", "info"),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._buttons: dict[str, SidebarButton] = {}
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addSpacing(8)

        colors = theme_colors(get_config().theme)
        muted = colors["icon_stroke"]
        accent = colors["accent"]

        for name, icon_name in self.ITEMS:
            btn = SidebarButton(name, icon_name)
            btn.load_icons(muted, accent)
            btn.clicked.connect(lambda checked, n=name: self._on_click(n))
            self._buttons[name] = btn
            layout.addWidget(btn)

        layout.addStretch()

        first = self.ITEMS[0][0]
        self._buttons[first].setChecked(True)

    def changeEvent(self, event) -> None:  # type: ignore[override]
        super().changeEvent(event)
        from PySide6.QtCore import QEvent

        if event.type() == QEvent.Type.StyleChange:
            clear_cache()
            colors = theme_colors(get_config().theme)
            muted = colors["icon_stroke"]
            accent = colors["accent"]
            for btn in self._buttons.values():
                btn.load_icons(muted, accent)

    def _on_click(self, name: str) -> None:
        for key, btn in self._buttons.items():
            btn.setChecked(key == name)
        self.navigation_changed.emit(name)

    def select(self, name: str) -> None:
        """Programmatically select a sidebar item."""
        self._on_click(name)
