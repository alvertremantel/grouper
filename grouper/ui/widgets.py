"""
widgets.py — Shared themed Qt widgets for Grouper.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, Signal, SignalInstance
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QStyleOptionSpinBox,
    QWidget,
)

from ..config import get_config
from ..styles import theme_colors

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def reconnect(signal: SignalInstance, slot: object) -> None:
    """Disconnect all receivers of *signal*, then connect *slot*."""
    with contextlib.suppress(RuntimeError):
        signal.disconnect()
    signal.connect(slot)


def clear_layout(layout: QLayout, *, keep: set[QWidget] | None = None) -> None:
    """Remove and ``deleteLater`` all widgets in *layout*.

    Widgets in *keep* (if provided) are removed from the layout but
    **not** deleted.  Nested layouts are cleared recursively.
    """
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            if keep and widget in keep:
                continue
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout(), keep=keep)


def clear_flow(layout: QLayout) -> None:
    """Remove all widgets and spacer items from a flow layout."""
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()


def restyle_tree(widget: QWidget) -> None:
    """Force QSS re-evaluation on *widget* and all its children.

    Qt does not propagate descendant-selector changes when a parent's
    objectName is set after initial styling.  Call this after any
    dynamic ``setObjectName()`` to ensure children pick up rules like
    ``#card QWidget { background-color: transparent; }``.
    """
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    for child in widget.findChildren(QWidget):
        style.unpolish(child)
        style.polish(child)


class ElidedLabel(QLabel):
    """QLabel that elides text with '. . .' when space is tight."""

    _ELLIPSIS = " . . ."

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def setFullText(self, text: str) -> None:
        self._full_text = text
        self._elide()

    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        metrics = self.fontMetrics()
        avail = self.width()
        if metrics.horizontalAdvance(self._full_text) <= avail:
            super().setText(self._full_text)
            return
        suffix_w = metrics.horizontalAdvance(self._ELLIPSIS)
        lo, hi = 0, len(self._full_text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if metrics.horizontalAdvance(self._full_text[:mid]) + suffix_w <= avail:
                lo = mid
            else:
                hi = mid - 1
        trimmed = self._full_text[:lo]
        super().setText(trimmed.rstrip() + self._ELLIPSIS if trimmed else self._ELLIPSIS)


def truncate_title(text: str, max_len: int = 25) -> str:
    """Truncate *text* with ellipsis if it exceeds *max_len*."""
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def make_chip(text: str, *, strikethrough: bool = False) -> QFrame:
    """Read-only chip (chipFrame + smallMuted label)."""
    chip = QFrame()
    chip.setObjectName("chipFrame")
    lay = QHBoxLayout(chip)
    lay.setContentsMargins(6, 2, 6, 2)
    lay.setSpacing(0)
    lbl = QLabel(text)
    lbl.setObjectName("smallMuted")
    if strikethrough:
        lbl.setStyleSheet("text-decoration: line-through;")
    lay.addWidget(lbl)
    return chip


def make_removable_chip(text: str, on_remove: Callable[[], None]) -> QFrame:
    """Chip with x remove button (chipFrame + smallMuted label)."""
    chip = QFrame()
    chip.setObjectName("chipFrame")
    lay = QHBoxLayout(chip)
    lay.setContentsMargins(6, 2, 2, 2)
    lay.setSpacing(4)
    lbl = QLabel(text)
    lbl.setObjectName("smallMuted")
    lay.addWidget(lbl)
    btn = QPushButton("x")
    btn.setObjectName("removeButton")
    btn.setFixedSize(18, 18)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(on_remove)
    lay.addWidget(btn)
    return chip


def flash_checkbox_blocked(check: QCheckBox, blocker_names: str, duration_ms: int = 800) -> None:
    """Flash a checkbox red to indicate blocked completion."""
    check.setProperty("blocked", True)
    check.style().unpolish(check)
    check.style().polish(check)
    check.setToolTip(f"Blocked by: {blocker_names}")

    def _clear() -> None:
        check.setProperty("blocked", False)
        check.style().unpolish(check)
        check.style().polish(check)
        check.setToolTip("")

    QTimer.singleShot(duration_ms, _clear)


def show_or_empty(has_data: bool, *content: QWidget, empty: QWidget) -> None:
    """Show *content* widgets and hide *empty* when *has_data* is True, else reverse."""
    for w in content:
        w.setVisible(has_data)
    empty.setVisible(not has_data)


# ---------------------------------------------------------------------------
# SVG chevron templates
# ---------------------------------------------------------------------------

_CHEVRON_UP_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 6">'
    '<polyline points="1.5,5 5,1.5 8.5,5" stroke="{color}" '
    'stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)

_CHEVRON_DOWN_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 6">'
    '<polyline points="1.5,1 5,4.5 8.5,1" stroke="{color}" '
    'stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)


# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------


class _ChevronMixin:
    """Paints custom SVG chevron arrows over the native up/down buttons."""

    def paintEvent(self, event: object) -> None:
        super().paintEvent(event)  # type: ignore[misc]

        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)  # type: ignore[attr-defined]
        style = self.style()  # type: ignore[attr-defined]

        up_rect = style.subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            opt,
            QStyle.SubControl.SC_SpinBoxUp,
            self,
        )
        down_rect = style.subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            opt,
            QStyle.SubControl.SC_SpinBoxDown,
            self,
        )

        color = self.palette().color(QPalette.ColorRole.Text).name()  # type: ignore[attr-defined]
        painter = QPainter(self)  # type: ignore[arg-type]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for rect, svg_tmpl in ((up_rect, _CHEVRON_UP_SVG), (down_rect, _CHEVRON_DOWN_SVG)):
            svg_data = svg_tmpl.format(color=color).encode("utf-8")
            renderer = QSvgRenderer(svg_data)
            icon_w, icon_h = 10, 6
            target = QRectF(
                rect.x() + (rect.width() - icon_w) / 2,
                rect.y() + (rect.height() - icon_h) / 2,
                icon_w,
                icon_h,
            )
            renderer.render(painter, target)

        painter.end()


# ---------------------------------------------------------------------------
# Themed widgets
# ---------------------------------------------------------------------------


class ThemedSpinBox(_ChevronMixin, QSpinBox):
    """QSpinBox with custom SVG chevron arrows that follow the theme."""


class ThemedDateEdit(_ChevronMixin, QDateEdit):
    """QDateEdit with custom SVG chevron arrows; arrows always step ±1 day."""

    def stepBy(self, steps: int) -> None:
        self.setDate(self.date().addDays(steps))


# ---------------------------------------------------------------------------
# Segmented control
# ---------------------------------------------------------------------------


class SegmentedControl(QWidget):
    """Horizontal toggle bar — visually a single bar of segments.

    The selected segment gets a highlighted background and accent-colored text
    (matching the sidebar checked state).  Unselected segments use muted text.

    Emits ``index_changed(int)`` when the selection changes.
    """

    index_changed = Signal(int)

    def __init__(self, labels: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: list[QPushButton] = []
        self._selected = 0

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        for i, text in enumerate(labels):
            btn = QPushButton(text)
            btn.setObjectName(f"seg_{i}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _checked, idx=i: self.set_index(idx))
            self._buttons.append(btn)
            lay.addWidget(btn)

        self._apply_theme()
        self.set_index(0)

    # -- public API ----------------------------------------------------------

    def set_index(self, index: int) -> None:
        """Select the segment at *index* and emit ``index_changed``."""
        if index < 0 or index >= len(self._buttons):
            return
        if index == self._selected:
            return
        self._selected = index
        self._apply_styles()
        self.index_changed.emit(index)

    def selected_index(self) -> int:
        return self._selected

    # -- theming -------------------------------------------------------------

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            self._apply_theme()

    def _apply_theme(self) -> None:
        """Re-read theme colors and refresh styles."""
        colors = theme_colors(get_config().theme)
        self._accent = colors["accent"]
        self._bg_tertiary = colors["bg-tertiary"]
        self._text_muted = colors["text-muted"]
        self._bg_secondary = colors["bg-secondary"]
        self._border = colors["border"]
        self._apply_styles()

    def _apply_styles(self) -> None:
        """Apply per-button inline styles based on selection state."""
        n = len(self._buttons)
        for i, btn in enumerate(self._buttons):
            # Per-corner radius: round outer edges only (6px matches standard buttons)
            if n == 1:
                tl = tr = br = bl = 9
            elif i == 0:
                tl, tr, br, bl = 9, 0, 0, 9
            elif i == n - 1:
                tl, tr, br, bl = 0, 9, 9, 0
            else:
                tl = tr = br = bl = 0

            radii = (
                f"  border-top-left-radius: {tl}px;"
                f"  border-top-right-radius: {tr}px;"
                f"  border-bottom-right-radius: {br}px;"
                f"  border-bottom-left-radius: {bl}px;"
            )

            sel = f"#seg_{i}"
            if i == self._selected:
                btn.setStyleSheet(
                    f"QPushButton{sel} {{"
                    f"  background-color: {self._bg_tertiary};"
                    f"  color: {self._accent};"
                    f"  font-weight: 600;"
                    f"  border: 1px solid transparent;"
                    f"  {radii}"
                    f"  padding: 7px 16px;"
                    f"  min-height: 20px;"
                    f"}}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton{sel} {{"
                    f"  background-color: {self._bg_secondary};"
                    f"  color: {self._text_muted};"
                    f"  font-weight: 400;"
                    f"  border: 1px solid transparent;"
                    f"  {radii}"
                    f"  padding: 7px 16px;"
                    f"  min-height: 20px;"
                    f"}}"
                    f"QPushButton{sel}:hover {{"
                    f"  background-color: {self._bg_tertiary};"
                    f"}}"
                )
