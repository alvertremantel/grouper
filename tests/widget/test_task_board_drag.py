"""Widget tests for task board card drag-and-drop behavior."""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import MagicMock, patch

from desktop.models import Project, Task
from desktop.ui.tasks.task_board import TASK_MIME_TYPE, ProjectColumn, TaskCard
from PySide6.QtCore import QByteArray, QEvent, QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget


class _FakeDrag:
    instances: ClassVar[list[_FakeDrag]] = []

    def __init__(self, source) -> None:
        self.source = source
        self.mime_data = None
        self.pixmap = None
        self.hot_spot = None
        self.exec_action = None
        self.__class__.instances.append(self)

    def setMimeData(self, mime_data: QMimeData) -> None:
        self.mime_data = mime_data

    def setPixmap(self, pixmap) -> None:
        self.pixmap = pixmap

    def setHotSpot(self, hot_spot: QPoint) -> None:
        self.hot_spot = hot_spot

    def exec(self, action):
        self.exec_action = action
        return action


def _mouse_event(
    event_type: QEvent.Type,
    pos: QPoint,
    *,
    button: Qt.MouseButton = Qt.MouseButton.NoButton,
    buttons: Qt.MouseButton = Qt.MouseButton.NoButton,
) -> QMouseEvent:
    point = QPointF(pos)
    return QMouseEvent(
        event_type,
        point,
        point,
        point,
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def _make_card(qapp: QApplication) -> TaskCard:
    card = TaskCard()
    card.resize(320, 140)
    card.populate(
        Task(
            id=7,
            project_id=3,
            title="Drag me",
            tags=["alpha"],
        ),
        prereq_tasks=[Task(id=11, project_id=3, title="Prereq")],
    )
    card.show()
    qapp.processEvents()
    return card


def test_task_card_passive_widgets_are_drag_passthrough(qapp: QApplication) -> None:
    """Passive card content should not intercept drag-start mouse events."""
    card = _make_card(qapp)

    assert card._title_lbl.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert card._pri_lbl.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert card._due_lbl.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert card._tags_widget.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert card._prereqs_widget.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    for widget in card._tags_widget.findChildren(QWidget):
        assert widget.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    for widget in card._prereqs_widget.findChildren(QWidget):
        assert widget.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    card.close()


def test_task_card_drag_initiation_sets_task_mime_payload(qapp: QApplication) -> None:
    """Dragging a task card should produce the task-board MIME payload."""
    card = _make_card(qapp)
    _FakeDrag.instances.clear()

    start = QPoint(80, 24)
    end = QPoint(80 + QApplication.startDragDistance() + 8, 24)

    with patch("desktop.ui.tasks.task_board.QDrag", _FakeDrag):
        card.mousePressEvent(
            _mouse_event(
                QEvent.Type.MouseButtonPress,
                start,
                button=Qt.MouseButton.LeftButton,
                buttons=Qt.MouseButton.LeftButton,
            )
        )
        card.mouseMoveEvent(
            _mouse_event(
                QEvent.Type.MouseMove,
                end,
                buttons=Qt.MouseButton.LeftButton,
            )
        )

    assert len(_FakeDrag.instances) == 1
    drag = _FakeDrag.instances[0]
    assert drag.mime_data is not None
    assert bytes(drag.mime_data.data(TASK_MIME_TYPE)).decode() == "7:3"
    assert drag.hot_spot == start
    assert drag.exec_action == Qt.DropAction.MoveAction
    assert card._drag_start_pos is None

    card.close()


def test_task_card_click_toggles_expand_but_drag_does_not(qapp: QApplication) -> None:
    """Short clicks expand the card; drag gestures should not."""
    card = _make_card(qapp)
    click_pos = QPoint(80, 24)

    card.mousePressEvent(
        _mouse_event(
            QEvent.Type.MouseButtonPress,
            click_pos,
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.LeftButton,
        )
    )
    card.mouseReleaseEvent(
        _mouse_event(
            QEvent.Type.MouseButtonRelease,
            click_pos,
            button=Qt.MouseButton.LeftButton,
        )
    )
    assert card._expanded is True

    card._collapse_immediate()
    _FakeDrag.instances.clear()
    drag_end = QPoint(80 + QApplication.startDragDistance() + 8, 24)

    with patch("desktop.ui.tasks.task_board.QDrag", _FakeDrag):
        card.mousePressEvent(
            _mouse_event(
                QEvent.Type.MouseButtonPress,
                click_pos,
                button=Qt.MouseButton.LeftButton,
                buttons=Qt.MouseButton.LeftButton,
            )
        )
        card.mouseMoveEvent(
            _mouse_event(
                QEvent.Type.MouseMove,
                drag_end,
                buttons=Qt.MouseButton.LeftButton,
            )
        )
        card.mouseReleaseEvent(
            _mouse_event(
                QEvent.Type.MouseButtonRelease,
                drag_end,
                button=Qt.MouseButton.LeftButton,
            )
        )

    assert len(_FakeDrag.instances) == 1
    assert card._expanded is False

    card.close()


def test_project_column_drop_updates_task_project() -> None:
    """Dropping a task on a different column should move it."""
    column = ProjectColumn()
    column.project = Project(id=11, board_id=1, name="Destination")

    mime = QMimeData()
    mime.setData(TASK_MIME_TYPE, QByteArray(b"7:3"))
    event = MagicMock()
    event.mimeData.return_value = mime

    with patch("desktop.ui.tasks.task_board.update_task") as mock_update:
        column.dropEvent(event)

    mock_update.assert_called_once_with(7, project_id=11)
    event.acceptProposedAction.assert_called_once()


def test_project_column_same_column_drop() -> None:
    """Dropping a task on its own column should be a no-op."""
    column = ProjectColumn()
    column.project = Project(id=3, board_id=1, name="Source")

    mime = QMimeData()
    mime.setData(TASK_MIME_TYPE, QByteArray(b"7:3"))
    event = MagicMock()
    event.mimeData.return_value = mime

    with patch("desktop.ui.tasks.task_board.update_task") as mock_update:
        column.dropEvent(event)

    mock_update.assert_not_called()
    event.acceptProposedAction.assert_called_once()


def test_project_column_malformed_mime_drop() -> None:
    """Dropping a malformed MIME payload should be ignored safely."""
    column = ProjectColumn()
    column.project = Project(id=11, board_id=1, name="Destination")

    mime = QMimeData()
    mime.setData(TASK_MIME_TYPE, QByteArray(b"not-an-int:3"))
    event = MagicMock()
    event.mimeData.return_value = mime

    with patch("desktop.ui.tasks.task_board.update_task") as mock_update:
        column.dropEvent(event)

    mock_update.assert_not_called()
    event.ignore.assert_called_once()


def test_project_column_drag_leave_cleanup() -> None:
    """dragLeaveEvent should turn off the drag highlight."""
    column = ProjectColumn()
    with patch.object(column, "_highlight") as mock_highlight:
        event = MagicMock()
        column.dragLeaveEvent(event)
        mock_highlight.assert_called_once_with(False)


def test_checkbox_click_does_not_expand_card(qapp: QApplication) -> None:
    """Checkbox interaction should toggle completion without expanding the card."""
    card = _make_card(qapp)

    with patch("desktop.ui.tasks.task_board.complete_task", return_value=[]):
        card._check.click()
        qapp.processEvents()

    assert card._check.isChecked() is True
    assert card._expanded is False

    card.close()
