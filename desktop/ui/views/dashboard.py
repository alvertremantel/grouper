"""
dashboard.py — Home view showing a summary of active sessions and upcoming tasks.
"""

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...database import get_active_sessions
from ...database.boards import get_board_by_id
from ...database.connection import get_notifier
from ...database.events import list_events_for_range
from ...database.projects import get_project_by_id, get_starred_projects
from ...database.settings import get_setting, set_setting
from ...database.tasks import get_starred_tasks, get_tasks_by_board, get_tasks_with_due_dates
from ...models import Project, Task
from ..shared.base_card import BaseCard
from ..shared.widget_pool import WidgetPool
from ..shared.widgets import ElidedLabel, clear_layout
from ..time.activity_week import ActivityWeekStrip
from ..time.time_grid import FADE_HEIGHT, HOUR_HEIGHT, TimeGrid


def _compute_schedule_max_height() -> int:
    full_grid = HOUR_HEIGHT * 24 + FADE_HEIGHT * 2
    return int(full_grid * 0.75) + 100


_SCHEDULE_MAX_HEIGHT = _compute_schedule_max_height()

_AGENDA_VIEW_INDEX = 2  # CalView.AGENDA in calendar_view.py


class _SessionCard(BaseCard):
    """Reusable card for an active session."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = self._make_row()
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        self._name_lbl = ElidedLabel()
        self._name_lbl.setObjectName("titleLabelLarge")
        lay.addWidget(self._name_lbl)

        self._elapsed_lbl = QLabel()
        self._elapsed_lbl.setObjectName("accentLabel")
        self._elapsed_lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        lay.addWidget(self._elapsed_lbl, alignment=Qt.AlignmentFlag.AlignRight)

        self._paused_lbl = QLabel("⏸ PAUSED")
        self._paused_lbl.setObjectName("warningLabel")
        self._paused_lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        lay.addWidget(self._paused_lbl)

    def populate(self, session) -> None:
        self._name_lbl.setFullText(f"⏱  {session.activity_name}")
        self._elapsed_lbl.setText(session.format_duration())
        self._paused_lbl.setVisible(session.is_paused)

    def update_elapsed(self, text: str) -> None:
        self._elapsed_lbl.setText(text)


class _TaskCard(BaseCard):
    """Reusable card for an upcoming task."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = self._make_row()
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        self._title_lbl = ElidedLabel()
        self._title_lbl.setObjectName("titleLabel")
        lay.addWidget(self._title_lbl)

        self._proj_lbl = QLabel()
        self._proj_lbl.setObjectName("mutedLabel")
        self._proj_lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        lay.addWidget(self._proj_lbl)

        self._due_lbl = QLabel()
        self._due_lbl.setObjectName("warningLabel")
        self._due_lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        lay.addWidget(self._due_lbl, alignment=Qt.AlignmentFlag.AlignRight)

    def populate(self, task, project_name: str | None = None) -> None:
        self._title_lbl.setFullText(f"📋  {task.title}")
        if project_name:
            self._proj_lbl.setText(project_name)
            self._proj_lbl.setVisible(True)
        else:
            self._proj_lbl.setVisible(False)
        if task.due_date:
            self._due_lbl.setText(task.due_date.strftime("%b %d"))
            self._due_lbl.setVisible(True)
        else:
            self._due_lbl.setVisible(False)


class _TaskboxCard(BaseCard):
    """Dashboard card showing starred projects then tasks in a single column."""

    VISIBLE_LIMIT = 5

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, object_name="card")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._proj_expanded = False
        self._task_expanded = False
        self._all_projects: list[Project] = []
        self._all_tasks: list[Task] = []
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        # Content area (hidden when empty)
        self._content = QWidget()
        content_lay = QVBoxLayout(self._content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(8)

        # Projects section
        proj_header = QLabel("Projects")
        proj_header.setObjectName("mutedLabel")
        content_lay.addWidget(proj_header)
        self._proj_layout = QVBoxLayout()
        self._proj_layout.setSpacing(2)
        self._proj_layout.setContentsMargins(0, 0, 0, 0)
        content_lay.addLayout(self._proj_layout)
        self._proj_overflow = QPushButton()
        self._proj_overflow.setObjectName("linkButton")
        self._proj_overflow.setVisible(False)
        self._proj_overflow.clicked.connect(self._toggle_proj_expand)
        content_lay.addWidget(self._proj_overflow)

        # Tasks section
        task_header = QLabel("Tasks")
        task_header.setObjectName("mutedLabel")
        content_lay.addWidget(task_header)
        self._task_layout = QVBoxLayout()
        self._task_layout.setSpacing(2)
        self._task_layout.setContentsMargins(0, 0, 0, 0)
        content_lay.addLayout(self._task_layout)
        self._task_overflow = QPushButton()
        self._task_overflow.setObjectName("linkButton")
        self._task_overflow.setVisible(False)
        self._task_overflow.clicked.connect(self._toggle_task_expand)
        content_lay.addWidget(self._task_overflow)

        outer.addWidget(self._content)

        self._empty_lbl = QLabel("No starred items.")
        self._empty_lbl.setObjectName("mutedLabel")
        outer.addWidget(self._empty_lbl)

    def populate(self, projects: list[Project], tasks: list[Task]) -> None:
        self._all_projects = projects
        self._all_tasks = tasks
        self._proj_expanded = False
        self._task_expanded = False

        # Pre-fetch projects and boards to avoid N+1 queries
        project_ids = {t.project_id for t in tasks}
        self._projects_cache = {pid: get_project_by_id(pid) for pid in project_ids}
        board_ids = {p.board_id for p in list(self._projects_cache.values()) + list(projects) if p}
        self._boards_cache = {bid: get_board_by_id(bid) for bid in board_ids}

        has_items = bool(projects) or bool(tasks)
        self._content.setVisible(has_items)
        self._empty_lbl.setVisible(not has_items)

        self._render_projects()
        self._render_tasks()

    def _render_projects(self) -> None:
        clear_layout(self._proj_layout)
        limit = len(self._all_projects) if self._proj_expanded else self.VISIBLE_LIMIT
        for p in self._all_projects[:limit]:
            board = self._boards_cache.get(p.board_id)
            prefix = f"{board.name} > " if board else ""
            lbl = ElidedLabel()
            lbl.setFullText(f"{prefix}{p.name}")
            lbl.setObjectName("cardTitle")
            self._proj_layout.addWidget(lbl)

        hidden = len(self._all_projects) - self.VISIBLE_LIMIT
        if hidden > 0:
            self._proj_overflow.setVisible(True)
            if self._proj_expanded:
                self._proj_overflow.setText("\u25b2 show less")
            else:
                self._proj_overflow.setText(f"+ {hidden} more")
        else:
            self._proj_overflow.setVisible(False)

    def _render_tasks(self) -> None:
        clear_layout(self._task_layout)
        limit = len(self._all_tasks) if self._task_expanded else self.VISIBLE_LIMIT
        for t in self._all_tasks[:limit]:
            proj = self._projects_cache.get(t.project_id)
            if proj:
                board = self._boards_cache.get(proj.board_id)
                ctx = f"{board.name} > {proj.name}" if board else proj.name
                text = f"({ctx})  {t.title}"
            else:
                text = t.title
            lbl = ElidedLabel()
            lbl.setFullText(text)
            lbl.setObjectName("cardTitle")
            self._task_layout.addWidget(lbl)

        hidden = len(self._all_tasks) - self.VISIBLE_LIMIT
        if hidden > 0:
            self._task_overflow.setVisible(True)
            if self._task_expanded:
                self._task_overflow.setText("\u25b2 show less")
            else:
                self._task_overflow.setText(f"+ {hidden} more")
        else:
            self._task_overflow.setVisible(False)

    def _toggle_proj_expand(self) -> None:
        self._proj_expanded = not self._proj_expanded
        self._render_projects()

    def _toggle_task_expand(self) -> None:
        self._task_expanded = not self._task_expanded
        self._render_tasks()


class _ScheduleSection(QWidget):
    """Right-column widget: 2-day time grid with responsive compaction to 1 column."""

    navigate_clicked = Signal()

    _COMPACT_THRESHOLD = 480  # section width in px; below this show 1 column

    # Height cap: 75% of the full 24-hour grid + overhead for header/fade
    MAX_HEIGHT: int = _SCHEDULE_MAX_HEIGHT

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_compact = False
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(100)
        self._resize_timer.timeout.connect(self.refresh)
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Header row: "Schedule" + "Open Agenda >"
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header = QLabel("Schedule")
        header.setProperty("subheading", True)
        header_row.addWidget(header)
        header_row.addStretch()
        agenda_btn = QPushButton("Open Agenda \u203a")
        agenda_btn.setObjectName("linkButton")
        agenda_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        agenda_btn.clicked.connect(self.navigate_clicked.emit)
        header_row.addWidget(agenda_btn)
        lay.addLayout(header_row)

        # 2-day time grid (drops enabled, no slot-click event creation)
        self._grid = TimeGrid(
            columns=2, enable_drops=True, emit_slot_clicked=False, follow_now=True
        )
        self._grid.item_dropped.connect(self._on_drop)
        lay.addWidget(self._grid)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def refresh(self) -> None:
        """Fetch today + tomorrow events/tasks and push into the grid."""
        today = date.today()
        cols = 1 if self._is_compact else 2
        dates = [today + timedelta(days=i) for i in range(cols)]
        start_dt = datetime(today.year, today.month, today.day)
        end_dt = start_dt + timedelta(days=cols)

        events = list_events_for_range(start_dt, end_dt)
        tasks = get_tasks_with_due_dates(start_dt=start_dt, end_dt=end_dt)

        self._grid.set_visible_columns(cols)
        self._grid.set_data(dates, events, tasks)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.width() < self._COMPACT_THRESHOLD
        if compact != self._is_compact:
            self._is_compact = compact
            if not self._resize_timer.isActive():
                self._resize_timer.start()

    def _on_drop(self) -> None:
        self.refresh()


class DashboardView(QWidget):
    """Central dashboard giving a quick overview of everything."""

    navigate_requested = Signal(str, int)  # (view_name, sub_view_index)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build()
        self._schedule.navigate_clicked.connect(
            lambda: self.navigate_requested.emit("Calendar", _AGENDA_VIEW_INDEX)
        )
        self._dirty: bool = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(50)
        self._refresh_timer.timeout.connect(self.refresh)
        get_notifier().data_changed.connect(
            self._on_data_changed, Qt.ConnectionType.QueuedConnection
        )
        self.refresh()

        # Auto-refresh every 5 seconds for running timer elapsed display
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_update)
        self._timer.start(5000)

    def _on_data_changed(self) -> None:
        if self.isVisible():
            if not self._refresh_timer.isActive():
                self._refresh_timer.start()
        else:
            self._dirty = True

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._dirty:
            self._dirty = False
            self.refresh()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(20)

        heading = QLabel("Dashboard")
        heading.setProperty("heading", True)
        outer.addWidget(heading)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(16)
        self._scroll.setWidget(container)
        outer.addWidget(self._scroll)

        # Sessions section
        self._session_header = QLabel("Active Sessions (0)")
        self._session_header.setProperty("subheading", True)
        self._layout.addWidget(self._session_header)

        self._session_cards_layout = QVBoxLayout()
        self._session_cards_layout.setSpacing(6)
        self._session_cards_layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addLayout(self._session_cards_layout)

        self._session_pool: WidgetPool[_SessionCard] = WidgetPool(
            factory=_SessionCard,
            layout=self._session_cards_layout,
            initial=4,
        )
        self._no_sessions_lbl = QLabel("No active sessions.")
        self._no_sessions_lbl.setObjectName("mutedLabel")
        self._session_cards_layout.addWidget(self._no_sessions_lbl)

        # Horizontal divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        divider.setFixedHeight(1)
        self._layout.addWidget(divider)

        # Two-column layout: left (taskbox + upcoming) | right (reserved)
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(16)

        # Left column: Taskbox then Upcoming Tasks
        left_col = QVBoxLayout()
        left_col.setSpacing(8)

        self._taskbox_header = QLabel("Taskbox (0)")
        self._taskbox_header.setProperty("subheading", True)
        left_col.addWidget(self._taskbox_header)

        self._taskbox = _TaskboxCard()
        left_col.addWidget(self._taskbox)

        # Upcoming Tasks (below taskbox)
        self._task_header = QLabel("Upcoming Tasks (0)")
        self._task_header.setProperty("subheading", True)
        left_col.addWidget(self._task_header)

        self._task_cards_layout = QVBoxLayout()
        self._task_cards_layout.setSpacing(6)
        self._task_cards_layout.setContentsMargins(0, 0, 0, 0)
        left_col.addLayout(self._task_cards_layout)

        self._task_pool: WidgetPool[_TaskCard] = WidgetPool(
            factory=_TaskCard,
            layout=self._task_cards_layout,
            initial=8,
        )
        self._no_tasks_lbl = QLabel("No upcoming tasks with due dates.")
        self._no_tasks_lbl.setObjectName("mutedLabel")
        self._task_cards_layout.addWidget(self._no_tasks_lbl)

        # Board Tasks (from last-viewed task board)
        self._board_header = QLabel("Board Tasks")
        self._board_header.setProperty("subheading", True)
        left_col.addWidget(self._board_header)

        self._board_cards_layout = QVBoxLayout()
        self._board_cards_layout.setSpacing(6)
        self._board_cards_layout.setContentsMargins(0, 0, 0, 0)
        left_col.addLayout(self._board_cards_layout)

        self._board_pool: WidgetPool[_TaskCard] = WidgetPool(
            factory=_TaskCard,
            layout=self._board_cards_layout,
            initial=8,
        )
        self._no_board_lbl = QLabel("No board selected.")
        self._no_board_lbl.setObjectName("mutedLabel")
        self._board_cards_layout.addWidget(self._no_board_lbl)

        left_col.addStretch()

        left_widget = QWidget()
        left_widget.setLayout(left_col)
        bottom_row.addWidget(left_widget, stretch=1)

        # Right column: Schedule (2-day agenda grid)
        right_col = QVBoxLayout()
        right_col.setSpacing(8)

        self._schedule = _ScheduleSection()
        right_col.addWidget(self._schedule)

        right_widget = QWidget()
        right_widget.setLayout(right_col)
        right_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        bottom_row.addWidget(right_widget, stretch=1)

        # Cap schedule height so the grid's sizeHint doesn't bloat the row
        section_max = self._schedule.MAX_HEIGHT
        self._schedule.setMaximumHeight(section_max)

        # Wrap the two-column row in a widget so we can cap the row's total height.
        # Without this, the grid's sizeHint (~1192px) inflates the row and
        # Qt centers the maxHeight-capped right_widget vertically in the surplus.
        bottom_wrapper = QWidget()
        bottom_wrapper.setLayout(bottom_row)
        bottom_wrapper.setMaximumHeight(section_max)
        self._layout.addWidget(bottom_wrapper)

        # Horizontal divider below the two-column section
        divider2 = QFrame()
        divider2.setFrameShape(QFrame.Shape.HLine)
        divider2.setFrameShadow(QFrame.Shadow.Plain)
        divider2.setFixedHeight(1)
        self._layout.addWidget(divider2)

        # Activity week strip — session blocks on a 7-day hourly grid
        stored = get_setting("dashboard_activity_expanded", "1")
        self._activity_expanded: bool = stored != "0"
        prefix = "\u25bc" if self._activity_expanded else "\u25b6"
        self._activity_toggle = QPushButton(f"{prefix}  Logged Activity")
        self._activity_toggle.setObjectName("linkButton")
        self._activity_toggle.setProperty("subheading", True)
        self._activity_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._activity_toggle.clicked.connect(self._toggle_activity)
        self._layout.addWidget(self._activity_toggle)

        self._activity_week = ActivityWeekStrip()
        self._activity_week.setVisible(self._activity_expanded)
        self._layout.addWidget(self._activity_week)

        # Push all content to the top; absorb remaining viewport space
        self._layout.addStretch()

    def refresh(self) -> None:
        sessions = get_active_sessions()
        tasks = get_tasks_with_due_dates()[:8]
        starred_projects = get_starred_projects()
        starred_tasks = get_starred_tasks()
        self.setUpdatesEnabled(False)
        try:
            self._apply_sessions(sessions)
            self._apply_tasks(tasks)
            self._apply_board_tasks()
            self._taskbox_header.setText(f"Taskbox ({len(starred_projects) + len(starred_tasks)})")
            self._taskbox.populate(starred_projects, starred_tasks)
            self._schedule.refresh()
            self._activity_week.refresh()
        finally:
            self.setUpdatesEnabled(True)

    def _apply_sessions(self, sessions: list) -> None:
        self._session_header.setText(f"Active Sessions ({len(sessions)})")
        self._session_pool.begin_update()
        for s in sessions:
            card = self._session_pool.acquire()
            card.populate(s)
        self._no_sessions_lbl.setVisible(len(sessions) == 0)

    def _apply_tasks(self, tasks: list) -> None:
        self._task_header.setText(f"Upcoming Tasks ({len(tasks)})")
        # Pre-fetch projects to avoid N+1 queries
        project_ids = {t.project_id for t in tasks}
        projects = {pid: get_project_by_id(pid) for pid in project_ids}
        self._task_pool.begin_update()
        for t in tasks:
            card = self._task_pool.acquire()
            proj = projects.get(t.project_id)
            card.populate(t, project_name=proj.name if proj else None)
        self._no_tasks_lbl.setVisible(len(tasks) == 0)

    def _apply_board_tasks(self) -> None:
        stored = get_setting("active_board_id")
        if not stored:
            self._board_header.setText("Board Tasks")
            self._no_board_lbl.setVisible(True)
            self._board_pool.begin_update()
            return

        try:
            board_id = int(stored)
        except (ValueError, TypeError):
            self._board_header.setText("Board Tasks")
            self._no_board_lbl.setVisible(True)
            self._board_pool.begin_update()
            return
        board = get_board_by_id(board_id)
        board_name = board.name if board else "Board"

        tasks = [t for t in get_tasks_by_board(board_id) if not t.is_completed]
        self._board_header.setText(f"{board_name} ({len(tasks)})")
        self._no_board_lbl.setVisible(len(tasks) == 0)

        project_ids = {t.project_id for t in tasks}
        projects = {pid: get_project_by_id(pid) for pid in project_ids}

        self._board_pool.begin_update()
        for t in tasks[:12]:
            card = self._board_pool.acquire()
            proj = projects.get(t.project_id)
            card.populate(t, project_name=proj.name if proj else None)

    def _tick_update(self) -> None:
        """Lightweight timer tick: update only elapsed time labels in-place.
        Falls back to full refresh if session count changed."""
        sessions = get_active_sessions()
        if len(sessions) != self._session_pool.active_count:
            self.refresh()
            return
        for i, s in enumerate(sessions):
            card = self._session_pool.card_at(i)
            if card is not None:
                card.update_elapsed(s.format_duration())

    def _toggle_activity(self) -> None:
        """Collapse or expand the Logged Activity week strip.

        Preserves the toggle button's visual position in the viewport so
        the view doesn't jump when the ~1200px grid appears or disappears.
        """
        # Snapshot the toggle button's position relative to the viewport
        toggle_y_in_container = self._activity_toggle.y()
        scroll_pos = self._scroll.verticalScrollBar().value()
        visual_y = toggle_y_in_container - scroll_pos

        self._activity_expanded = not self._activity_expanded
        prefix = "\u25bc" if self._activity_expanded else "\u25b6"
        self._activity_toggle.setText(f"{prefix}  Logged Activity")
        self._activity_week.setVisible(self._activity_expanded)

        # Force layout recalc so toggle's new container-y is correct
        self._scroll.widget().updateGeometry()
        self._scroll.widget().layout().activate()

        # Restore: put the toggle back at the same visual position
        new_toggle_y = self._activity_toggle.y()
        self._scroll.verticalScrollBar().setValue(new_toggle_y - visual_y)

        set_setting("dashboard_activity_expanded", "1" if self._activity_expanded else "0")
