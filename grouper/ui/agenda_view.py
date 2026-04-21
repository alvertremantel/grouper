"""
agenda_view.py — Two-pane agenda planning view.

Left pane: Taskbox — unscheduled tasks from starred projects and individually
starred tasks, grouped separately, each draggable onto the schedule.

Right pane: Schedule — 3-day TimeGrid (with drops enabled) where tasks can be
dropped onto specific time slots to schedule them.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from itertools import groupby

from PySide6.QtCore import QByteArray, QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..config import get_config
from ..database.boards import get_board_by_id
from ..database.events import list_events_for_range
from ..database.projects import get_project_by_id
from ..database.tasks import (
    get_tasks_with_due_dates,
    get_unscheduled_starred_tasks,
    get_unscheduled_tasks_for_starred_projects,
)
from ..models import Task
from ..styles import theme_colors
from .mime_types import TIMELINE_TASK_MIME
from .time_grid import TimeGrid
from .widgets import clear_layout

# ---------------------------------------------------------------------------
# Draggable task card for the taskbox
# ---------------------------------------------------------------------------


class _TaskboxItem(QFrame):
    """A single draggable task row in the agenda taskbox."""

    def __init__(self, task: Task, context: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._task = task
        self._drag_start_pos: QPoint | None = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        colors = theme_colors(get_config().theme)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(1)

        title_lbl = QLabel(task.title)
        title_lbl.setStyleSheet(
            f"color: {colors['text']}; font-size: 12px; font-weight: 500; background: transparent;"
        )
        title_lbl.setWordWrap(False)
        lay.addWidget(title_lbl)

        if context:
            ctx_lbl = QLabel(context)
            ctx_lbl.setStyleSheet(
                f"color: {colors['text-muted']}; font-size: 10px; background: transparent;"
            )
            ctx_lbl.setWordWrap(False)
            lay.addWidget(ctx_lbl)

        self.setStyleSheet(
            f"_TaskboxItem {{ background: {colors['bg-secondary']}; "
            f"border-radius: 6px; border: 1px solid {colors['border']}; }}"
        )

    # -- Drag source ----------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_start_pos is not None
            and (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(TIMELINE_TASK_MIME, QByteArray(str(self._task.id).encode()))
            drag.setMimeData(mime)

            # Render pixmap with accent border for visual emphasis
            colors = theme_colors(get_config().theme)
            pixmap = QPixmap(self.size())
            self.render(pixmap)
            painter = QPainter(pixmap)
            accent = QColor(colors["accent"])
            painter.setPen(QPen(accent, 2))
            painter.drawRoundedRect(1, 1, pixmap.width() - 2, pixmap.height() - 2, 6, 6)
            painter.end()
            pixmap.setDevicePixelRatio(self.devicePixelRatioF())
            drag.setPixmap(pixmap)
            drag.setHotSpot(event.position().toPoint())
            drag.exec(Qt.DropAction.MoveAction)
            self._drag_start_pos = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# Agenda taskbox (left pane)
# ---------------------------------------------------------------------------


class _AgendaTaskbox(QWidget):
    """Left pane showing unscheduled tasks from starred projects and starred tasks."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(300)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 8, 0)
        outer.setSpacing(0)

        heading = QLabel("Taskbox")
        heading.setObjectName("sectionHeading")
        heading.setStyleSheet("font-size: 14px; font-weight: 700; padding: 4px 0;")
        outer.addWidget(heading)

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        inner = QWidget()
        self._inner_lay = QVBoxLayout(inner)
        self._inner_lay.setContentsMargins(0, 0, 0, 0)
        self._inner_lay.setSpacing(0)

        # Section 1: Project Tasks
        self._proj_header = QLabel("Project Tasks")
        self._proj_header.setStyleSheet("font-size: 13px; font-weight: 600; padding: 6px 0 2px 0;")
        self._inner_lay.addWidget(self._proj_header)

        self._proj_layout = QVBoxLayout()
        self._proj_layout.setContentsMargins(0, 0, 0, 0)
        self._proj_layout.setSpacing(4)
        self._inner_lay.addLayout(self._proj_layout)

        # Section 2: Starred Tasks
        self._star_header = QLabel("Starred Tasks")
        self._star_header.setStyleSheet("font-size: 13px; font-weight: 600; padding: 10px 0 2px 0;")
        self._inner_lay.addWidget(self._star_header)

        self._star_layout = QVBoxLayout()
        self._star_layout.setContentsMargins(0, 0, 0, 0)
        self._star_layout.setSpacing(4)
        self._inner_lay.addLayout(self._star_layout)

        self._inner_lay.addStretch()

        # Empty state
        self._empty_lbl = QLabel("No unscheduled tasks.\nStar projects or tasks to see them here.")
        self._empty_lbl.setObjectName("emptyCalendar")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setWordWrap(True)
        self._inner_lay.addWidget(self._empty_lbl)

        scroll.setWidget(inner)

    def refresh(self) -> None:
        proj_tasks = get_unscheduled_tasks_for_starred_projects()
        starred_tasks = get_unscheduled_starred_tasks()

        has_items = bool(proj_tasks) or bool(starred_tasks)
        self._proj_header.setVisible(bool(proj_tasks))
        self._star_header.setVisible(bool(starred_tasks))
        self._empty_lbl.setVisible(not has_items)

        # Pre-fetch projects and boards to avoid N+1 queries
        all_tasks = list(proj_tasks) + list(starred_tasks)
        project_ids = {t.project_id for t in all_tasks}
        projects = {pid: get_project_by_id(pid) for pid in project_ids}
        board_ids = {p.board_id for p in projects.values() if p}
        boards = {bid: get_board_by_id(bid) for bid in board_ids}

        # -- Section 1: Project Tasks (grouped by project) --
        clear_layout(self._proj_layout)
        for project_id, tasks_iter in groupby(proj_tasks, key=lambda t: t.project_id):
            tasks = list(tasks_iter)
            proj = projects.get(project_id)
            if proj:
                board = boards.get(proj.board_id)
                prefix = f"{board.name} > " if board else ""
                proj_lbl = QLabel(f"{prefix}{proj.name}")
                colors = theme_colors(get_config().theme)
                proj_lbl.setStyleSheet(
                    f"color: {colors['text-muted']}; font-size: 11px; "
                    f"font-weight: 600; padding: 4px 0 1px 2px; background: transparent;"
                )
                self._proj_layout.addWidget(proj_lbl)

            for task in tasks:
                item = _TaskboxItem(task)
                self._proj_layout.addWidget(item)

        # -- Section 2: Starred Tasks --
        clear_layout(self._star_layout)
        for task in starred_tasks:
            proj = projects.get(task.project_id)
            ctx = ""
            if proj:
                board = boards.get(proj.board_id)
                ctx = f"{board.name} > {proj.name}" if board else proj.name
            item = _TaskboxItem(task, context=ctx)
            self._star_layout.addWidget(item)


# ---------------------------------------------------------------------------
# Main agenda view
# ---------------------------------------------------------------------------


class AgendaView(QWidget):
    """Two-pane agenda: Taskbox (left) + 3-day schedule grid (right)."""

    event_edit_requested = Signal(object)  # Event

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._taskbox = _AgendaTaskbox()
        lay.addWidget(self._taskbox)

        self._grid = TimeGrid(columns=3, enable_drops=True, emit_slot_clicked=False)
        self._grid.event_clicked.connect(self.event_edit_requested.emit)
        self._grid.item_dropped.connect(self._on_item_dropped)
        lay.addWidget(self._grid, stretch=1)

        self._anchor: date = date.today()

    def set_dates(self, anchor: date) -> None:
        self._anchor = anchor

    def refresh(self) -> None:
        dates = [self._anchor + timedelta(days=i) for i in range(3)]
        start_dt = datetime(dates[0].year, dates[0].month, dates[0].day)
        end_dt = start_dt + timedelta(days=3)

        events = list_events_for_range(start_dt, end_dt)
        tasks = get_tasks_with_due_dates(start_dt=start_dt, end_dt=end_dt)

        self._grid.set_data(dates, events, tasks)
        self._taskbox.refresh()

    def _on_item_dropped(self) -> None:
        self.refresh()
