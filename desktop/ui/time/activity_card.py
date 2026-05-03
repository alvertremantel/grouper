"""activity_card.py — Activity selection components (drag-and-drop cards + quadrants)."""

from typing import Literal

from PySide6.QtCore import QByteArray, QEvent, QMimeData, Qt, Signal
from PySide6.QtGui import QDrag, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...config import get_config
from ...database import (
    add_activity_group,
    get_activities_by_group,
    remove_activity_group,
)
from ...styles import theme_colors
from ..shared.base_card import BaseCard
from ..shared.icons import get_icon
from ..shared.widget_pool import WidgetPool
from ..shared.widgets import reconnect

# -- Drag-and-drop constants ------------------------------------------------

ACTIVITY_MOVE_MIME = "application/x-grouper-activity-move"
ACTIVITY_COPY_MIME = "application/x-grouper-activity-copy"

# -- Types -------------------------------------------------------------------

GridMode = Literal["2x2", "1x2"]


def _find_parent_quadrant(widget: QWidget | None) -> "ActivityQuadrant | None":
    """Walk up the widget tree to find the containing ActivityQuadrant."""
    w: QWidget | None = widget
    while w is not None:
        if isinstance(w, ActivityQuadrant):
            return w
        parent = w.parent()
        w = parent if isinstance(parent, QWidget) else None
    return None


class DragHandleButton(QPushButton):
    """A button that initiates a drag operation when click-dragged."""

    def __init__(
        self,
        activity_name: str,
        activity_id: int,
        mime_type: str,
        icon: QIcon,
        tooltip: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._activity_name = activity_name
        self._activity_id = activity_id
        self._mime_type = mime_type
        self._drag_start_pos = None
        self.setIcon(icon)
        self.setFixedSize(24, 24)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setObjectName("dragHandle")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos is None:
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        distance = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
        if distance < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime = QMimeData()
        payload = f"{self._activity_id}:{self._activity_name}"
        mime.setData(self._mime_type, QByteArray(payload.encode()))
        drag.setMimeData(mime)

        # Ghost pixmap from parent ActivityCard
        card = self.parent()
        if not isinstance(card, QWidget):
            return
        pixmap = QPixmap(card.size())
        card.render(pixmap)
        semi = QPixmap(pixmap.size())
        semi.fill(Qt.GlobalColor.transparent)
        painter = QPainter(semi)
        painter.setOpacity(0.7)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        drag.setPixmap(semi)
        drag.setHotSpot(self._drag_start_pos)

        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        drag.exec(Qt.DropAction.MoveAction)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start_pos = None


class ActivityCard(BaseCard):
    """A clickable card representing a single activity in a quadrant."""

    clicked = Signal(str)

    def __init__(self, activity_name: str, activity_id: int, parent: QWidget | None = None):
        super().__init__(parent, object_name="activityCard")
        self._activity_name = activity_name
        self._activity_id = activity_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click to start session")
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        self._label = QLabel(self._activity_name)
        self._label.setObjectName("activityCardLabel")
        lay.addWidget(self._label, stretch=1)

        stroke = theme_colors(get_config().theme)["icon_stroke"]
        move_btn = DragHandleButton(
            self._activity_name,
            self._activity_id,
            ACTIVITY_MOVE_MIME,
            get_icon("move", stroke),
            "Drag to move to another group",
            parent=self,
        )
        lay.addWidget(move_btn)

        copy_btn = DragHandleButton(
            self._activity_name,
            self._activity_id,
            ACTIVITY_COPY_MIME,
            get_icon("copy", stroke),
            "Drag to copy to another group",
            parent=self,
        )
        lay.addWidget(copy_btn)

    def populate(self, activity_name: str, activity_id: int) -> None:
        """Repopulate this card with new activity data for pooled reuse."""
        self._activity_name = activity_name
        self._activity_id = activity_id
        self._label.setText(activity_name)
        self._refresh_icons()
        for btn in self.findChildren(DragHandleButton):
            btn._activity_name = activity_name
            btn._activity_id = activity_id

    def _refresh_icons(self) -> None:
        """Update drag-handle icon colors to match the current theme."""
        stroke = theme_colors(get_config().theme)["icon_stroke"]
        for btn in self.findChildren(DragHandleButton):
            if btn._mime_type == ACTIVITY_MOVE_MIME:
                btn.setIcon(get_icon("move", stroke))
            elif btn._mime_type == ACTIVITY_COPY_MIME:
                btn.setIcon(get_icon("copy", stroke))

    def changeEvent(self, event: QEvent) -> None:  # type: ignore[override]
        """Re-color icons when the theme (stylesheet) changes."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            self._refresh_icons()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._activity_name)
        super().mousePressEvent(event)


class ActivityQuadrant(QFrame):
    """A single quadrant with group selector and activity cards."""

    activity_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("activityQuadrant")
        self.setAcceptDrops(True)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.group_selector = QComboBox()
        self.group_selector.setObjectName("quadrantGroupSelector")
        self.group_selector.addItem("— Select Group —", None)
        self.group_selector.currentIndexChanged.connect(self._on_group_changed)
        layout.addWidget(self.group_selector)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("activityCardScroll")
        self._card_container = QWidget()
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.setSpacing(6)
        self._card_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._card_container)
        layout.addWidget(scroll)

        # Widget pool — pool widgets are addWidget()ed before the hint/stretch
        self._activity_pool: WidgetPool[ActivityCard] = WidgetPool(
            factory=lambda: ActivityCard("", 0),
            layout=self._card_layout,
            initial=8,
        )

        self._hint_lbl = QLabel("Select a group above")
        self._hint_lbl.setObjectName("activityHintLabel")
        self._hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_lbl.setVisible(True)
        self._card_layout.addWidget(self._hint_lbl)

        self._empty_activity_lbl = QLabel("No activities in this group")
        self._empty_activity_lbl.setObjectName("activityHintLabel")
        self._empty_activity_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_activity_lbl.setVisible(False)
        self._card_layout.addWidget(self._empty_activity_lbl)

    def _on_group_changed(self, index: int) -> None:
        group_name = self.group_selector.currentData()
        if group_name is None:
            self._activity_pool.begin_update()
            self._hint_lbl.setVisible(True)
            self._empty_activity_lbl.setVisible(False)
        else:
            self._hint_lbl.setVisible(False)
            self._refresh_activities(group_name)

    def _refresh_activities(self, group_name: str) -> None:
        activities = get_activities_by_group(group_name)

        self._activity_pool.begin_update()
        for a in activities:
            card = self._activity_pool.acquire()
            card.populate(a.name, a.id or 0)
            reconnect(card.clicked, self.activity_selected.emit)

        self._empty_activity_lbl.setVisible(len(activities) == 0)
        self._hint_lbl.setVisible(False)

    def refresh_groups(self, groups: list[str]):
        current_data = self.group_selector.currentData()
        self.group_selector.clear()
        self.group_selector.addItem("— Select Group —", None)
        for g in groups:
            self.group_selector.addItem(g, g)

        if current_data and current_data in groups:
            idx = self.group_selector.findData(current_data)
            if idx >= 0:
                self.group_selector.setCurrentIndex(idx)
        elif current_data:
            self.group_selector.addItem(current_data, current_data)
            idx = self.group_selector.findData(current_data)
            self.group_selector.setCurrentIndex(idx)

    # -- Drag-and-drop (drop target) ----------------------------------------

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat(ACTIVITY_MOVE_MIME) or mime.hasFormat(ACTIVITY_COPY_MIME):
            event.acceptProposedAction()
            self._highlight(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat(ACTIVITY_MOVE_MIME) or mime.hasFormat(ACTIVITY_COPY_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._highlight(False)

    def dropEvent(self, event):
        self._highlight(False)
        mime = event.mimeData()
        is_move = mime.hasFormat(ACTIVITY_MOVE_MIME)
        is_copy = mime.hasFormat(ACTIVITY_COPY_MIME)
        if not (is_move or is_copy):
            event.ignore()
            return

        mime_type = ACTIVITY_MOVE_MIME if is_move else ACTIVITY_COPY_MIME
        try:
            payload = mime.data(mime_type).data().decode()
            activity_id, _activity_name = payload.split(":", 1)
            activity_id = int(activity_id)
        except (ValueError, UnicodeDecodeError):
            event.ignore()
            return

        target_group = self.group_selector.currentData()
        if target_group is None:
            event.ignore()
            return

        # Find source quadrant to get source group
        source_widget = event.source()
        source_quadrant = _find_parent_quadrant(source_widget)
        source_group = source_quadrant.group_selector.currentData() if source_quadrant else None

        if source_group == target_group:
            event.ignore()
            return

        # Perform the operation
        add_activity_group(activity_id, target_group)
        if is_move and source_group:
            remove_activity_group(activity_id, source_group)

        # Refresh all quadrants via the TimeTrackerView
        tracker = self.window().findChild(QWidget, "timeTrackerView")
        if tracker is not None:
            refresh = getattr(tracker, "refresh", None)
            if refresh is not None:
                refresh()

        event.acceptProposedAction()

    def _highlight(self, active: bool):
        self.setProperty("drag", bool(active))
        self.style().unpolish(self)
        self.style().polish(self)
