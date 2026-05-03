"""
task_list.py — Flat sortable/filterable task list view.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...database import list_projects
from ...database.boards import list_boards
from ...database.connection import get_notifier
from ...database.prerequisites import get_prerequisite_tasks, get_prerequisite_tasks_for_ids
from ...database.projects import get_project_by_id
from ...database.task_links import get_links_for_task_ids
from ...database.tasks import (
    complete_task,
    delete_task,
    get_tasks_by_board,
    uncomplete_task,
    update_task,
)
from ...models import Task, TaskLink
from ..shared.animated_stack import AnimatedViewStack, SlideAxis
from ..shared.icons import get_themed_icon
from ..shared.link_chips import LinkChipsRow
from ..shared.widget_pool import WidgetPool
from ..shared.widgets import (
    clear_layout,
    flash_checkbox_blocked,
    make_chip,
    reconnect,
    restyle_tree,
    truncate_title,
)
from .dialogs import ConfirmDialog
from .task_panel import TaskPanel


class _FlexListRow(QFrame):
    """Reusable row widget that can render as a project header or a task row."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Build the full task row layout (most complex case).
        # Header mode just shows/hides parts.
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(12, 8, 12, 8)
        self._lay.setSpacing(10)

        # --- Task row widgets ---
        self._left = QWidget()
        left_layout = QVBoxLayout(self._left)
        left_layout.setSpacing(4)
        left_layout.setContentsMargins(0, 0, 0, 0)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        self._check = QCheckBox()
        title_row.addWidget(self._check)

        self._title = QLabel()
        self._title.setWordWrap(True)
        self._title.setObjectName("cardTitle")
        title_row.addWidget(self._title, stretch=1)
        left_layout.addLayout(title_row)

        self._chips = LinkChipsRow(0)  # placeholder task id
        left_layout.addWidget(self._chips)

        self._meta_row_widget = QWidget()
        meta_row = QHBoxLayout(self._meta_row_widget)
        meta_row.setSpacing(8)
        meta_row.setContentsMargins(0, 0, 0, 0)

        self._proj_lbl = QLabel()
        self._proj_lbl.setObjectName("smallMuted")
        meta_row.addWidget(self._proj_lbl)

        self._pri_lbl = QLabel()
        meta_row.addWidget(self._pri_lbl)

        self._due_lbl = QLabel()
        self._due_lbl.setObjectName("warningLabel")
        meta_row.addWidget(self._due_lbl)

        meta_row.addStretch()
        left_layout.addWidget(self._meta_row_widget)

        self._tags_row = QHBoxLayout()
        self._tags_row.setSpacing(4)
        self._tags_widget = QWidget()
        self._tags_widget.setLayout(self._tags_row)
        left_layout.addWidget(self._tags_widget)

        self._prereqs_row = QHBoxLayout()
        self._prereqs_row.setSpacing(4)
        self._prereqs_widget = QWidget()
        self._prereqs_widget.setLayout(self._prereqs_row)
        left_layout.addWidget(self._prereqs_widget)

        self._lay.addWidget(self._left, stretch=1)

        self._edit_btn = QPushButton()
        self._edit_btn.setIcon(get_themed_icon("edit"))
        self._edit_btn.setFixedSize(28, 28)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setToolTip("Edit Task")
        self._edit_btn.setObjectName("iconButton")
        self._lay.addWidget(self._edit_btn)

        self._star_btn = QPushButton()
        self._star_btn.setIcon(get_themed_icon("star"))
        self._star_btn.setFixedSize(28, 28)
        self._star_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._star_btn.setToolTip("Toggle Star")
        self._star_btn.setObjectName("iconButton")
        self._lay.addWidget(self._star_btn)

        self._del_btn = QPushButton()
        self._del_btn.setIcon(get_themed_icon("trash"))
        self._del_btn.setFixedSize(28, 28)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setToolTip("Delete Task")
        self._del_btn.setObjectName("iconButton")
        self._lay.addWidget(self._del_btn)

        # --- Header-mode label (hidden by default) ---
        self._header_lbl = QLabel()
        self._header_lbl.setObjectName("mutedLabel")
        self._header_stretch: QWidget | None = None

        self._task_id: int | None = None
        self._view_ref: TaskListView | None = None
        self._task: Task | None = None

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            self._edit_btn.setIcon(get_themed_icon("edit"))
            icon_name = "star_filled" if self._task and self._task.is_starred else "star"
            self._star_btn.setIcon(get_themed_icon(icon_name))
            self._del_btn.setIcon(get_themed_icon("trash"))

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self._view_ref and self._task:
            self._view_ref._edit_task(self._task)
        else:
            super().mouseDoubleClickEvent(event)

    def populate_as_header(self, name: str) -> None:
        self.setObjectName("projectHeader")
        self._left.setVisible(False)
        self._edit_btn.setVisible(False)
        self._star_btn.setVisible(False)
        self._del_btn.setVisible(False)
        self._tags_widget.setVisible(False)
        self._prereqs_widget.setVisible(False)
        self._task = None
        # Show only the header label inside the layout
        if self._lay.indexOf(self._header_lbl) < 0:
            self._lay.insertWidget(0, self._header_lbl)
            if self._header_stretch is None:
                self._header_stretch = QWidget()
            self._lay.addWidget(self._header_stretch)
        self._header_lbl.setText(name)
        self._header_lbl.setVisible(True)
        restyle_tree(self)

    def populate_as_task(
        self,
        task: Task,
        show_project_name: bool,
        view: TaskListView,
        links: list[TaskLink] | None = None,
        prereq_tasks: list[Task] | None = None,
    ) -> None:
        if task.id is None:
            return
        task_id: int = task.id
        self._task_id = task_id
        self.setObjectName("card")
        self._view_ref = view
        self._task = task

        # Hide header mode if previously used
        self._header_lbl.setVisible(False)
        self._left.setVisible(True)
        self._edit_btn.setVisible(True)
        self._star_btn.setVisible(True)
        self._del_btn.setVisible(True)

        # Update title
        self._title.setText(task.title)
        completed_prop = task.is_completed
        self._title.setProperty("completed", completed_prop)
        self._title.style().unpolish(self._title)
        self._title.style().polish(self._title)

        # Update checkbox (block signals to avoid triggering toggle)
        self._check.blockSignals(True)
        self._check.setChecked(task.is_completed)
        self._check.blockSignals(False)

        # Reconnect check signal
        reconnect(self._check.toggled, lambda c, tid=task_id: view._toggle(tid, c))

        # Update chips — pass pre-loaded links if available
        self._chips.set_task_id(task_id, links)

        # Project label
        if show_project_name:
            proj = get_project_by_id(task.project_id)
            self._proj_lbl.setText(proj.name if proj else "")
            self._proj_lbl.setVisible(bool(proj))
        else:
            self._proj_lbl.setVisible(False)

        # Priority label
        if task.priority > 0:
            self._pri_lbl.setText(f"P{task.priority}")
            self._pri_lbl.setObjectName(f"priority{task.priority}")
            self._pri_lbl.setVisible(True)
        else:
            self._pri_lbl.setVisible(False)

        # Due date label
        if task.due_date:
            self._due_lbl.setText(task.due_date.strftime("%b %d"))
            self._due_lbl.setVisible(True)
        else:
            self._due_lbl.setVisible(False)

        # Tags
        clear_layout(self._tags_row)
        if task.tags:
            for tag_name in task.tags:
                self._tags_row.addWidget(make_chip(tag_name))
            self._tags_row.addStretch()
            self._tags_widget.setVisible(True)
        else:
            self._tags_widget.setVisible(False)

        # Prerequisites — use pre-loaded data if available, else query
        clear_layout(self._prereqs_row)
        if prereq_tasks is None:
            prereq_tasks = get_prerequisite_tasks(task_id)
        if prereq_tasks:
            for pt in prereq_tasks:
                text = f"{truncate_title(pt.title)} → this"
                self._prereqs_row.addWidget(make_chip(text, strikethrough=pt.is_completed))
            self._prereqs_row.addStretch()
            self._prereqs_widget.setVisible(True)
        else:
            self._prereqs_widget.setVisible(False)

        # Set star icon state
        icon_name = "star_filled" if task.is_starred else "star"
        self._star_btn.setIcon(get_themed_icon(icon_name))

        # Reconnect edit / star / delete buttons
        reconnect(self._edit_btn.clicked, lambda: view._edit_task(task))
        reconnect(self._star_btn.clicked, lambda: view._toggle_star(task))
        reconnect(self._del_btn.clicked, lambda: view._delete_task(task_id))

        # Force style refresh for objectName change — must include children
        # so descendant selectors like #card QWidget { transparent } apply.
        restyle_tree(self)


class TaskListView(QWidget):
    """Flat task list with board filter and optional project grouping."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()
        self._dirty: bool = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(50)
        self._refresh_timer.timeout.connect(self.refresh)
        get_notifier().data_changed.connect(
            self._on_data_changed, Qt.ConnectionType.QueuedConnection
        )
        self.refresh()

    def _on_data_changed(self) -> None:
        if self.isVisible():
            if not self._refresh_timer.isActive():
                self._refresh_timer.start()
        else:
            self._dirty = True

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._dirty:
            self._dirty = False
            self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._inner_stack = AnimatedViewStack(axis=SlideAxis.HORIZONTAL)
        root.addWidget(self._inner_stack)

        # -- Page 0: list content ----------------------------------------------
        list_page = QWidget()
        outer = QVBoxLayout(list_page)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Task List")
        title.setProperty("heading", True)
        header.addWidget(title)
        header.addStretch()

        add_btn = QPushButton("+ New Task")
        add_btn.setProperty("primary", True)
        add_btn.clicked.connect(self._add_task)
        header.addWidget(add_btn)
        outer.addLayout(header)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Board:"))
        self._board_filter = QComboBox()
        self._board_filter.currentIndexChanged.connect(lambda _: self.refresh())
        filter_row.addWidget(self._board_filter)

        self._show_completed = QCheckBox("Show completed")
        self._show_completed.toggled.connect(lambda _: self.refresh())
        filter_row.addWidget(self._show_completed)

        self._group_by_project = QCheckBox("Group by project")
        self._group_by_project.toggled.connect(lambda _: self.refresh())
        filter_row.addWidget(self._group_by_project)

        filter_row.addStretch()
        outer.addLayout(filter_row)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._list_container)
        outer.addWidget(self._scroll)

        # Pre-allocate widget pool
        self._row_pool: WidgetPool[_FlexListRow] = WidgetPool(
            factory=_FlexListRow,
            layout=self._list_layout,
            initial=16,
        )
        self._empty_lbl = QLabel("No tasks to show.")
        self._empty_lbl.setObjectName("emptyMessage")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_layout.addWidget(self._empty_lbl)

        self._inner_stack.addWidget(list_page)  # index 0

        # -- Page 1: task panel ------------------------------------------------
        self._task_panel = TaskPanel()
        self._task_panel.closed.connect(self._close_panel)
        self._task_panel.task_saved.connect(self._on_task_saved)
        self._inner_stack.addWidget(self._task_panel)  # index 1

    def refresh(self) -> None:
        current_bid = self._board_filter.currentData()
        self._board_filter.blockSignals(True)
        self._board_filter.clear()
        boards = list_boards()
        for b in boards:
            self._board_filter.addItem(b.name, b.id)
            if b.id == current_bid:
                self._board_filter.setCurrentIndex(self._board_filter.count() - 1)
        self._board_filter.blockSignals(False)

        bid_raw = self._board_filter.currentData()
        show_done = self._show_completed.isChecked()
        group_by_project = self._group_by_project.isChecked()

        if bid_raw is None:
            if not boards:
                self._row_pool.begin_update()
                self._empty_lbl.setText("No boards available.")
                self._empty_lbl.setVisible(True)
                return
            bid_raw = boards[0].id

        bid: int = bid_raw
        all_tasks = get_tasks_by_board(bid)
        all_tasks.sort(key=lambda t: (t.is_completed, t.priority, t.created_at or datetime.min))
        visible_tasks = [t for t in all_tasks if show_done or not t.is_completed]

        # Batch-load links and prerequisites for all visible tasks (2 queries
        # instead of 2*N per-row queries).
        visible_ids = [t.id for t in visible_tasks if t.id is not None]
        links_map = get_links_for_task_ids(visible_ids)
        prereqs_map = get_prerequisite_tasks_for_ids(visible_ids)

        v_bar = self._scroll.verticalScrollBar()
        v_pos = v_bar.value()
        self.setUpdatesEnabled(False)
        try:
            self._row_pool.begin_update()
            if not visible_tasks:
                self._empty_lbl.setText("No tasks to show.")
                self._empty_lbl.setVisible(True)
                return
            self._empty_lbl.setVisible(False)

            if group_by_project:
                self._render_grouped(visible_tasks, links_map, prereqs_map)
            else:
                self._render_flat(visible_tasks, links_map, prereqs_map)
        finally:
            self.setUpdatesEnabled(True)
            v_bar.setValue(v_pos)

    def _render_flat(
        self,
        tasks: list[Task],
        links_map: dict[int, list[TaskLink]],
        prereqs_map: dict[int, list[Task]],
    ) -> None:
        for t in tasks:
            row = self._row_pool.acquire()
            task_links = links_map.get(t.id, []) if t.id is not None else None
            task_prereqs = prereqs_map.get(t.id, []) if t.id is not None else None
            row.populate_as_task(
                t,
                show_project_name=True,
                view=self,
                links=task_links,
                prereq_tasks=task_prereqs,
            )

    def _render_grouped(
        self,
        tasks: list[Task],
        links_map: dict[int, list[TaskLink]],
        prereqs_map: dict[int, list[Task]],
    ) -> None:
        project_tasks: dict[int, list[Task]] = {}
        project_order: list[int] = []
        for t in tasks:
            if t.project_id not in project_tasks:
                project_tasks[t.project_id] = []
                project_order.append(t.project_id)
            project_tasks[t.project_id].append(t)

        for pid in project_order:
            proj = get_project_by_id(pid)
            if proj:
                header_row = self._row_pool.acquire()
                header_row.populate_as_header(proj.name)

            for t in project_tasks[pid]:
                row = self._row_pool.acquire()
                task_links = links_map.get(t.id, []) if t.id is not None else None
                task_prereqs = prereqs_map.get(t.id, []) if t.id is not None else None
                row.populate_as_task(
                    t,
                    show_project_name=False,
                    view=self,
                    links=task_links,
                    prereq_tasks=task_prereqs,
                )

    def _edit_task(self, task: Task) -> None:
        if task.id is None:
            return
        board_id = self._board_filter.currentData()
        if board_id is None:
            return
        self._inner_stack.setCurrentIndex(1)  # start slide animation immediately
        # Defer DB-heavy load to next event loop iteration so the first
        # animation frame renders without blocking.
        QTimer.singleShot(0, lambda t=task, b=board_id: self._task_panel.load_for_edit(t, b))

    def _delete_task(self, task_id: int) -> None:
        dlg = ConfirmDialog("Delete Task", "Permanently delete this task?", self.window())
        if dlg.exec():
            delete_task(task_id)
            self.refresh()

    def _toggle_star(self, task: Task) -> None:
        if task.id is None:
            return
        new_val = 0 if task.is_starred else 1
        update_task(task.id, is_starred=new_val)
        self.refresh()

    def _toggle(self, task_id: int, checked: bool) -> None:
        if checked:
            blockers = complete_task(task_id)
            if blockers:
                # Blocked — refresh will reset the checkbox; flash the row
                self.refresh()
                self._flash_blocked(task_id, blockers)
                return
        else:
            uncomplete_task(task_id)
        self.refresh()

    def _flash_blocked(self, task_id: int, blockers: list) -> None:
        """Flash the checkbox red for the blocked task row."""
        for child in self._list_container.findChildren(_FlexListRow):
            if child._task_id == task_id:
                names = ", ".join(b.title for b in blockers)
                flash_checkbox_blocked(child._check, names)
                break

    def _add_task(self) -> None:
        board_id = self._board_filter.currentData()
        if board_id is None:
            return
        projects = list_projects()
        if not projects:
            return
        self._task_panel.load_for_create(projects, board_id)
        self._inner_stack.setCurrentIndex(1)

    # -- task panel integration ------------------------------------------------

    def _close_panel(self) -> None:
        """Slide back to the list view."""
        self._inner_stack.setCurrentIndex(0)

    def _on_task_saved(self) -> None:
        """Refresh after a task was created or updated via the panel."""
        self.refresh()
