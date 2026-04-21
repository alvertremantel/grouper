"""
task_panel.py — Full-width task create/edit panel.

Replaces CreateTaskDialog and EditTaskDialog with a spacious panel that
slides in from the right via AnimatedViewStack(HORIZONTAL), following the
ActivityConfigPanel pattern.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..database.prerequisites import (
    add_prerequisite,
    get_prerequisite_tasks,
    remove_prerequisite,
)
from ..database.tags import add_tag_to_task, get_task_tags, remove_tag_from_task
from ..database.task_links import add_link, delete_link, get_links_for_task
from ..database.tasks import (
    create_task_with_relations,
    delete_task,
    get_task,
    get_tasks_by_board,
    update_task,
)
from ..models import Project, Task
from .dialogs import ConfirmDialog
from .widgets import (
    ThemedDateEdit,
    ThemedSpinBox,
    clear_flow,
    clear_layout,
    make_removable_chip,
    truncate_title,
)


class TaskPanel(QWidget):
    """Full-width task create/edit panel.

    Signals
    -------
    closed
        Back button clicked or save completed; parent should slide back.
    task_saved
        A task was created or updated; parent should refresh data.
    """

    closed = Signal()
    task_saved = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode: str = "create"  # "create" | "edit"
        self._task: Task | None = None
        self._board_id: int | None = None
        self._pending_tags: list[str] = []
        self._pending_prereqs: list[tuple[int, str]] = []
        self._build()

    # -- layout ----------------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header row (fixed, outside scroll)
        header_container = QWidget()
        header_container.setObjectName("taskPanelHeader")
        header = QHBoxLayout(header_container)
        header.setContentsMargins(28, 20, 28, 12)
        header.setSpacing(12)

        self._back_btn = QPushButton("\u2190 Back")
        self._back_btn.setObjectName("taskPanelBackBtn")
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(self._on_back)
        header.addWidget(self._back_btn)

        self._title_lbl = QLabel("New Task")
        self._title_lbl.setProperty("heading", True)
        header.addWidget(self._title_lbl)
        header.addStretch()

        self._save_btn = QPushButton("Save")
        self._save_btn.setProperty("primary", True)
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.clicked.connect(self._on_save)
        header.addWidget(self._save_btn)

        outer.addWidget(header_container)

        # Scrollable form area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        form_container = QWidget()
        self._form = QVBoxLayout(form_container)
        self._form.setContentsMargins(28, 16, 28, 28)
        self._form.setSpacing(20)

        # ── Basic Info ────────────────────────────────────────────────────
        # Project selector (create mode only)
        self._project_section = QWidget()
        proj_lay = QVBoxLayout(self._project_section)
        proj_lay.setContentsMargins(0, 0, 0, 0)
        proj_lay.setSpacing(4)
        proj_lbl = QLabel("PROJECT")
        proj_lbl.setObjectName("taskPanelSection")
        proj_lay.addWidget(proj_lbl)
        self._project_combo = QComboBox()
        self._project_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        proj_lay.addWidget(self._project_combo)
        self._form.addWidget(self._project_section)

        # Title
        title_section = QVBoxLayout()
        title_section.setSpacing(4)
        title_lbl = QLabel("TITLE")
        title_lbl.setObjectName("taskPanelSection")
        title_section.addWidget(title_lbl)
        self._title_input = QLineEdit()
        self._title_input.setObjectName("taskPanelTitle")
        self._title_input.setPlaceholderText("What needs to be done?")
        title_section.addWidget(self._title_input)
        self._form.addLayout(title_section)

        # Description
        desc_section = QVBoxLayout()
        desc_section.setSpacing(4)
        desc_lbl = QLabel("DESCRIPTION")
        desc_lbl.setObjectName("taskPanelSection")
        desc_section.addWidget(desc_lbl)
        self._desc_input = QTextEdit()
        self._desc_input.setObjectName("taskPanelDescription")
        self._desc_input.setPlaceholderText("Add notes, context, or details...")
        self._desc_input.setMinimumHeight(100)
        self._desc_input.setMaximumHeight(200)
        self._desc_input.setTabChangesFocus(True)
        desc_section.addWidget(self._desc_input)
        self._form.addLayout(desc_section)

        # ── Details ───────────────────────────────────────────────────────
        details_section = QVBoxLayout()
        details_section.setSpacing(4)
        details_lbl = QLabel("DETAILS")
        details_lbl.setObjectName("taskPanelSection")
        details_section.addWidget(details_lbl)

        details_row = QHBoxLayout()
        details_row.setSpacing(16)

        # Priority
        pri_group = QVBoxLayout()
        pri_group.setSpacing(4)
        pri_label = QLabel("Priority")
        pri_label.setObjectName("infoLabel")
        pri_group.addWidget(pri_label)
        self._priority_spin = ThemedSpinBox()
        self._priority_spin.setRange(0, 5)
        self._priority_spin.setValue(0)
        self._priority_spin.setSpecialValueText("None")
        self._priority_spin.setMinimumWidth(80)
        pri_group.addWidget(self._priority_spin)
        details_row.addLayout(pri_group)

        # Due date
        due_group = QVBoxLayout()
        due_group.setSpacing(4)
        due_label = QLabel("Due Date")
        due_label.setObjectName("infoLabel")
        due_group.addWidget(due_label)
        due_row = QHBoxLayout()
        due_row.setSpacing(8)
        self._due_check = QCheckBox("Set due date")
        self._due_date = ThemedDateEdit()
        self._due_date.setDate(QDate.currentDate())
        self._due_date.setEnabled(False)
        self._due_check.toggled.connect(self._due_date.setEnabled)
        due_row.addWidget(self._due_check)
        due_row.addWidget(self._due_date)
        due_group.addLayout(due_row)
        details_row.addLayout(due_group)

        details_row.addStretch()
        details_section.addLayout(details_row)
        self._form.addLayout(details_section)

        # ── Tags ──────────────────────────────────────────────────────────
        tags_section = QVBoxLayout()
        tags_section.setSpacing(4)
        tags_lbl = QLabel("TAGS")
        tags_lbl.setObjectName("taskPanelSection")
        tags_section.addWidget(tags_lbl)

        self._tags_flow = QHBoxLayout()
        self._tags_flow.setSpacing(4)
        self._tags_flow.setContentsMargins(0, 0, 0, 0)
        tags_section.addLayout(self._tags_flow)

        tag_add_row = QHBoxLayout()
        tag_add_row.setSpacing(8)
        self._tag_input = QLineEdit()
        self._tag_input.setPlaceholderText("Add tag...")
        self._tag_input.returnPressed.connect(self._add_tag)
        tag_add_btn = QPushButton("Add")
        tag_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        tag_add_btn.clicked.connect(self._add_tag)
        tag_add_row.addWidget(self._tag_input, stretch=1)
        tag_add_row.addWidget(tag_add_btn)
        tags_section.addLayout(tag_add_row)
        self._form.addLayout(tags_section)

        # ── Prerequisites ─────────────────────────────────────────────────
        prereqs_section = QVBoxLayout()
        prereqs_section.setSpacing(4)
        prereqs_lbl = QLabel("PREREQUISITES")
        prereqs_lbl.setObjectName("taskPanelSection")
        prereqs_section.addWidget(prereqs_lbl)

        self._prereqs_flow = QVBoxLayout()
        self._prereqs_flow.setSpacing(4)
        self._prereqs_flow.setContentsMargins(0, 0, 0, 0)
        prereqs_section.addLayout(self._prereqs_flow)

        prereq_add_row = QHBoxLayout()
        prereq_add_row.setSpacing(8)
        self._prereq_combo = QComboBox()
        self._prereq_combo.addItem("Select prerequisite...", None)
        prereq_add_btn = QPushButton("Add")
        prereq_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prereq_add_btn.clicked.connect(self._add_prereq)
        prereq_add_row.addWidget(self._prereq_combo, stretch=1)
        prereq_add_row.addWidget(prereq_add_btn)
        prereqs_section.addLayout(prereq_add_row)
        self._form.addLayout(prereqs_section)

        # ── Links (edit mode only) ────────────────────────────────────────
        self._links_section = QWidget()
        links_lay = QVBoxLayout(self._links_section)
        links_lay.setContentsMargins(0, 0, 0, 0)
        links_lay.setSpacing(4)
        links_lbl = QLabel("LINKS")
        links_lbl.setObjectName("taskPanelSection")
        links_lay.addWidget(links_lbl)

        self._links_container = QVBoxLayout()
        self._links_container.setSpacing(4)
        links_lay.addLayout(self._links_container)

        link_add_row = QHBoxLayout()
        link_add_row.setSpacing(8)
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("URL or file path\u2026")
        self._url_input.returnPressed.connect(self._add_link)
        self._label_input = QLineEdit()
        self._label_input.setPlaceholderText("Label (optional)")
        self._label_input.setMaximumWidth(160)
        link_add_btn = QPushButton("Add")
        link_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        link_add_btn.clicked.connect(self._add_link)
        link_add_row.addWidget(self._url_input, stretch=1)
        link_add_row.addWidget(self._label_input)
        link_add_row.addWidget(link_add_btn)
        links_lay.addLayout(link_add_row)

        self._link_error = QLabel()
        self._link_error.setObjectName("errorLabel")
        self._link_error.hide()
        links_lay.addWidget(self._link_error)

        self._form.addWidget(self._links_section)

        # ── Danger zone (edit mode only) ──────────────────────────────────
        self._danger_section = QWidget()
        danger_lay = QVBoxLayout(self._danger_section)
        danger_lay.setContentsMargins(0, 16, 0, 0)
        danger_lay.setSpacing(8)
        danger_lbl = QLabel("DANGER ZONE")
        danger_lbl.setObjectName("taskPanelSection")
        danger_lay.addWidget(danger_lbl)

        danger_row = QHBoxLayout()
        self._delete_btn = QPushButton("Delete Task")
        self._delete_btn.setObjectName("dangerButton")
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.clicked.connect(self._on_delete)
        danger_row.addWidget(self._delete_btn)
        danger_row.addStretch()
        danger_lay.addLayout(danger_row)

        self._form.addWidget(self._danger_section)

        self._form.addStretch()

        scroll.setWidget(form_container)
        outer.addWidget(scroll, stretch=1)

    # -- public API ------------------------------------------------------------

    def load_for_create(
        self,
        projects: list[Project],
        board_id: int,
        preselected_project_id: int | None = None,
    ) -> None:
        """Configure the panel for creating a new task."""
        self._mode = "create"
        self._task = None
        self._board_id = board_id
        self._pending_tags = []
        self._pending_prereqs = []

        self._title_lbl.setText("New Task")
        self._save_btn.setText("Create")

        # Show project selector
        self._project_section.setVisible(True)
        self._project_combo.clear()
        for p in projects:
            self._project_combo.addItem(p.name, p.id)
        if preselected_project_id is not None:
            idx = self._project_combo.findData(preselected_project_id)
            if idx >= 0:
                self._project_combo.setCurrentIndex(idx)

        # Clear fields
        self._title_input.clear()
        self._desc_input.clear()
        self._priority_spin.setValue(0)
        self._due_check.setChecked(False)
        self._due_date.setDate(QDate.currentDate())

        # Clear pending collections
        self._rebuild_tags_flow()
        self._rebuild_prereqs_flow()
        self._populate_prereq_combo()

        # Hide edit-only sections
        self._links_section.setVisible(False)
        self._danger_section.setVisible(False)

        self._title_input.setFocus()

    def load_for_edit(self, task: Task, board_id: int) -> None:
        """Configure the panel for editing an existing task."""
        self._mode = "edit"
        self._task = task
        self._board_id = board_id
        self._pending_tags = []
        self._pending_prereqs = []

        self._title_lbl.setText("Edit Task")
        self._save_btn.setText("Save")

        # Hide project selector in edit mode
        self._project_section.setVisible(False)

        # Populate fields
        self._title_input.setText(task.title)
        self._desc_input.setPlainText(task.description)
        self._priority_spin.setValue(task.priority)

        if task.due_date:
            self._due_check.setChecked(True)
            self._due_date.setDate(
                QDate(task.due_date.year, task.due_date.month, task.due_date.day)
            )
        else:
            self._due_check.setChecked(False)
            self._due_date.setDate(QDate.currentDate())

        # Refresh live-commit sections from DB
        self._refresh_tags()
        self._refresh_prereqs()
        self._refresh_links()
        self._populate_prereq_combo()

        # Show edit-only sections
        self._links_section.setVisible(True)
        self._danger_section.setVisible(True)

        self._title_input.setFocus()

    # -- back / save -----------------------------------------------------------

    def _on_back(self) -> None:
        if self._mode == "edit" and self._task and self._task.id is not None:
            # Auto-save basic fields since tags/prereqs/links are already committed
            if self._title_input.text().strip():
                self._save_basic_fields()
            self.closed.emit()  # start slide-out animation first
            QTimer.singleShot(0, self.task_saved.emit)  # yield to event loop before refresh
        else:
            self.closed.emit()

    def _on_save(self) -> None:
        if self._mode == "create":
            self._save_create()
        else:
            self._save_edit()

    def _save_create(self) -> None:
        title = self._title_input.text().strip()
        if not title:
            return
        project_id = self._project_combo.currentData()
        if project_id is None:
            return

        due = self._get_due_date()
        description = self._desc_input.toPlainText().strip()

        create_task_with_relations(
            project_id=project_id,
            title=title,
            description=description,
            priority=self._priority_spin.value(),
            due_date=due,
            tags=list(self._pending_tags),
            prerequisites=[pid for pid, _ in self._pending_prereqs],
        )
        self.closed.emit()  # start slide-out animation first
        QTimer.singleShot(0, self.task_saved.emit)  # yield to event loop before refresh

    def _save_edit(self) -> None:
        if self._task is None or self._task.id is None:
            return
        self._save_basic_fields()
        self.closed.emit()  # start slide-out animation first
        QTimer.singleShot(0, self.task_saved.emit)  # yield to event loop before refresh

    def _save_basic_fields(self) -> None:
        """Save title, description, priority, due_date for the current task."""
        if self._task is None or self._task.id is None:
            return
        due = self._get_due_date()
        update_task(
            self._task.id,
            title=self._title_input.text().strip(),
            description=self._desc_input.toPlainText().strip(),
            priority=self._priority_spin.value(),
            due_date=due,
        )

    def _get_due_date(self) -> datetime | None:
        if self._due_check.isChecked():
            qd = self._due_date.date()
            return datetime(qd.year(), qd.month(), qd.day())
        return None

    # -- delete ----------------------------------------------------------------

    def _on_delete(self) -> None:
        if self._task is None or self._task.id is None:
            return
        dlg = ConfirmDialog(
            "Delete Task",
            f'Delete "{truncate_title(self._task.title, 40)}"? This cannot be undone.',
            self.window(),
        )
        if dlg.exec():
            delete_task(self._task.id)
            self.closed.emit()  # start slide-out animation first
            QTimer.singleShot(0, self.task_saved.emit)  # yield to event loop before refresh

    # -- tags ------------------------------------------------------------------

    def _add_tag(self) -> None:
        name = self._tag_input.text().strip()
        if not name:
            return
        self._tag_input.clear()

        if self._mode == "edit" and self._task and self._task.id is not None:
            # Live commit
            add_tag_to_task(self._task.id, name)
            self._refresh_tags()
        else:
            # Pending for create
            if name not in self._pending_tags:
                self._pending_tags.append(name)
                self._rebuild_tags_flow()

    def _remove_tag(self, tag_name: str) -> None:
        if self._mode == "edit" and self._task and self._task.id is not None:
            remove_tag_from_task(self._task.id, tag_name)
            self._refresh_tags()
        else:
            if tag_name in self._pending_tags:
                self._pending_tags.remove(tag_name)
                self._rebuild_tags_flow()

    def _refresh_tags(self) -> None:
        """Rebuild tag chips from DB (edit mode)."""
        clear_flow(self._tags_flow)
        if self._task is None or self._task.id is None:
            return
        tags = get_task_tags(self._task.id)
        for tag_name in tags:
            chip = make_removable_chip(tag_name, lambda _n=tag_name: self._remove_tag(_n))
            self._tags_flow.addWidget(chip)
        self._tags_flow.addStretch()

    def _rebuild_tags_flow(self) -> None:
        """Rebuild tag chips from pending list (create mode)."""
        clear_flow(self._tags_flow)
        for tag_name in self._pending_tags:
            chip = make_removable_chip(tag_name, lambda _n=tag_name: self._remove_tag(_n))
            self._tags_flow.addWidget(chip)
        self._tags_flow.addStretch()

    # -- prerequisites ---------------------------------------------------------

    def _populate_prereq_combo(self) -> None:
        self._prereq_combo.clear()
        self._prereq_combo.addItem("Select prerequisite...", None)
        if self._board_id is None:
            return
        tasks = get_tasks_by_board(self._board_id)
        existing_ids: set[int] = set()
        if self._mode == "edit" and self._task and self._task.id is not None:
            existing_ids = {
                pt.id for pt in get_prerequisite_tasks(self._task.id) if pt.id is not None
            }
            existing_ids.add(self._task.id)  # exclude self
        else:
            existing_ids = {pid for pid, _ in self._pending_prereqs}
        for t in tasks:
            if t.id is not None and not t.is_completed and t.id not in existing_ids:
                self._prereq_combo.addItem(t.title, t.id)

    def _add_prereq(self) -> None:
        prereq_id = self._prereq_combo.currentData()
        if prereq_id is None:
            return
        title = self._prereq_combo.currentText()

        if self._mode == "edit" and self._task and self._task.id is not None:
            add_prerequisite(self._task.id, prereq_id)
            idx = self._prereq_combo.currentIndex()
            self._prereq_combo.removeItem(idx)
            self._prereq_combo.setCurrentIndex(0)
            self._refresh_prereqs()
        else:
            if any(pid == prereq_id for pid, _ in self._pending_prereqs):
                return
            self._pending_prereqs.append((prereq_id, title))
            idx = self._prereq_combo.currentIndex()
            self._prereq_combo.removeItem(idx)
            self._prereq_combo.setCurrentIndex(0)
            self._rebuild_prereqs_flow()

    def _remove_prereq(self, prereq_task_id: int) -> None:
        if self._mode == "edit" and self._task and self._task.id is not None:
            remove_prerequisite(self._task.id, prereq_task_id)
            task = get_task(prereq_task_id)
            if task and not task.is_completed:
                self._prereq_combo.addItem(task.title, task.id)
            self._refresh_prereqs()
        else:
            removed_title = ""
            new_list = []
            for pid, t in self._pending_prereqs:
                if pid == prereq_task_id:
                    removed_title = t
                else:
                    new_list.append((pid, t))
            self._pending_prereqs = new_list
            if removed_title:
                self._prereq_combo.addItem(removed_title, prereq_task_id)
            self._rebuild_prereqs_flow()

    def _refresh_prereqs(self) -> None:
        """Rebuild prereq chips from DB (edit mode)."""
        clear_layout(self._prereqs_flow)
        if self._task is None or self._task.id is None:
            return
        prereqs = get_prerequisite_tasks(self._task.id)
        for pt in prereqs:
            text = f"{truncate_title(pt.title)} \u2192 this"
            chip = make_removable_chip(text, lambda _pid=pt.id: self._remove_prereq(_pid))
            self._prereqs_flow.addWidget(chip)

    def _rebuild_prereqs_flow(self) -> None:
        """Rebuild prereq chips from pending list (create mode)."""
        clear_layout(self._prereqs_flow)
        for task_id, title in self._pending_prereqs:
            text = f"{truncate_title(title)} \u2192 this"
            chip = make_removable_chip(text, lambda _pid=task_id: self._remove_prereq(_pid))
            self._prereqs_flow.addWidget(chip)

    # -- links -----------------------------------------------------------------

    def _add_link(self) -> None:
        if self._task is None or self._task.id is None:
            return
        url = self._url_input.text().strip()
        if not url:
            self._link_error.setText("URL cannot be empty.")
            self._link_error.show()
            return
        self._link_error.hide()
        label = self._label_input.text().strip() or None
        add_link(self._task.id, url, label)
        self._url_input.clear()
        self._label_input.clear()
        self._refresh_links()

    def _delete_link(self, link_id: int) -> None:
        delete_link(link_id)
        self._refresh_links()

    def _refresh_links(self) -> None:
        """Rebuild link rows from DB."""
        clear_layout(self._links_container)
        if self._task is None or self._task.id is None:
            return
        links = get_links_for_task(self._task.id)
        for link in links:
            row = QHBoxLayout()
            row.setSpacing(8)
            icon = "\U0001f5c2" if link.link_type == "file" else "\U0001f517"
            display = link.label if link.label else link.url
            if len(display) > 50:
                display = display[:49] + "\u2026"
            lbl = QLabel(f"{icon} {display}")
            lbl.setToolTip(link.url)
            del_btn = QPushButton("\u2715")
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
