"""Tests for dialog surface opacity and theme contrast."""

from __future__ import annotations

import math
import re

import pytest
from desktop.models import Activity
from desktop.styles import _THEME_PALETTE, available_themes, load_theme
from desktop.ui.tasks.dialogs import AddGroupDialog, FramelessDialog
from desktop.ui.time.activity_config import _ActivityDetailEditor
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFrame, QLabel, QListWidget, QWidget

pytestmark = pytest.mark.widget

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_KEY_PIXEL_THEMES = ["black", "dark", "light", "oxygen"]


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    assert _HEX_RE.match(hex_str), f"invalid hex color: {hex_str}"
    return (
        int(hex_str[1:3], 16),
        int(hex_str[3:5], 16),
        int(hex_str[5:7], 16),
    )


def _relative_luminance(hex_str: str) -> float:
    def _channel(value: int) -> float:
        normalized = value / 255.0
        if normalized <= 0.03928:
            return normalized / 12.92
        return ((normalized + 0.055) / 1.055) ** 2.4

    red, green, blue = _hex_to_rgb(hex_str)
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def _contrast_ratio(c1: str, c2: str) -> float:
    lighter = max(_relative_luminance(c1), _relative_luminance(c2))
    darker = min(_relative_luminance(c1), _relative_luminance(c2))
    return (lighter + 0.05) / (darker + 0.05)


def _perceptual_delta(c1: str, c2: str) -> float:
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    distance = math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)
    return distance / math.sqrt(3 * 255**2)


def _grab_screen_rect(widget: QWidget) -> tuple[QRect, QImage]:
    screen = widget.screen()
    assert screen is not None
    rect = widget.frameGeometry()
    pixmap = screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())
    return rect, pixmap.toImage()


def _sample_screen_pixel(widget: QWidget, point: QPoint) -> QColor:
    rect, image = _grab_screen_rect(widget)
    return image.pixelColor(point - rect.topLeft())


def _sample_widget_pixel(widget: QWidget, point: QPoint) -> QColor:
    image = widget.grab().toImage()
    return image.pixelColor(point)


def _sample_hex(widget: QWidget, point: QPoint) -> str:
    return _sample_screen_pixel(widget, point).name().lower()


def _center_point(widget: QWidget) -> QPoint:
    return widget.rect().center()


def _global_center_point(widget: QWidget) -> QPoint:
    return widget.mapToGlobal(widget.rect().center())


def _global_page_sample_point(widget: QWidget) -> QPoint:
    return widget.mapToGlobal(QPoint(20, 20))


def _global_card_sample_point(widget: QWidget) -> QPoint:
    return widget.mapToGlobal(QPoint(widget.width() - 40, widget.height() - 40))


def _settle_ui(qapp) -> None:
    qapp.processEvents()
    QTest.qWait(25)
    qapp.processEvents()


class _TestDialog(FramelessDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Opacity Test")
        self.resize(420, 280)
        layout = self.contentLayout()
        layout.addWidget(QLabel("Dialog body"))
        layout.addStretch(1)


@pytest.fixture
def themed_dialog(qapp):
    def _make(theme: str = "dark") -> FramelessDialog:
        load_theme(qapp, theme)
        dialog = _TestDialog()
        dialog.move(100, 100)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        _settle_ui(qapp)
        return dialog

    return _make


@pytest.fixture
def themed_page(qapp):
    def _make(theme: str = "dark") -> QWidget:
        load_theme(qapp, theme)
        page = QWidget()
        page.resize(420, 280)
        page.move(40, 40)
        page.show()
        _settle_ui(qapp)
        return page

    return _make


class TestPaletteContrastForDialogs:
    """Verify every theme provides enough dialog chrome separation."""

    def test_dialog_chrome_differs_from_page_bg(self) -> None:
        for name, colors in _THEME_PALETTE.items():
            deltas = [
                _perceptual_delta(colors["bg-primary"], colors["dialog-title-bg"]),
                _perceptual_delta(colors["bg-primary"], colors["dialog-border"]),
            ]
            assert max(deltas) >= 0.04, f"{name}: dialog chrome blends into page background"

    def test_all_themes_have_dialog_critical_tokens(self) -> None:
        required = {
            "bg-primary",
            "text",
            "text-muted",
            "dialog-bg",
            "dialog-content-bg",
            "dialog-title-bg",
            "dialog-border",
        }
        for name, colors in _THEME_PALETTE.items():
            assert required.issubset(colors), f"{name} missing {sorted(required - set(colors))}"

    def test_black_dialog_uses_standard_black_theme_surfaces(self) -> None:
        colors = _THEME_PALETTE["black"]
        assert colors["dialog-bg"] == colors["bg-primary"]
        assert colors["dialog-content-bg"] == colors["bg-primary"]
        assert colors["dialog-title-bg"] == colors["bg-tertiary"]
        assert colors["dialog-border"] == colors["border"]

    def test_border_differs_from_bg_primary(self) -> None:
        for name, colors in _THEME_PALETTE.items():
            assert colors["dialog-border"] != colors["bg-primary"], name
            assert _contrast_ratio(colors["dialog-border"], colors["bg-primary"]) > 1.05, name


class TestFramelessDialogOpacity:
    """Verify shown frameless dialogs render distinct screen-visible surfaces."""

    @pytest.mark.parametrize("theme", available_themes())
    def test_dialog_content_is_opaque_on_screen(self, qapp, themed_dialog, theme: str) -> None:
        dialog = themed_dialog(theme)
        try:
            content = dialog.findChild(QWidget, "dialogContent")
            assert content is not None
            pixel = _sample_screen_pixel(dialog, _global_center_point(content))
            assert pixel.alpha() == 255
        finally:
            dialog.close()
            dialog.deleteLater()
            qapp.processEvents()

    @pytest.mark.parametrize("theme", available_themes())
    def test_dialog_frame_is_opaque_on_screen(self, qapp, themed_dialog, theme: str) -> None:
        dialog = themed_dialog(theme)
        try:
            frame = dialog.findChild(QFrame, "dialogFrame")
            assert frame is not None
            pixel = _sample_screen_pixel(dialog, frame.mapToGlobal(QPoint(10, 10)))
            assert pixel.alpha() == 255
        finally:
            dialog.close()
            dialog.deleteLater()
            qapp.processEvents()

    @pytest.mark.parametrize("theme", _KEY_PIXEL_THEMES)
    def test_dialog_chrome_differs_from_plain_page(self, qapp, themed_dialog, themed_page, theme: str) -> None:
        page = themed_page(theme)
        dialog = themed_dialog(theme)
        try:
            page_hex = _sample_hex(page, _global_page_sample_point(page))
            title_bar = dialog.findChild(QWidget, "dialogTitleBar")
            assert title_bar is not None

            title_hex = _sample_hex(dialog, _global_center_point(title_bar))

            assert _perceptual_delta(page_hex, title_hex) >= 0.015, (
                f"{theme}: dialog chrome is visually indistinguishable from the page"
            )
        finally:
            page.close()
            page.deleteLater()
            dialog.close()
            dialog.deleteLater()
            qapp.processEvents()

    @pytest.mark.parametrize("theme", _KEY_PIXEL_THEMES)
    def test_parented_dialog_chrome_differs_from_host_page(self, qapp, theme: str) -> None:
        load_theme(qapp, theme)
        host = QWidget()
        host.resize(800, 600)
        host.move(0, 0)
        host.show()
        _settle_ui(qapp)

        dialog = _TestDialog(host)
        dialog.move(100, 100)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        _settle_ui(qapp)
        try:
            title_bar = dialog.findChild(QWidget, "dialogTitleBar")
            assert title_bar is not None
            host_hex = _sample_screen_pixel(host, _global_page_sample_point(host)).name().lower()
            title_hex = _sample_screen_pixel(dialog, _global_center_point(title_bar)).name().lower()
            assert _perceptual_delta(host_hex, title_hex) >= 0.02, (
                f"{theme}: parented dialog chrome is visually indistinguishable from the host page"
            )
        finally:
            host.close()
            host.deleteLater()
            dialog.close()
            dialog.deleteLater()
            qapp.processEvents()


class TestAddGroupDialogContrast:
    @pytest.mark.parametrize("theme", ["black", "oxygen"])
    def test_group_list_uses_standard_list_surface(self, qapp, theme: str) -> None:
        load_theme(qapp, theme)

        host = _ActivityDetailEditor()
        activity = Activity(
            id=1,
            name="Test Activity",
            description=None,
            is_background=False,
            is_archived=False,
            groups=["Existing"],
            tags=[],
        )
        host.load(activity)
        host.resize(700, 500)
        host.move(0, 0)
        host.show()
        _settle_ui(qapp)

        dialog = AddGroupDialog(["Existing", "Alpha", "Beta", "Gamma"], activity.groups, host)
        dialog.move(120, 80)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        _settle_ui(qapp)
        try:
            existing_list = dialog.findChild(QListWidget)
            assert existing_list is not None
            list_hex = _sample_screen_pixel(
                dialog,
                existing_list.viewport().mapToGlobal(
                    QPoint(existing_list.viewport().width() - 12, existing_list.viewport().height() - 12)
                ),
            ).name().lower()
            expected_hex = _THEME_PALETTE[theme]["bg-secondary"]
            assert _perceptual_delta(expected_hex, list_hex) < 0.02, (
                f"{theme}: add-group list no longer uses the standard list surface"
            )
        finally:
            host.close()
            host.deleteLater()
            dialog.close()
            dialog.deleteLater()
            qapp.processEvents()

    @pytest.mark.parametrize("theme", ["black", "oxygen", "dark", "light"])
    def test_parented_dialog_border_differs_from_host_card(self, qapp, theme: str) -> None:
        load_theme(qapp, theme)

        host = _ActivityDetailEditor()
        activity = Activity(
            id=1,
            name="Test Activity",
            description=None,
            is_background=False,
            is_archived=False,
            groups=["Existing"],
            tags=[],
        )
        host.load(activity)
        host.resize(700, 500)
        host.move(0, 0)
        host.show()
        _settle_ui(qapp)

        dialog = AddGroupDialog(["Existing", "Alpha", "Beta", "Gamma"], activity.groups, host)
        dialog.move(120, 80)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        _settle_ui(qapp)

        try:
            # We want to ensure the 16px margin around the dialog is NOT pure black
            # due to parented QWidget transparency bleed-through.
            margin_point = dialog.mapToGlobal(QPoint(5, 5))
            margin_hex = _sample_screen_pixel(dialog, margin_point).name().lower()

            # The margin should blend with or be distinct from the host card, but definitely NOT pure black glitch
            # Unless the host card itself is black (which is not true for any theme's bg-secondary except maybe black theme)
            # Actually, black theme bg-secondary is #141414, which is not pure black #000000.
            assert margin_hex != "#000000" or _THEME_PALETTE[theme]["bg-secondary"] == "#000000", (
                f"{theme}: margin is pure black, likely due to transparent background glitch"
            )

            frame = dialog.findChild(QFrame, "dialogFrame")
            assert frame is not None

            # Sample the top edge, away from the rounded corners
            border_point = frame.mapToGlobal(QPoint(frame.width() // 2, 0))
            border_hex = _sample_screen_pixel(dialog, border_point).name().lower()

            # Sample the margin just outside the frame, top center
            margin_outside_frame_point = frame.mapToGlobal(QPoint(frame.width() // 2, -5))
            margin_outside_frame_hex = _sample_screen_pixel(dialog, margin_outside_frame_point).name().lower()

            assert _perceptual_delta(margin_outside_frame_hex, border_hex) >= 0.015, (
                f"{theme}: parented dialog border is visually indistinguishable from its surrounding margin"
            )
        finally:
            host.close()
            host.deleteLater()
            dialog.close()
            dialog.deleteLater()
            qapp.processEvents()
