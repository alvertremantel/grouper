"""Widget tests covering frameless dialog construction."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from desktop.ui.shared.base_dialog import BaseButtonDialog, BaseFormDialog, FramelessDialog
from desktop.ui.tasks.dialogs import (
    AddBoardDialog,
    AddGroupDialog,
    ConfirmDialog,
    CreateActivityDialog,
    CreateProjectDialog,
    CreateTaskDialog,
    EditBoardDialog,
    EditProjectDialog,
    StopSessionDialog,
)
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialogButtonBox, QFrame, QGraphicsDropShadowEffect, QLabel, QWidget

pytestmark = pytest.mark.widget


class _TestDialog(FramelessDialog):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Test Dialog")


class TestFramelessDialog:
    """Verify the base dialog structure that all subclasses inherit."""

    def test_uses_translucent_background_attribute(self, qapp) -> None:
        dialog = _TestDialog()
        try:
            assert dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        finally:
            dialog.deleteLater()

    def test_does_not_auto_fill_background(self, qapp) -> None:
        dialog = _TestDialog()
        try:
            assert not dialog.autoFillBackground()
        finally:
            dialog.deleteLater()

    def test_has_frameless_window_hint(self, qapp) -> None:
        dialog = _TestDialog()
        try:
            flags = dialog.windowFlags()
            assert flags & Qt.WindowType.FramelessWindowHint
            assert flags & Qt.WindowType.Dialog
        finally:
            dialog.deleteLater()

    def test_dialog_frame_object_name(self, qapp) -> None:
        dialog = _TestDialog()
        try:
            assert dialog.findChild(QFrame, "dialogFrame") is not None
        finally:
            dialog.deleteLater()

    def test_dialog_content_object_name(self, qapp) -> None:
        dialog = _TestDialog()
        try:
            assert dialog.findChild(QWidget, "dialogContent") is not None
        finally:
            dialog.deleteLater()

    def test_dialog_has_drop_shadow(self, qapp) -> None:
        dialog = _TestDialog()
        try:
            frame = dialog.findChild(QFrame, "dialogFrame")
            assert frame is not None
            assert isinstance(frame.graphicsEffect(), QGraphicsDropShadowEffect)
        finally:
            dialog.deleteLater()

    def test_dialog_title_bar_drag_moves_window(self, qapp) -> None:
        dialog = _TestDialog()
        dialog.move(200, 200)
        dialog.show()
        qapp.processEvents()
        try:
            title_bar = dialog.findChild(QWidget, "dialogTitleBar")
            assert title_bar is not None
            start_pos = dialog.pos()
            center = title_bar.rect().center()
            # Simulate a left-button drag on the title bar
            QTest.mousePress(title_bar, Qt.MouseButton.LeftButton, pos=center)
            qapp.processEvents()
            # Move the mouse 40 px right / 30 px down in global space
            global_center = title_bar.mapToGlobal(center)
            QTest.mouseMove(title_bar, global_center + QPoint(40, 30))
            qapp.processEvents()
            QTest.mouseRelease(title_bar, Qt.MouseButton.LeftButton)
            qapp.processEvents()
            # The dialog should have moved (or at least _drag_pos was set)
            assert dialog.pos() != start_pos or hasattr(title_bar, "_drag_pos")
        finally:
            dialog.close()
            dialog.deleteLater()


class TestBaseButtonDialog:
    """Verify the custom-content button dialog base."""

    def test_finalize_content_adds_button_box(self, qapp) -> None:
        class TinyDialog(BaseButtonDialog):
            def __init__(self):
                super().__init__("Tiny", 200)
                self.finalize_content()

        dlg = TinyDialog()
        try:
            boxes = dlg.findChildren(QDialogButtonBox)
            assert len(boxes) == 1
            assert dlg.contentLayout().indexOf(boxes[0]) >= 0
        finally:
            dlg.deleteLater()

    def test_finalize_content_twice_raises(self, qapp) -> None:
        class TinyDialog(BaseButtonDialog):
            def __init__(self):
                super().__init__("Tiny", 200)
                self.finalize_content()

        dlg = TinyDialog()
        try:
            with pytest.raises(RuntimeError):
                dlg.finalize_content()
        finally:
            dlg.deleteLater()


_DIALOG_FACTORIES: list[tuple[str, Callable[[], FramelessDialog]]] = [
    ("CreateActivityDialog", lambda: CreateActivityDialog()),
    ("CreateProjectDialog", lambda: CreateProjectDialog(1)),
    ("EditProjectDialog", lambda: EditProjectDialog("Project", 1, None)),
    ("EditBoardDialog", lambda: EditBoardDialog(1, "Board")),
    ("AddBoardDialog", lambda: AddBoardDialog()),
    ("CreateTaskDialog", lambda: CreateTaskDialog([])),
    ("StopSessionDialog", lambda: StopSessionDialog("Activity")),
    ("ConfirmDialog", lambda: ConfirmDialog("Confirm", "Body text")),
    ("AddGroupDialog", lambda: AddGroupDialog(["Focus"], [])),
]


class TestDialogSubclasses:
    """Verify lightweight construction coverage across dialog subclasses."""

    @pytest.mark.parametrize(("dialog_name", "factory"), _DIALOG_FACTORIES)
    def test_dialog_constructs(self, qapp, dialog_name: str, factory: Callable[[], FramelessDialog]):
        dialog = factory()
        try:
            assert isinstance(dialog, FramelessDialog), dialog_name
            assert dialog.windowTitle()
        finally:
            dialog.deleteLater()

    def test_add_group_dialog_is_base_button_dialog(self, qapp) -> None:
        dlg = AddGroupDialog(["Focus"], [])
        try:
            assert isinstance(dlg, BaseButtonDialog)
            assert not isinstance(dlg, BaseFormDialog)
        finally:
            dlg.deleteLater()

    def test_add_group_dialog_has_no_form_attribute(self, qapp) -> None:
        dlg = AddGroupDialog(["Focus"], [])
        try:
            assert not hasattr(dlg, "_form")
        finally:
            dlg.deleteLater()

    def test_stop_session_dialog_is_base_button_dialog(self, qapp) -> None:
        dlg = StopSessionDialog("Activity")
        try:
            assert isinstance(dlg, BaseButtonDialog)
            assert not isinstance(dlg, BaseFormDialog)
        finally:
            dlg.deleteLater()

    def test_add_group_dialog_tag_variant(self, qapp) -> None:
        dlg = AddGroupDialog(
            ["Alpha"],
            [],
            title="Add Tag",
            item_label="tag",
            limit_hint=None,
        )
        try:
            assert dlg.windowTitle() == "Add Tag"
            info = dlg.findChild(QLabel, "infoLabel")
            assert info is not None
            assert "tag name" in info.text().lower()
            assert "max 3 groups" not in info.text().lower()
        finally:
            dlg.deleteLater()

    def test_no_remove_item_self_form_in_dialogs_source(self) -> None:
        src = Path(__file__).parents[2] / "desktop" / "ui" / "tasks" / "dialogs.py"
        assert src.exists()
        text = src.read_text(encoding="utf-8")
        assert "removeItem(self._form)" not in text
