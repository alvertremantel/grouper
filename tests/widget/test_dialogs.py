"""Widget tests covering frameless dialog construction."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from desktop.ui.tasks.dialogs import (
    AddBoardDialog,
    AddGroupDialog,
    ConfirmDialog,
    CreateActivityDialog,
    CreateProjectDialog,
    CreateTaskDialog,
    EditBoardDialog,
    EditProjectDialog,
    FramelessDialog,
    StopSessionDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QWidget

pytestmark = pytest.mark.widget


class _TestDialog(FramelessDialog):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Test Dialog")


class TestFramelessDialog:
    """Verify the base dialog structure that all subclasses inherit."""

    def test_does_not_use_translucent_background_attribute(self, qapp) -> None:
        dialog = _TestDialog()
        try:
            assert not dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
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
