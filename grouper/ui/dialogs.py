"""
dialogs.py — Shared dialog windows for Grouper.
"""

from datetime import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..database.prerequisites import (
    add_prerequisite,
    get_prerequisite_tasks,
    remove_prerequisite,
)
from ..database.tags import (
    add_tag_to_task,
    get_task_tags,
    remove_tag_from_task,
)
from ..database.task_links import add_link, delete_link, get_links_for_task
from ..database.tasks import get_task, get_tasks_by_board
from .title_bar import DialogTitleBar
from .widgets import (
    ThemedDateEdit,
    ThemedSpinBox,
    clear_layout,
    make_removable_chip,
    truncate_title,
)


def _build_due_date_row(
    existing_date: datetime | None = None,
) -> tuple[QCheckBox, ThemedDateEdit, QHBoxLayout]:
    """Build a due-date checkbox + date-edit row, optionally pre-populated."""
    due_check = QCheckBox("Set due date")
    due_date = ThemedDateEdit()
    if existing_date:
        due_date.setDate(QDate(existing_date.year, existing_date.month, existing_date.day))
        due_check.setChecked(True)
        due_date.setEnabled(True)
    else:
        due_date.setDate(QDate.currentDate())
        due_date.setEnabled(False)
    due_check.toggled.connect(due_date.setEnabled)
    row = QHBoxLayout()
    row.addWidget(due_check)
    row.addWidget(due_date)
    return due_check, due_date, row


class FramelessDialog(QDialog):
    """Base class for frameless dialogs with custom title bar and shadow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)

        self._container = QFrame()
        self._container.setObjectName("dialogFrame")
        self._container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        self._container.setGraphicsEffect(shadow)

        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(16, 16, 16, 16)
        self._outer_layout.addWidget(self._container)

        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(0)

        self._title_bar = DialogTitleBar("", self._container)
        self._title_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._container_layout.addWidget(self._title_bar)

        self._content = QWidget()
        self._content.setObjectName("dialogContent")
        self._content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._container_layout.addWidget(self._content)

        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(16, 12, 16, 16)
        self._content_layout.setSpacing(10)

    def setWindowTitle(self, title: str):
        super().setWindowTitle(title)
        if hasattr(self, "_title_bar"):
            self._title_bar.set_title(title)

    def contentLayout(self) -> QVBoxLayout:
        return self._content_layout


class CreateActivityDialog(FramelessDialog):
    """Dialog for creating a new activity (time-tracking entity)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Activity")
        self.setMinimumWidth(380)

        layout = QFormLayout()
        self.contentLayout().addLayout(layout)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Activity name")
        layout.addRow("Name:", self.name_input)

        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Optional description")
        layout.addRow("Description:", self.desc_input)

        self.bg_check = QCheckBox("Background activity (e.g. Music)")
        layout.addRow("", self.bg_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self) -> dict:
        return {
            "name": self.name_input.text().strip(),
            "description": self.desc_input.text().strip() or None,
            "is_background": self.bg_check.isChecked(),
        }


class CreateProjectDialog(FramelessDialog):
    """Dialog for creating a new project (task container)."""

    def __init__(self, board_id: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.setMinimumWidth(380)
        self.board_id = board_id

        layout = QFormLayout()
        self.contentLayout().addLayout(layout)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Project name")
        layout.addRow("Name:", self.name_input)

        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Optional description")
        layout.addRow("Description:", self.desc_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self) -> dict:
        return {
            "name": self.name_input.text().strip(),
            "board_id": self.board_id,
            "description": self.desc_input.text().strip() or None,
        }


class EditProjectDialog(FramelessDialog):
    """Dialog for editing a project's name, description, or deleting it."""

    def __init__(
        self,
        project_name: str,
        project_id: int,
        project_description: str | None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit Project")
        self.setMinimumWidth(380)
        self._project_name = project_name
        self._project_id = project_id
        self._deleted = False

        layout = QFormLayout()
        self.contentLayout().addLayout(layout)

        self.name_input = QLineEdit()
        self.name_input.setText(project_name)
        layout.addRow("Name:", self.name_input)

        self.desc_input = QLineEdit()
        self.desc_input.setText(project_description or "")
        self.desc_input.setPlaceholderText("Optional description")
        layout.addRow("Description:", self.desc_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.contentLayout().addWidget(buttons)

        delete_btn = QPushButton("Delete Project")
        delete_btn.setObjectName("dangerButton")
        delete_btn.clicked.connect(self._on_delete)
        self.contentLayout().addWidget(delete_btn)

    def _on_delete(self) -> None:
        from ..database.projects import delete_project_by_id

        dlg = ConfirmDialog(
            "Delete Project",
            f"Permanently delete '{self._project_name}' and all its tasks?\nThis cannot be undone.",
            self,
        )
        if dlg.exec():
            delete_project_by_id(self._project_id)
            self._deleted = True
            self.reject()

    def get_values(self) -> dict:
        return {
            "name": self.name_input.text().strip(),
            "description": self.desc_input.text().strip() or None,
        }

    def was_deleted(self) -> bool:
        return self._deleted


class EditBoardDialog(FramelessDialog):
    """Dialog for editing a board's name or deleting it."""

    def __init__(self, board_id: int, current_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Board")
        self.setMinimumWidth(380)
        self._board_id = board_id
        self._deleted = False

        layout = QFormLayout()
        self.contentLayout().addLayout(layout)

        self.name_input = QLineEdit()
        self.name_input.setText(current_name)
        layout.addRow("Name:", self.name_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        delete_btn = QPushButton("Delete Board")
        delete_btn.setObjectName("dangerButton")
        delete_btn.clicked.connect(self._on_delete)
        if board_id == 1:
            delete_btn.setVisible(False)
        layout.addRow(delete_btn)

    def _on_delete(self) -> None:
        from ..database.boards import delete_board

        dlg = ConfirmDialog(
            "Delete Board",
            "Permanently delete this board and ALL its projects and tasks?\nThis cannot be undone.",
            self,
        )
        if dlg.exec() and delete_board(self._board_id):
            self._deleted = True
            self.reject()

    def get_values(self) -> dict:
        return {
            "name": self.name_input.text().strip(),
        }

    def was_deleted(self) -> bool:
        return self._deleted


class AddBoardDialog(FramelessDialog):
    """Dialog for creating a new board."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Board")
        self.setMinimumWidth(320)

        layout = QFormLayout()
        self.contentLayout().addLayout(layout)

        self._name = QLineEdit()
        self._name.setPlaceholderText("Board name")
        layout.addRow("Name:", self._name)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_board_name(self) -> str:
        return self._name.text().strip()


class CreateTaskDialog(FramelessDialog):
    """Dialog for creating a new task."""

    def __init__(
        self,
        projects: list,
        parent=None,
        preselected_project_id: int | None = None,
        board_id: int | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("New Task")
        self.setMinimumWidth(380)
        self._board_id = board_id

        layout = QFormLayout()
        self.contentLayout().addLayout(layout)

        self.project_combo = QComboBox()
        for p in projects:
            self.project_combo.addItem(p.name, p.id)
        if preselected_project_id is not None:
            idx = self.project_combo.findData(preselected_project_id)
            if idx >= 0:
                self.project_combo.setCurrentIndex(idx)
        layout.addRow("Project:", self.project_combo)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Task title")
        layout.addRow("Title:", self.title_input)

        self.priority_spin = ThemedSpinBox()
        self.priority_spin.setRange(0, 5)
        self.priority_spin.setValue(0)
        self.priority_spin.setSpecialValueText("None")
        layout.addRow("Priority:", self.priority_spin)

        self.due_check, self.due_date, due_row = _build_due_date_row()
        layout.addRow("Due:", due_row)

        self._pending_tags: list[str] = []

        tag_row = QHBoxLayout()
        tag_row.setSpacing(6)
        self._tag_input = QLineEdit()
        self._tag_input.setPlaceholderText("Add tag...")
        self._tag_input.returnPressed.connect(self._add_pending_tag)
        tag_add_btn = QPushButton("Add")
        tag_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        tag_add_btn.clicked.connect(self._add_pending_tag)
        tag_row.addWidget(self._tag_input, stretch=1)
        tag_row.addWidget(tag_add_btn)
        layout.addRow("Tags:", tag_row)

        self._tag_chips_container = QHBoxLayout()
        self._tag_chips_container.setSpacing(6)
        layout.addRow(self._tag_chips_container)

        # --- Prerequisites section ---
        self._pending_prereqs: list[tuple[int, str]] = []  # (task_id, title)

        prereq_row = QHBoxLayout()
        prereq_row.setSpacing(6)
        self._prereq_combo = QComboBox()
        self._prereq_combo.addItem("Select prerequisite...", None)
        self._populate_prereq_combo()
        prereq_add_btn = QPushButton("Add")
        prereq_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prereq_add_btn.clicked.connect(self._add_pending_prereq)
        prereq_row.addWidget(self._prereq_combo, stretch=1)
        prereq_row.addWidget(prereq_add_btn)
        layout.addRow("Prereqs:", prereq_row)

        self._prereq_chips_container = QHBoxLayout()
        self._prereq_chips_container.setSpacing(6)
        layout.addRow(self._prereq_chips_container)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _populate_prereq_combo(self) -> None:
        """Fill the prerequisite combo with incomplete tasks from the same board."""
        if self._board_id is None:
            return
        tasks = get_tasks_by_board(self._board_id)
        for t in tasks:
            if t.id is not None and not t.is_completed:
                self._prereq_combo.addItem(t.title, t.id)

    def _add_pending_prereq(self) -> None:
        task_id = self._prereq_combo.currentData()
        if task_id is None:
            return
        if any(pid == task_id for pid, _ in self._pending_prereqs):
            return
        title = self._prereq_combo.currentText()
        self._pending_prereqs.append((task_id, title))
        self._rebuild_prereq_chips()

    def _remove_pending_prereq(self, task_id: int) -> None:
        self._pending_prereqs = [(pid, t) for pid, t in self._pending_prereqs if pid != task_id]
        self._rebuild_prereq_chips()

    def _rebuild_prereq_chips(self) -> None:
        clear_layout(self._prereq_chips_container)
        for task_id, title in self._pending_prereqs:
            text = f"{truncate_title(title)} → this"
            chip = make_removable_chip(text, lambda tid=task_id: self._remove_pending_prereq(tid))
            self._prereq_chips_container.addWidget(chip)
        self._prereq_chips_container.addStretch()

    def _add_pending_tag(self) -> None:
        name = self._tag_input.text().strip()
        if not name or name in self._pending_tags:
            return
        self._pending_tags.append(name)
        self._tag_input.clear()
        self._rebuild_pending_chips()

    def _remove_pending_tag(self, tag_name: str) -> None:
        if tag_name in self._pending_tags:
            self._pending_tags.remove(tag_name)
        self._rebuild_pending_chips()

    def _rebuild_pending_chips(self) -> None:
        clear_layout(self._tag_chips_container)
        for tag_name in self._pending_tags:
            chip = make_removable_chip(tag_name, lambda n=tag_name: self._remove_pending_tag(n))
            self._tag_chips_container.addWidget(chip)
        self._tag_chips_container.addStretch()

    def get_values(self) -> dict:
        due = None
        if self.due_check.isChecked():
            qd = self.due_date.date()
            due = datetime(qd.year(), qd.month(), qd.day())
        return {
            "project_id": self.project_combo.currentData(),
            "title": self.title_input.text().strip(),
            "priority": self.priority_spin.value(),
            "due_date": due,
            "tags": self._pending_tags,
            "prerequisites": [pid for pid, _ in self._pending_prereqs],
        }


class EditTaskDialog(FramelessDialog):
    """Dialog for editing an existing task."""

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task
        self.setWindowTitle("Edit Task")
        self.setMinimumWidth(420)

        layout = QFormLayout()
        self.contentLayout().addLayout(layout)

        self.title_input = QLineEdit()
        self.title_input.setText(task.title)
        self.title_input.setPlaceholderText("Task title")
        layout.addRow("Title:", self.title_input)

        self.priority_spin = ThemedSpinBox()
        self.priority_spin.setRange(0, 5)
        self.priority_spin.setValue(task.priority)
        self.priority_spin.setSpecialValueText("None")
        layout.addRow("Priority:", self.priority_spin)

        self.due_check, self.due_date, due_row = _build_due_date_row(task.due_date)
        layout.addRow("Due:", due_row)

        # --- Tags section ---
        tags_header = QLabel("Tags")
        tags_header.setObjectName("sectionHeader")
        layout.addRow(tags_header)

        self._tags_container = QHBoxLayout()
        self._tags_container.setSpacing(6)
        layout.addRow(self._tags_container)

        tag_add_row = QHBoxLayout()
        tag_add_row.setSpacing(6)
        self._tag_input = QLineEdit()
        self._tag_input.setPlaceholderText("Add tag...")
        self._tag_input.returnPressed.connect(self._add_tag)
        tag_add_btn = QPushButton("Add")
        tag_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        tag_add_btn.clicked.connect(self._add_tag)
        tag_add_row.addWidget(self._tag_input, stretch=1)
        tag_add_row.addWidget(tag_add_btn)
        layout.addRow(tag_add_row)

        self._refresh_tags()

        # --- Prerequisites section ---
        prereqs_header = QLabel("Prerequisites")
        prereqs_header.setObjectName("sectionHeader")
        layout.addRow(prereqs_header)

        self._prereqs_container = QVBoxLayout()
        self._prereqs_container.setSpacing(4)
        layout.addRow(self._prereqs_container)

        prereq_add_row = QHBoxLayout()
        prereq_add_row.setSpacing(6)
        self._prereq_combo = QComboBox()
        self._prereq_combo.addItem("Select prerequisite...", None)
        self._populate_prereq_combo()
        prereq_add_btn = QPushButton("Add")
        prereq_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prereq_add_btn.clicked.connect(self._add_prereq)
        prereq_add_row.addWidget(self._prereq_combo, stretch=1)
        prereq_add_row.addWidget(prereq_add_btn)
        layout.addRow(prereq_add_row)

        self._refresh_prereqs()

        # --- Links section ---
        links_header = QLabel("Links")
        links_header.setObjectName("sectionHeader")
        layout.addRow(links_header)

        self._links_container = QVBoxLayout()
        self._links_container.setSpacing(4)
        layout.addRow(self._links_container)

        # Add-link input row
        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("URL or file path…")
        self._label_input = QLineEdit()
        self._label_input.setPlaceholderText("Label (optional)")
        self._label_input.setMaximumWidth(120)
        add_btn = QPushButton("Add")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add_link)
        self._url_input.returnPressed.connect(self._add_link)
        add_row.addWidget(self._url_input, stretch=1)
        add_row.addWidget(self._label_input)
        add_row.addWidget(add_btn)
        layout.addRow(add_row)

        self._error_label = QLabel()
        self._error_label.setObjectName("errorLabel")
        self._error_label.hide()
        layout.addRow(self._error_label)

        self._refresh_links()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _refresh_links(self) -> None:
        """Rebuild the list of existing link rows."""
        clear_layout(self._links_container)

        links = get_links_for_task(self.task.id)
        for link in links:
            row = QHBoxLayout()
            row.setSpacing(6)
            icon = "🗂" if link.link_type == "file" else "🔗"
            display = link.label if link.label else link.url
            if len(display) > 40:
                display = display[:39] + "…"
            lbl = QLabel(f"{icon} {display}")
            lbl.setToolTip(link.url)
            del_btn = QPushButton("✕")
            del_btn.setFixedSize(22, 22)
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setObjectName("iconButton")
            del_btn.setToolTip("Remove link")
            del_btn.clicked.connect(lambda checked=False, lid=link.id: self._delete_link(lid))
            row.addWidget(lbl, stretch=1)
            row.addWidget(del_btn)

            wrapper = QWidget()
            wrapper.setLayout(row)
            self._links_container.addWidget(wrapper)

    def _add_link(self) -> None:
        url = self._url_input.text().strip()
        if not url:
            self._error_label.setText("URL cannot be empty.")
            self._error_label.show()
            return
        self._error_label.hide()
        label = self._label_input.text().strip() or None
        add_link(self.task.id, url, label)
        self._url_input.clear()
        self._label_input.clear()
        self._refresh_links()

    def _delete_link(self, link_id: int) -> None:
        delete_link(link_id)
        self._refresh_links()

    def _refresh_tags(self) -> None:
        clear_layout(self._tags_container)
        tags = get_task_tags(self.task.id)
        for tag_name in tags:
            chip = self._create_tag_chip(tag_name, self._remove_task_tag)
            self._tags_container.addWidget(chip)
        self._tags_container.addStretch()

    def _create_tag_chip(self, tag_name: str, remove_cb) -> QFrame:
        return make_removable_chip(tag_name, lambda: remove_cb(tag_name))

    def _add_tag(self) -> None:
        name = self._tag_input.text().strip()
        if not name:
            return
        add_tag_to_task(self.task.id, name)
        self._tag_input.clear()
        self._refresh_tags()

    def _remove_task_tag(self, tag_name: str) -> None:
        remove_tag_from_task(self.task.id, tag_name)
        self._refresh_tags()

    def _populate_prereq_combo(self) -> None:
        """Fill combo with incomplete tasks from the same board, excluding self."""
        from ..database.projects import get_project_by_id

        proj = get_project_by_id(self.task.project_id)
        if proj is None:
            return
        board_tasks = get_tasks_by_board(proj.board_id)
        current_prereqs = {pt.id for pt in get_prerequisite_tasks(self.task.id)}
        for t in board_tasks:
            if t.id == self.task.id or t.id is None:
                continue
            if t.is_completed or t.id in current_prereqs:
                continue
            self._prereq_combo.addItem(t.title, t.id)

    def _refresh_prereqs(self) -> None:
        """Rebuild the prerequisite chips from the database."""
        clear_layout(self._prereqs_container)
        prereqs = get_prerequisite_tasks(self.task.id)
        for pt in prereqs:
            if pt.id is None:
                import logging
                logging.getLogger(__name__).warning(
                    "Prerequisite task %r has no id; skipping chip", pt.title
                )
                continue
            text = f"{truncate_title(pt.title)} → this"
            chip = make_removable_chip(text, lambda pid=pt.id: self._remove_prereq(pid))
            self._prereqs_container.addWidget(chip)

    def _add_prereq(self) -> None:
        prereq_id = self._prereq_combo.currentData()
        if prereq_id is None:
            return
        add_prerequisite(self.task.id, prereq_id)
        # Remove from combo since it's now added
        idx = self._prereq_combo.currentIndex()
        self._prereq_combo.removeItem(idx)
        self._prereq_combo.setCurrentIndex(0)
        self._refresh_prereqs()

    def _remove_prereq(self, prereq_task_id: int) -> None:
        remove_prerequisite(self.task.id, prereq_task_id)
        task = get_task(prereq_task_id)
        if task and not task.is_completed:
            self._prereq_combo.addItem(task.title, task.id)
        self._refresh_prereqs()

    def get_values(self) -> dict:
        due = None
        if self.due_check.isChecked():
            qd = self.due_date.date()
            due = datetime(qd.year(), qd.month(), qd.day())
        return {
            "title": self.title_input.text().strip(),
            "priority": self.priority_spin.value(),
            "due_date": due,
        }


class StopSessionDialog(FramelessDialog):
    """Dialog shown when stopping a session — allows notes and optional task attribution."""

    def __init__(self, activity_name: str, tasks: list | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Stop Session — {activity_name}")
        self.setMinimumWidth(400)

        layout = self.contentLayout()

        layout.addWidget(QLabel("Session notes (optional):"))
        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(80)
        self.notes_input.setPlaceholderText("What did you work on?")
        layout.addWidget(self.notes_input)

        self.task_combo = None
        if tasks:
            self.attr_check = QCheckBox("Attribute time to a specific task")
            layout.addWidget(self.attr_check)

            self.task_combo = QComboBox()
            self.task_combo.addItem("— Select task —", None)
            for t in tasks:
                self.task_combo.addItem(t.title, t.id)
            self.task_combo.setEnabled(False)
            self.attr_check.toggled.connect(self.task_combo.setEnabled)
            layout.addWidget(self.task_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self) -> dict:
        task_id = None
        if self.task_combo and hasattr(self, "attr_check") and self.attr_check.isChecked():
            task_id = self.task_combo.currentData()
        return {
            "notes": self.notes_input.toPlainText().strip(),
            "task_id": task_id,
        }


class ConfirmDialog(FramelessDialog):
    """Simple yes/no confirmation dialog."""

    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = self.contentLayout()
        layout.addWidget(QLabel(message))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class AddGroupDialog(FramelessDialog):
    """Dialog for adding a group to an activity."""

    def __init__(self, existing_groups: list[str], current_groups: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Group")
        self.setMinimumWidth(300)
        self.selected_group = None

        layout = self.contentLayout()

        info_lbl = QLabel("Enter or select a group name (max 3 groups per activity):")
        info_lbl.setObjectName("infoLabel")
        layout.addWidget(info_lbl)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Group name")
        layout.addWidget(self.name_input)

        available = [g for g in existing_groups if g not in current_groups]
        if available:
            hint_lbl = QLabel("Or select existing:")
            hint_lbl.setObjectName("infoLabelSmall")
            layout.addWidget(hint_lbl)

            self.existing_list = QListWidget()
            self.existing_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
            for g in available:
                self.existing_list.addItem(g)
            self.existing_list.itemClicked.connect(self._select_existing)
            layout.addWidget(self.existing_list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _select_existing(self, item):
        self.selected_group = item.text()
        self.accept()

    def _on_accept(self):
        self.selected_group = self.name_input.text().strip()
        if self.selected_group:
            self.accept()
        else:
            self.name_input.setObjectName("transparentInput")
            self.name_input.setProperty("error", True)
            self.name_input.style().unpolish(self.name_input)
            self.name_input.style().polish(self.name_input)
