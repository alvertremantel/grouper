"""
task_board.py — Kanban-style board view for tasks.

Shows columns per project with task cards.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QEvent,
    QMimeData,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QDrag, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..config import get_config
from ..database import (
    create_board,
    get_or_create_default_board,
    list_boards,
    list_projects,
    rename_board,
)
from ..database.connection import get_notifier
from ..database.prerequisites import get_prerequisite_tasks, get_prerequisite_tasks_for_ids
from ..database.projects import update_project
from ..database.settings import get_setting, set_setting
from ..database.task_links import get_links_for_task_ids
from ..database.tasks import (
    complete_task,
    create_task,
    delete_task,
    get_tasks,
    uncomplete_task,
    update_task,
)
from ..models import Project, Task, TaskLink
from .animated_stack import AnimatedViewStack, SlideAxis
from .dialogs import (
    AddBoardDialog,
    ConfirmDialog,
    CreateProjectDialog,
    EditBoardDialog,
    EditProjectDialog,
)
from .icons import get_icon, get_themed_icon
from .link_chips import LinkChipsRow
from .task_panel import TaskPanel
from .widget_pool import WidgetPool
from .widgets import clear_layout, flash_checkbox_blocked, make_chip, truncate_title

logger = logging.getLogger(__name__)

COMPLETED_LIMIT = 20  # max completed tasks shown per column when filter is on

TASK_MIME_TYPE = "application/x-grouper-task"


class TaskCard(QFrame):
    """A reusable task card within a board column."""

    _currently_expanded: ClassVar[TaskCard | None] = None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.task: Task | None = None
        self._drag_start_pos = None
        self._expanded: bool = False
        self._expand_anim: QPropertyAnimation | None = None
        self._collapse_anim: QPropertyAnimation | None = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setObjectName("card")
        self._build()

    def _build(self) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        left_layout = QVBoxLayout()
        left_layout.setSpacing(4)
        left_layout.setContentsMargins(0, 0, 0, 0)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        self._check = QCheckBox()
        self._check.toggled.connect(self._on_toggle)
        title_row.addWidget(self._check)

        self._title_lbl = QLabel()
        self._title_lbl.setWordWrap(True)
        self._title_lbl.setObjectName("cardTitle")
        self._set_drag_passthrough(self._title_lbl)
        title_row.addWidget(self._title_lbl, stretch=1)

        left_layout.addLayout(title_row)

        self._chips = LinkChipsRow(0)  # placeholder; set_task_id called in populate()
        left_layout.addWidget(self._chips)

        self._tags_row = QHBoxLayout()
        self._tags_row.setSpacing(4)
        self._tags_widget = QWidget()
        self._tags_widget.setLayout(self._tags_row)
        self._set_drag_passthrough(self._tags_widget)
        left_layout.addWidget(self._tags_widget)

        self._prereqs_row = QHBoxLayout()
        self._prereqs_row.setSpacing(4)
        self._prereqs_widget = QWidget()
        self._prereqs_widget.setLayout(self._prereqs_row)
        self._set_drag_passthrough(self._prereqs_widget)
        left_layout.addWidget(self._prereqs_widget)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)

        self._pri_lbl = QLabel()
        self._set_drag_passthrough(self._pri_lbl)
        meta_row.addWidget(self._pri_lbl)

        self._due_lbl = QLabel()
        self._due_lbl.setObjectName("warningLabel")
        self._set_drag_passthrough(self._due_lbl)
        meta_row.addWidget(self._due_lbl)

        meta_row.addStretch()
        left_layout.addLayout(meta_row)

        # Action row (hidden by default, revealed on click)
        self._action_row = QWidget()
        self._action_row.setObjectName("cardActionRow")
        action_lay = QHBoxLayout(self._action_row)
        action_lay.setContentsMargins(0, 4, 0, 0)
        action_lay.setSpacing(4)

        self._edit_btn = QPushButton()
        self._edit_btn.setIcon(get_themed_icon("edit"))
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setToolTip("Edit Task")
        self._edit_btn.clicked.connect(self._on_edit)
        self._edit_btn.setObjectName("cardActionBtn")
        action_lay.addWidget(self._edit_btn, stretch=1)

        self._star_btn = QPushButton()
        self._star_btn.setIcon(get_themed_icon("star"))
        self._star_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._star_btn.setToolTip("Toggle Star")
        self._star_btn.clicked.connect(self._on_toggle_star)
        self._star_btn.setObjectName("cardActionBtn")
        action_lay.addWidget(self._star_btn, stretch=1)

        self._del_btn = QPushButton()
        self._del_btn.setIcon(self._trash_icon())
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setToolTip("Delete Task")
        self._del_btn.clicked.connect(self._on_delete_task)
        self._del_btn.setObjectName("cardActionBtnDanger")
        action_lay.addWidget(self._del_btn, stretch=1)

        self._action_row.setMaximumHeight(0)
        self._action_row.setVisible(False)
        left_layout.addWidget(self._action_row)

        lay.addLayout(left_layout, stretch=1)

    def _set_drag_passthrough(self, widget: QWidget) -> None:
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        for child in widget.findChildren(QWidget):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def populate(
        self,
        task: Task,
        links: list[TaskLink] | None = None,
        prereq_tasks: list[Task] | None = None,
    ) -> None:
        if self._expanded:
            self._collapse_immediate()
        if TaskCard._currently_expanded is self:
            TaskCard._currently_expanded = None
        self.task = task
        self._check.blockSignals(True)
        self._check.setChecked(task.is_completed)
        self._check.blockSignals(False)

        self._title_lbl.setText(task.title)
        self._title_lbl.setProperty("completed", task.is_completed)
        self._title_lbl.style().unpolish(self._title_lbl)
        self._title_lbl.style().polish(self._title_lbl)

        self.setProperty("priority", task.priority if task.priority > 0 else 0)
        self.style().unpolish(self)
        self.style().polish(self)

        if task.id is None:
            return
        self._chips.set_task_id(task.id, links)

        if task.priority > 0:
            self._pri_lbl.setText(f"P{task.priority}")
            self._pri_lbl.setObjectName(f"priority{task.priority}")
            self._pri_lbl.style().unpolish(self._pri_lbl)
            self._pri_lbl.style().polish(self._pri_lbl)
            self._pri_lbl.setVisible(True)
        else:
            self._pri_lbl.setVisible(False)

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
            self._set_drag_passthrough(self._tags_widget)
        else:
            self._tags_widget.setVisible(False)

        # Prerequisites — use pre-loaded data if available, else query
        clear_layout(self._prereqs_row)
        if prereq_tasks is None:
            prereq_tasks = get_prerequisite_tasks(task.id)
        if prereq_tasks:
            for pt in prereq_tasks:
                text = f"{truncate_title(pt.title)} → this"
                self._prereqs_row.addWidget(make_chip(text, strikethrough=pt.is_completed))
            self._prereqs_row.addStretch()
            self._prereqs_widget.setVisible(True)
            self._set_drag_passthrough(self._prereqs_widget)
        else:
            self._prereqs_widget.setVisible(False)

        icon_name = "star_filled" if task.is_starred else "star"
        self._star_btn.setIcon(get_themed_icon(icon_name))

    @staticmethod
    def _trash_icon() -> QIcon:
        """Return a trash icon in the theme's danger color."""
        from ..config import get_config
        from ..styles import theme_colors

        color = theme_colors(get_config().theme)["danger"]
        return get_icon("trash", color)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            self._edit_btn.setIcon(get_themed_icon("edit"))
            icon_name = "star_filled" if self.task and self.task.is_starred else "star"
            self._star_btn.setIcon(get_themed_icon(icon_name))
            self._del_btn.setIcon(self._trash_icon())

    def _on_toggle(self, checked: bool) -> None:
        if self.task is None or self.task.id is None:
            return
        if checked:
            blockers = complete_task(self.task.id)
            if blockers:
                self._check.blockSignals(True)
                self._check.setChecked(False)
                self._check.blockSignals(False)
                flash_checkbox_blocked(
                    self._check,
                    ", ".join(b.title for b in blockers),
                )
                return
        else:
            uncomplete_task(self.task.id)
        board = self.window().findChild(TaskBoardView)
        if board:
            board.refresh()

    def _on_toggle_star(self) -> None:
        if self.task is None or self.task.id is None:
            return
        new_val = 0 if self.task.is_starred else 1
        update_task(self.task.id, is_starred=new_val)
        board = self.window().findChild(TaskBoardView)
        if board:
            board.refresh()

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_edit()
        else:
            super().mouseDoubleClickEvent(event)

    def _on_edit(self) -> None:
        if self.task is None or self.task.id is None:
            return
        board = self.window().findChild(TaskBoardView)
        if board:
            board.show_edit_panel(self.task)

    def _on_delete_task(self) -> None:
        if self.task is None or self.task.id is None:
            return
        dlg = ConfirmDialog("Delete Task", "Permanently delete this task?", self.window())
        if dlg.exec():
            delete_task(self.task.id)
            board = self.window().findChild(TaskBoardView)
            if board:
                board.refresh()

    # ── Expand / collapse ──────────────────────────────────────────────

    def _toggle_expand(self) -> None:
        if self._expanded:
            self._collapse()
        else:
            if (
                TaskCard._currently_expanded is not None
                and TaskCard._currently_expanded is not self
            ):
                TaskCard._currently_expanded._collapse()
            self._expand()

    def _expand(self) -> None:
        self._expanded = True
        TaskCard._currently_expanded = self
        self._action_row.setVisible(True)

        # Set expanded dynamic property for QSS styling
        self.setProperty("expanded", True)
        self.style().unpolish(self)
        self.style().polish(self)

        if get_config().animations_enabled:
            target = self._action_row.sizeHint().height()
            self._expand_anim = QPropertyAnimation(self._action_row, b"maximumHeight")
            self._expand_anim.setDuration(120)
            self._expand_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._expand_anim.setStartValue(0)
            self._expand_anim.setEndValue(target)
            self._expand_anim.finished.connect(lambda: self._action_row.setMaximumHeight(16777215))
            self._expand_anim.start()
        else:
            self._action_row.setMaximumHeight(16777215)

    def _collapse(self) -> None:
        self._expanded = False
        if TaskCard._currently_expanded is self:
            TaskCard._currently_expanded = None

        self.setProperty("expanded", False)
        self.style().unpolish(self)
        self.style().polish(self)

        if get_config().animations_enabled:
            current_h = self._action_row.height()
            self._collapse_anim = QPropertyAnimation(self._action_row, b"maximumHeight")
            self._collapse_anim.setDuration(100)
            self._collapse_anim.setEasingCurve(QEasingCurve.Type.InCubic)
            self._collapse_anim.setStartValue(current_h)
            self._collapse_anim.setEndValue(0)
            self._collapse_anim.finished.connect(lambda: self._action_row.setVisible(False))
            self._collapse_anim.start()
        else:
            self._action_row.setMaximumHeight(0)
            self._action_row.setVisible(False)

    def _collapse_immediate(self) -> None:
        self._expanded = False
        if TaskCard._currently_expanded is self:
            TaskCard._currently_expanded = None
        self._action_row.setMaximumHeight(0)
        self._action_row.setVisible(False)
        self.setProperty("expanded", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            logger.debug(
                "Task card press received for task_id=%s", self.task.id if self.task else None
            )
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            distance = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            if distance < QApplication.startDragDistance():
                # This was a click, not a drag — check if it hit the checkbox
                child = self.childAt(self._drag_start_pos)
                if not isinstance(child, QCheckBox) and child is not self._check:
                    self._toggle_expand()
        self._drag_start_pos = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_start_pos is None:
            return super().mouseMoveEvent(event)
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(event)
        distance = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
        if distance < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)
        if self.task is None or self.task.id is None:
            return super().mouseMoveEvent(event)
        logger.debug(
            "Starting task card drag for task_id=%s project_id=%s",
            self.task.id,
            self.task.project_id,
        )
        drag = QDrag(self)
        mime = QMimeData()
        payload = f"{self.task.id}:{self.task.project_id}"
        mime.setData(TASK_MIME_TYPE, QByteArray(payload.encode()))
        drag.setMimeData(mime)
        pixmap = QPixmap(self.size() * self.devicePixelRatioF())
        pixmap.setDevicePixelRatio(self.devicePixelRatioF())
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 10, 10)
        painter.setClipPath(path)
        self.render(painter, self.rect().topLeft())
        painter.setOpacity(0.7)
        painter.fillRect(QRectF(0, 0, self.width(), self.height()), QColor(0, 0, 0, 40))
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(self._drag_start_pos)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        drag.exec(Qt.DropAction.MoveAction)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start_pos = None


class ProjectColumn(QFrame):
    """A reusable column in the board, representing one project."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: Project | None = None
        self._show_completed: bool = False
        self._original_style = None
        self.setMinimumWidth(260)
        self.setMaximumWidth(360)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setAcceptDrops(True)
        self._build()

    def _build(self) -> None:
        self.setObjectName("column")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # Header
        header = QHBoxLayout()
        self._name_lbl = QLabel()
        self._name_lbl.setObjectName("titleLabelLarge")
        header.addWidget(self._name_lbl)

        self._count_lbl = QLabel()
        self._count_lbl.setObjectName("columnCount")
        header.addWidget(self._count_lbl)

        header.addStretch()

        self._star_btn = QPushButton()
        self._star_btn.setIcon(get_themed_icon("star"))
        self._star_btn.setFixedSize(28, 28)
        self._star_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._star_btn.setToolTip("Toggle Star")
        self._star_btn.clicked.connect(self._on_toggle_star)
        self._star_btn.setObjectName("iconButtonLarge")
        header.addWidget(self._star_btn)

        self._settings_btn = QPushButton()
        self._settings_btn.setIcon(get_themed_icon("settings"))
        self._settings_btn.setFixedSize(28, 28)
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setToolTip("Project Settings")
        self._settings_btn.clicked.connect(self._edit_project)
        self._settings_btn.setObjectName("iconButtonLarge")
        header.addWidget(self._settings_btn)

        lay.addLayout(header)

        # Project description (shown below name if present)
        self._desc_lbl = QLabel()
        self._desc_lbl.setObjectName("smallMuted")
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setVisible(False)
        lay.addWidget(self._desc_lbl)

        # Cards area — pool goes here
        self._cards_layout = QVBoxLayout()
        self._cards_layout.setSpacing(6)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self._cards_layout)

        self._card_pool: WidgetPool[TaskCard] = WidgetPool(
            factory=TaskCard,
            layout=self._cards_layout,
            initial=6,
        )

        self._empty_lbl = QLabel()
        self._empty_lbl.setObjectName("smallMuted")
        self._cards_layout.addWidget(self._empty_lbl)

        self._overflow_lbl = QLabel()
        self._overflow_lbl.setObjectName("smallMuted")
        self._overflow_lbl.setVisible(False)
        self._cards_layout.addWidget(self._overflow_lbl)

        # Inline quick-add input
        self._quick_add = QLineEdit()
        self._quick_add.setObjectName("quickAddInput")
        self._quick_add.setPlaceholderText("+ Add task...")
        self._quick_add.setCursor(Qt.CursorShape.IBeamCursor)
        self._quick_add.returnPressed.connect(self._quick_create_task)
        lay.addWidget(self._quick_add)

        lay.addStretch()

    def populate(
        self,
        project: Project,
        tasks: list[Task],
        show_completed: bool,
        links_map: dict[int, list[TaskLink]] | None = None,
        prereqs_map: dict[int, list[Task]] | None = None,
    ) -> None:
        self.project = project
        self._show_completed = show_completed
        self._name_lbl.setText(project.name)

        icon_name = "star_filled" if project.is_starred else "star"
        self._star_btn.setIcon(get_themed_icon(icon_name))

        if project.description:
            self._desc_lbl.setText(project.description)
            self._desc_lbl.setVisible(True)
        else:
            self._desc_lbl.setVisible(False)

        active = [t for t in tasks if not t.is_completed]
        done = [t for t in tasks if t.is_completed]
        active_count = len(active)
        self._count_lbl.setText(str(active_count))
        self._count_lbl.setVisible(active_count > 0 and not show_completed)

        if show_completed:
            visible = done[:COMPLETED_LIMIT]
            self._quick_add.setVisible(False)
            if len(done) > COMPLETED_LIMIT:
                self._overflow_lbl.setText(f"…and {len(done) - COMPLETED_LIMIT} more")
                self._overflow_lbl.setVisible(True)
            else:
                self._overflow_lbl.setVisible(False)
        else:
            visible = active
            self._quick_add.setVisible(True)
            self._overflow_lbl.setVisible(False)

        self._card_pool.begin_update()
        for t in visible:
            card = self._card_pool.acquire()
            task_links = links_map.get(t.id, []) if links_map and t.id is not None else None
            task_prereqs = prereqs_map.get(t.id, []) if prereqs_map and t.id is not None else None
            card.populate(t, links=task_links, prereq_tasks=task_prereqs)

        if not visible:
            self._empty_lbl.setText("No completed tasks" if show_completed else "No active tasks")
            self._empty_lbl.setVisible(True)
        else:
            self._empty_lbl.setVisible(False)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            icon_name = "star_filled" if self.project and self.project.is_starred else "star"
            self._star_btn.setIcon(get_themed_icon(icon_name))
            self._settings_btn.setIcon(get_themed_icon("settings"))

    def _on_toggle_star(self) -> None:
        if self.project is None or self.project.id is None:
            return
        new_val = 0 if self.project.is_starred else 1
        update_project(self.project.id, is_starred=new_val)
        board = self.window().findChild(TaskBoardView)
        if board:
            board.refresh()

    def _edit_project(self) -> None:
        if self.project is None or self.project.id is None:
            return
        dlg = EditProjectDialog(self.project.name, self.project.id, self.project.description, self)
        accepted = dlg.exec()
        if dlg.was_deleted():
            board = self.window().findChild(TaskBoardView)
            if board:
                board.refresh()
            return
        if accepted:
            vals = dlg.get_values()
            if not vals["name"]:
                QMessageBox.warning(self, "Error", "Project name cannot be empty.")
                return
            name_changed = vals["name"] != self.project.name
            desc_changed = vals["description"] != self.project.description
            if name_changed or desc_changed:
                try:
                    update_project(
                        self.project.id, name=vals["name"], description=vals["description"]
                    )
                    board = self.window().findChild(TaskBoardView)
                    if board:
                        board.refresh()
                except Exception:
                    QMessageBox.warning(self, "Error", "A project with that name already exists.")

    def _quick_create_task(self) -> None:
        title = self._quick_add.text().strip()
        if not title or self.project is None or self.project.id is None:
            return
        create_task(project_id=self.project.id, title=title)
        self._quick_add.clear()
        # Find parent TaskBoardView and refresh
        from grouper.ui.task_board import TaskBoardView

        board = self.window().findChild(TaskBoardView)
        if board:
            board.refresh()

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat(TASK_MIME_TYPE):
            logger.debug(
                "Task drag entered project column project_id=%s",
                self.project.id if self.project else None,
            )
            event.acceptProposedAction()
            self._highlight(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat(TASK_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        self._highlight(False)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        self._highlight(False)
        mime = event.mimeData()
        if not mime.hasFormat(TASK_MIME_TYPE):
            event.ignore()
            return

        if self.project is None or self.project.id is None:
            event.ignore()
            return

        # Parse the mime payload "task_id:source_project_id".
        # Wrap in try/except because PySide6 silently swallows exceptions
        # raised inside event handlers — a malformed payload would cause the
        # drop to look accepted while update_task never runs.
        try:
            raw = mime.data(TASK_MIME_TYPE).data().decode()
            parts = raw.split(":", 1)
            task_id = int(parts[0])
            source_project_id = int(parts[1]) if len(parts) > 1 else -1
        except (ValueError, IndexError):
            event.ignore()
            return

        logger.debug(
            "Dropping task_id=%s from project_id=%s to project_id=%s",
            task_id,
            source_project_id,
            self.project.id,
        )

        if task_id > 0 and source_project_id != self.project.id:
            try:
                update_task(task_id, project_id=self.project.id)
            except Exception:
                logger.exception(
                    "Failed to move task %d to project %d during drag-and-drop",
                    task_id,
                    self.project.id,
                )
                # FK violation or other DB error (e.g. project deleted
                # between populate and drop). Accept the event to avoid
                # confusing Qt drag state, but skip the refresh.
                event.acceptProposedAction()
                return
            win = self.window()
            if win is not None:
                board = win.findChild(TaskBoardView)
                if board is not None:
                    board.refresh()

        event.acceptProposedAction()

    def _highlight(self, active: bool) -> None:
        if active:
            self.setProperty("drag", True)
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            self.setProperty("drag", False)
            self.style().unpolish(self)
            self.style().polish(self)


class TaskBoardView(QWidget):
    """Kanban-style board with columns per project."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Ensure at least a default board exists
        default_board = get_or_create_default_board()

        # Load active board ID from settings, defaulting to the ensured board.
        default_board_id = default_board.id if default_board.id is not None else 1
        stored = get_setting("active_board_id", str(default_board_id)) or str(default_board_id)
        try:
            self._active_board_id: int | None = int(stored)
        except ValueError:
            self._active_board_id = default_board_id

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

        # -- Page 0: board content ---------------------------------------------
        board_page = QWidget()
        outer = QVBoxLayout(board_page)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title = QLabel("Board:")
        title.setProperty("heading", True)
        header.addWidget(title)

        self._board_combo = QComboBox()
        self._board_combo.setMinimumWidth(250)
        self._board_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._board_combo.currentIndexChanged.connect(self._on_board_changed)
        header.addWidget(self._board_combo, stretch=1)

        rename_btn = QPushButton("Edit Board")
        rename_btn.setToolTip("Edit Board")
        rename_btn.clicked.connect(self._edit_board)
        header.addWidget(rename_btn)

        add_board_btn = QPushButton("+ Board")
        add_board_btn.clicked.connect(self._add_board)
        header.addWidget(add_board_btn)

        # "Show completed" toggle — default off
        self._show_completed_cb = QCheckBox("Show completed")
        self._show_completed_cb.setChecked(False)
        self._show_completed_cb.setToolTip(
            "When checked, active tasks are hidden and up to "
            f"{COMPLETED_LIMIT} completed tasks are shown per column."
        )
        self._show_completed_cb.toggled.connect(self.refresh)
        header.addWidget(self._show_completed_cb)

        header.addStretch()

        add_proj_btn = QPushButton("+ Project")
        add_proj_btn.clicked.connect(self._add_project)
        header.addWidget(add_proj_btn)

        add_task_btn = QPushButton("+ Task")
        add_task_btn.setProperty("primary", True)
        add_task_btn.clicked.connect(self._add_task)
        header.addWidget(add_task_btn)
        outer.addLayout(header)

        # Scrollable board area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._board_container = QWidget()
        self._board_layout = QHBoxLayout(self._board_container)
        self._board_layout.setContentsMargins(0, 0, 0, 0)
        self._board_layout.setSpacing(16)
        self._board_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._scroll.setWidget(self._board_container)
        outer.addWidget(self._scroll)

        self._col_pool: WidgetPool[ProjectColumn] = WidgetPool(
            factory=ProjectColumn,
            layout=self._board_layout,
            initial=6,
        )
        self._empty_board_lbl = QLabel("No projects on this board yet. Click '+ Project' to start.")
        self._empty_board_lbl.setObjectName("emptyMessage")
        self._empty_board_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._board_layout.addWidget(self._empty_board_lbl)

        self._inner_stack.addWidget(board_page)  # index 0

        # -- Page 1: task panel ------------------------------------------------
        self._task_panel = TaskPanel()
        self._task_panel.closed.connect(self._close_panel)
        self._task_panel.task_saved.connect(self._on_task_saved)
        self._inner_stack.addWidget(self._task_panel)  # index 1

    def refresh(self) -> None:
        h_bar = self._scroll.horizontalScrollBar()
        v_bar = self._scroll.verticalScrollBar()
        h_pos = h_bar.value()
        v_pos = v_bar.value()
        self.setUpdatesEnabled(False)
        try:
            self._refresh_inner()
        finally:
            self.setUpdatesEnabled(True)
            h_bar.setValue(h_pos)
            v_bar.setValue(v_pos)

    def _refresh_inner(self) -> None:
        # Refresh the board combo box first without triggering changes
        self._board_combo.blockSignals(True)
        self._board_combo.clear()
        boards = list_boards()
        active_idx = 0
        for i, b in enumerate(boards):
            self._board_combo.addItem(b.name, b.id)
            if b.id == self._active_board_id:
                active_idx = i
        if boards:
            self._board_combo.setCurrentIndex(active_idx)
            # Just in case the currently loaded active board ID was invalid/deleted
            self._active_board_id = self._board_combo.currentData()
        self._board_combo.blockSignals(False)

        show_completed = self._show_completed_cb.isChecked()

        self._col_pool.begin_update()

        if self._active_board_id is None:
            self._empty_board_lbl.setText("No board selected.")
            self._empty_board_lbl.setVisible(True)
            return

        projects = list_projects(board_id=self._active_board_id)
        if not projects:
            self._empty_board_lbl.setText(
                "No projects on this board yet. Click '+ Project' to start."
            )
            self._empty_board_lbl.setVisible(True)
            return

        self._empty_board_lbl.setVisible(False)

        # Collect all tasks across all projects, then batch-load links and
        # prerequisites in two queries instead of 2*N per-card queries.
        all_project_tasks: list[tuple[Project, list[Task]]] = []
        all_task_ids: list[int] = []
        for p in projects:
            if p.id is None:
                continue
            tasks = get_tasks(p.id)
            all_project_tasks.append((p, tasks))
            all_task_ids.extend(t.id for t in tasks if t.id is not None)

        links_map = get_links_for_task_ids(all_task_ids)
        prereqs_map = get_prerequisite_tasks_for_ids(all_task_ids)

        for p, tasks in all_project_tasks:
            col = self._col_pool.acquire()
            col.populate(p, tasks, show_completed, links_map, prereqs_map)

    def _on_board_changed(self, idx: int) -> None:
        if idx >= 0:
            board_id = self._board_combo.currentData()
            self._active_board_id = board_id
            set_setting("active_board_id", str(board_id))
            self.refresh()

    def _add_board(self) -> None:
        dlg = AddBoardDialog(self)
        if dlg.exec() and dlg.get_board_name():
            try:
                board = create_board(dlg.get_board_name())
                self._active_board_id = board.id
                set_setting("active_board_id", str(board.id))
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to create board: {e}")

    def _edit_board(self) -> None:
        if self._active_board_id is None:
            return

        current_name = self._board_combo.currentText()
        dlg = EditBoardDialog(self._active_board_id, current_name, self)
        accepted = dlg.exec()
        if dlg.was_deleted():
            self._active_board_id = 1
            set_setting("active_board_id", "1")
            self.refresh()
            return
        if accepted:
            vals = dlg.get_values()
            new_name = vals["name"]
            if new_name and new_name != current_name:
                if rename_board(self._active_board_id, new_name):
                    self.refresh()
                else:
                    QMessageBox.warning(self, "Error", "A board with that name already exists.")

    def _add_project(self) -> None:
        if self._active_board_id is None:
            return

        from ..database import create_project

        dlg = CreateProjectDialog(board_id=self._active_board_id, parent=self)
        if dlg.exec():
            vals = dlg.get_values()
            if vals["name"]:
                create_project(**vals)
                self.refresh()

    def _add_task(self) -> None:
        self.show_create_panel()

    # -- task panel integration ------------------------------------------------

    def show_create_panel(self, project_id: int | None = None) -> None:
        """Slide to the task panel in create mode."""
        if self._active_board_id is None:
            return
        projects = list_projects(board_id=self._active_board_id)
        if not projects:
            return
        self._task_panel.load_for_create(projects, self._active_board_id, project_id)
        self._inner_stack.setCurrentIndex(1)

    def show_edit_panel(self, task: Task) -> None:
        """Slide to the task panel in edit mode."""
        if self._active_board_id is None:
            return
        board_id = self._active_board_id
        self._inner_stack.setCurrentIndex(1)  # start slide animation immediately
        # Defer DB-heavy load to next event loop iteration so the first
        # animation frame renders without blocking.
        QTimer.singleShot(0, lambda t=task, b=board_id: self._task_panel.load_for_edit(t, b))

    def _close_panel(self) -> None:
        """Slide back to the board view."""
        self._inner_stack.setCurrentIndex(0)

    def _on_task_saved(self) -> None:
        """Refresh after a task was created or updated via the panel."""
        self.refresh()
