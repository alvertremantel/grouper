"""
activity_config.py — Full-width configuration panel for activities and groups.

Replaces the old EditActivitiesDialog with a two-column layout:
  Left:  Group browser with collapsible sections
  Right: Activity detail editor (name, groups, tags, delete)
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...database.activities import (
    add_activity_group,
    archive_activity,
    create_group,
    delete_group,
    get_activities_by_group,
    get_activity_by_id,
    get_all_groups,
    get_ungrouped_activities,
    list_all_groups,
    remove_activity_group,
    rename_activity_by_id,
    rename_group,
    soft_delete_activity,
    unarchive_activity,
)
from ...database.tags import (
    add_tag_to_activity,
    list_tags,
    remove_tag_from_activity,
)
from ...models import Activity, Group
from ..shared.widgets import clear_flow, clear_layout, make_removable_chip

# ---------------------------------------------------------------------------
# ActivityConfigPanel — top-level widget
# ---------------------------------------------------------------------------


class ActivityConfigPanel(QWidget):
    """Full-width activity/group management panel.

    Signals:
        closed:       Back button clicked; parent should slide back.
        data_changed: Any mutation occurred; parent should refresh quadrants.
    """

    closed = Signal()
    data_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selected_activity_id: int | None = None
        self._build()

    # -- layout --------------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(20)

        # Header row
        header = QHBoxLayout()
        back_btn = QPushButton("\u2190 Back to Time Tracker")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.closed.emit)
        header.addWidget(back_btn)

        title = QLabel("Activity Configuration")
        title.setProperty("heading", True)
        header.addWidget(title)
        header.addStretch()
        outer.addLayout(header)

        # Splitter gets all remaining space
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # -- Left: group browser --
        left = QFrame()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 8, 0)
        left_lay.setSpacing(10)

        groups_header = QHBoxLayout()
        groups_label = QLabel("GROUPS")
        groups_label.setObjectName("sectionHeader")
        groups_header.addWidget(groups_label)
        groups_header.addStretch()

        new_group_btn = QPushButton("+ New Group")
        new_group_btn.setObjectName("addButton")
        new_group_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_group_btn.clicked.connect(self._start_new_group)
        groups_header.addWidget(new_group_btn)
        left_lay.addLayout(groups_header)

        # Inline new-group input (hidden by default)
        self._new_group_input = QLineEdit()
        self._new_group_input.setObjectName("transparentInput")
        self._new_group_input.setPlaceholderText("Group name\u2026")
        self._new_group_input.returnPressed.connect(self._commit_new_group)
        self._new_group_input.hide()
        left_lay.addWidget(self._new_group_input)

        # Scrollable group list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._groups_container = QWidget()
        self._groups_layout = QVBoxLayout(self._groups_container)
        self._groups_layout.setContentsMargins(0, 0, 0, 0)
        self._groups_layout.setSpacing(8)
        self._groups_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._groups_container)
        left_lay.addWidget(scroll)

        splitter.addWidget(left)

        # -- Right: activity detail editor --
        right = QFrame()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(8, 0, 0, 0)
        right_lay.setSpacing(0)

        self._detail_placeholder = QLabel("Select an activity to edit")
        self._detail_placeholder.setObjectName("infoLabel")
        self._detail_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_lay.addWidget(self._detail_placeholder)

        self._detail_editor = _ActivityDetailEditor()
        self._detail_editor.data_changed.connect(self._on_detail_changed)
        self._detail_editor.hide()
        right_lay.addWidget(self._detail_editor)
        right_lay.addStretch()

        splitter.addWidget(right)
        splitter.setSizes([350, 550])
        outer.addWidget(splitter, stretch=1)

    # -- public API -----------------------------------------------------------

    def refresh(self) -> None:
        """Rebuild the entire panel from database state."""
        self._rebuild_group_browser()
        if self._selected_activity_id is not None:
            act = get_activity_by_id(self._selected_activity_id)
            if act and not act.is_deleted:
                self._detail_editor.load(act)
                self._detail_editor.show()
                self._detail_placeholder.hide()
            else:
                self._selected_activity_id = None
                self._detail_editor.hide()
                self._detail_placeholder.show()
        else:
            self._detail_editor.hide()
            self._detail_placeholder.show()

    # -- group browser --------------------------------------------------------

    def _rebuild_group_browser(self) -> None:
        clear_layout(self._groups_layout)
        groups = list_all_groups()
        for group in groups:
            section = _GroupSection(group)
            section.activity_clicked.connect(self._select_activity)
            section.group_renamed.connect(self._on_group_renamed)
            section.group_deleted.connect(self._on_group_deleted)
            self._groups_layout.addWidget(section)

        # Ungrouped section
        ungrouped = get_ungrouped_activities()
        if ungrouped:
            section = _UngroupedSection(ungrouped)
            section.activity_clicked.connect(self._select_activity)
            self._groups_layout.addWidget(section)

    def _start_new_group(self) -> None:
        self._new_group_input.clear()
        self._new_group_input.show()
        self._new_group_input.setFocus()

    def _commit_new_group(self) -> None:
        name = self._new_group_input.text().strip()
        self._new_group_input.hide()
        self._new_group_input.clear()
        if name:
            try:
                create_group(name)
            except Exception:
                return  # duplicate or invalid
            self._rebuild_group_browser()
            self.data_changed.emit()

    # -- activity selection ---------------------------------------------------

    def _select_activity(self, activity_id: int) -> None:
        self._selected_activity_id = activity_id
        act = get_activity_by_id(activity_id)
        if act is None:
            return
        self._detail_editor.load(act)
        self._detail_editor.show()
        self._detail_placeholder.hide()

    # -- mutation callbacks ---------------------------------------------------

    def _on_detail_changed(self) -> None:
        self._rebuild_group_browser()
        self.data_changed.emit()

    def _on_group_renamed(self) -> None:
        self._rebuild_group_browser()
        if self._selected_activity_id is not None:
            act = get_activity_by_id(self._selected_activity_id)
            if act:
                self._detail_editor.load(act)
        self.data_changed.emit()

    def _on_group_deleted(self) -> None:
        self._rebuild_group_browser()
        if self._selected_activity_id is not None:
            act = get_activity_by_id(self._selected_activity_id)
            if act:
                self._detail_editor.load(act)
        self.data_changed.emit()


# ---------------------------------------------------------------------------
# _GroupSection — collapsible group with its member activities
# ---------------------------------------------------------------------------


class _GroupSection(QFrame):
    """A single group in the browser: header (name + rename/delete) + activity list."""

    activity_clicked = Signal(int)
    group_renamed = Signal()
    group_deleted = Signal()

    def __init__(self, group: Group, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._group = group
        self._collapsed = False
        self._armed_delete = False
        self.setObjectName("card")
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        # Header row
        header = QHBoxLayout()
        header.setSpacing(6)

        self._name_label = QLabel(self._group.name)
        self._name_label.setObjectName("sectionHeader")
        self._name_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._name_label.installEventFilter(self)
        header.addWidget(self._name_label)

        self._name_input = QLineEdit(self._group.name)
        self._name_input.setObjectName("transparentInput")
        self._name_input.editingFinished.connect(self._commit_rename)
        self._name_input.hide()
        header.addWidget(self._name_input)

        header.addStretch()

        # Activity count
        activities = get_activities_by_group(self._group.name)
        count_lbl = QLabel(f"({len(activities)})")
        count_lbl.setObjectName("infoLabel")
        header.addWidget(count_lbl)

        self._delete_btn = QPushButton("\u00d7")
        self._delete_btn.setObjectName("removeButton")
        self._delete_btn.setFixedSize(22, 22)
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.setToolTip("Delete group")
        self._delete_btn.clicked.connect(self._on_delete_click)
        self._delete_btn.installEventFilter(self)
        header.addWidget(self._delete_btn)

        lay.addLayout(header)

        self._delete_warning = QLabel("Double-click to confirm")
        self._delete_warning.setObjectName("dangerLabel")
        self._delete_warning.hide()
        lay.addWidget(self._delete_warning)

        # Activity list
        self._activity_container = QWidget()
        self._activity_layout = QVBoxLayout(self._activity_container)
        self._activity_layout.setContentsMargins(12, 0, 0, 0)
        self._activity_layout.setSpacing(2)

        for act in activities:
            btn = QPushButton(act.name)
            btn.setObjectName("transparentInput")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("text-align: left; padding: 4px 8px;")
            btn.clicked.connect(lambda _=False, aid=act.id: self.activity_clicked.emit(aid))
            self._activity_layout.addWidget(btn)

        if not activities:
            empty = QLabel("No activities")
            empty.setObjectName("infoLabel")
            self._activity_layout.addWidget(empty)

        lay.addWidget(self._activity_container)

    # -- rename (double-click header) -----------------------------------------

    def eventFilter(self, obj: QWidget, event: QEvent) -> bool:  # type: ignore[override]
        if obj is self._name_label and event.type() == QEvent.Type.MouseButtonDblClick:
            self._start_rename()
            return True
        if (
            obj is self._delete_btn
            and event.type() == QEvent.Type.MouseButtonDblClick
            and self._armed_delete
        ):
            delete_group(self._group.id)  # type: ignore[arg-type]
            self.group_deleted.emit()
            return True
        return super().eventFilter(obj, event)

    def _start_rename(self) -> None:
        self._name_label.hide()
        self._name_input.setText(self._group.name)
        self._name_input.show()
        self._name_input.setFocus()
        self._name_input.selectAll()

    def _commit_rename(self) -> None:
        new_name = self._name_input.text().strip()
        self._name_input.hide()
        self._name_label.show()
        if new_name and new_name != self._group.name and rename_group(self._group.id, new_name):  # type: ignore[arg-type]
            self._group.name = new_name
            self._name_label.setText(new_name)
            self.group_renamed.emit()

    # -- delete (two-stage) ---------------------------------------------------

    def _on_delete_click(self) -> None:
        self._armed_delete = True
        self._delete_btn.setText("Confirm")
        self._delete_btn.setObjectName("dangerButton")
        self._delete_btn.setFixedSize(self._delete_btn.sizeHint())
        self._delete_btn.style().unpolish(self._delete_btn)
        self._delete_btn.style().polish(self._delete_btn)
        self._delete_warning.show()


# ---------------------------------------------------------------------------
# _UngroupedSection — activities with no group membership
# ---------------------------------------------------------------------------


class _UngroupedSection(QFrame):
    """Lists activities that belong to no group."""

    activity_clicked = Signal(int)

    def __init__(self, activities: list[Activity], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        header = QLabel("UNGROUPED")
        header.setObjectName("sectionHeader")
        lay.addWidget(header)

        container = QWidget()
        clayout = QVBoxLayout(container)
        clayout.setContentsMargins(12, 0, 0, 0)
        clayout.setSpacing(2)

        for act in activities:
            btn = QPushButton(act.name)
            btn.setObjectName("transparentInput")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("text-align: left; padding: 4px 8px;")
            btn.clicked.connect(lambda _=False, aid=act.id: self.activity_clicked.emit(aid))
            clayout.addWidget(btn)

        lay.addWidget(container)


# ---------------------------------------------------------------------------
# _ActivityDetailEditor — right-column activity editor
# ---------------------------------------------------------------------------


class _ActivityDetailEditor(QFrame):
    """Editable detail view for a selected activity."""

    data_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._activity: Activity | None = None
        self._armed_delete = False
        self.setObjectName("card")
        self._build()

    def _build(self) -> None:
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(16, 16, 16, 16)
        self._outer.setSpacing(16)

        # -- Name section --
        name_section = QVBoxLayout()
        name_section.setSpacing(4)
        name_lbl = QLabel("Name")
        name_lbl.setObjectName("infoLabel")
        name_section.addWidget(name_lbl)

        self._name_input = QLineEdit()
        self._name_input.setObjectName("transparentInput")
        self._name_input.editingFinished.connect(self._rename_activity)
        name_section.addWidget(self._name_input)
        self._outer.addLayout(name_section)

        # -- Groups section --
        groups_section = QVBoxLayout()
        groups_section.setSpacing(4)
        groups_lbl = QLabel("Groups")
        groups_lbl.setObjectName("infoLabel")
        groups_section.addWidget(groups_lbl)

        self._groups_flow = QHBoxLayout()
        self._groups_flow.setSpacing(4)
        self._groups_flow.setContentsMargins(0, 0, 0, 0)
        groups_section.addLayout(self._groups_flow)

        add_group_btn = QPushButton("+ Add Group")
        add_group_btn.setObjectName("addButton")
        add_group_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_group_btn.clicked.connect(self._add_group)
        groups_section.addWidget(add_group_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._group_warning = QLabel("No groups — activity won't appear in any quadrant")
        self._group_warning.setObjectName("dangerLabel")
        self._group_warning.hide()
        groups_section.addWidget(self._group_warning)

        self._outer.addLayout(groups_section)

        # -- Tags section --
        tags_section = QVBoxLayout()
        tags_section.setSpacing(4)
        tags_lbl = QLabel("Tags")
        tags_lbl.setObjectName("infoLabel")
        tags_section.addWidget(tags_lbl)

        self._tags_flow = QHBoxLayout()
        self._tags_flow.setSpacing(4)
        self._tags_flow.setContentsMargins(0, 0, 0, 0)
        tags_section.addLayout(self._tags_flow)

        add_tag_btn = QPushButton("+ Add Tag")
        add_tag_btn.setObjectName("addButton")
        add_tag_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_tag_btn.clicked.connect(self._add_tag)
        tags_section.addWidget(add_tag_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._outer.addLayout(tags_section)

        # -- Danger zone --
        self._outer.addSpacing(24)
        danger_header = QLabel("Danger Zone")
        danger_header.setObjectName("infoLabel")
        self._outer.addWidget(danger_header)

        danger_row = QHBoxLayout()
        danger_row.setSpacing(8)

        self._archive_btn = QPushButton("Archive")
        self._archive_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._archive_btn.clicked.connect(self._toggle_archive)
        danger_row.addWidget(self._archive_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setObjectName("dangerButton")
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.clicked.connect(self._on_delete_click)
        self._delete_btn.installEventFilter(self)
        danger_row.addWidget(self._delete_btn)

        danger_row.addStretch()
        self._outer.addLayout(danger_row)

        self._delete_warning = QLabel("Double-click to confirm deletion")
        self._delete_warning.setObjectName("dangerLabel")
        self._delete_warning.hide()
        self._outer.addWidget(self._delete_warning)

        self._outer.addStretch()

    # -- load activity --------------------------------------------------------

    def load(self, activity: Activity) -> None:
        """Populate the editor with the given activity's data."""
        self._activity = activity
        self._armed_delete = False
        self._delete_btn.setText("Delete")
        self._delete_btn.setProperty("armed", False)
        self._delete_btn.style().unpolish(self._delete_btn)
        self._delete_btn.style().polish(self._delete_btn)
        self._delete_warning.hide()

        self._name_input.setText(activity.name)

        # Archive button label
        if activity.is_archived:
            self._archive_btn.setText("Unarchive")
        else:
            self._archive_btn.setText("Archive")

        self._rebuild_groups()
        self._rebuild_tags()

    # -- groups ---------------------------------------------------------------

    def _rebuild_groups(self) -> None:
        clear_flow(self._groups_flow)
        if self._activity is None:
            return
        for gname in self._activity.groups:
            chip = make_removable_chip(gname, lambda _g=gname: self._remove_group(_g))
            self._groups_flow.addWidget(chip)
        self._groups_flow.addStretch()
        self._group_warning.setVisible(len(self._activity.groups) == 0)

    def _add_group(self) -> None:
        if self._activity is None:
            return
        if len(self._activity.groups) >= 3:
            self._group_warning.setText("Maximum 3 groups per activity")
            self._group_warning.show()
            return
        from ..tasks.dialogs import AddGroupDialog

        all_groups = get_all_groups()
        dlg = AddGroupDialog(all_groups, self._activity.groups, self)
        if (
            dlg.exec()
            and dlg.selected_group
            and add_activity_group(self._activity.id, dlg.selected_group)
        ):  # type: ignore[arg-type]
            self._activity.groups.append(dlg.selected_group)
            self._rebuild_groups()
            self.data_changed.emit()

    def _remove_group(self, group_name: str) -> None:
        if self._activity is None:
            return
        remove_activity_group(self._activity.id, group_name)  # type: ignore[arg-type]
        self._activity.groups = [g for g in self._activity.groups if g != group_name]
        self._rebuild_groups()
        self.data_changed.emit()

    # -- tags -----------------------------------------------------------------

    def _rebuild_tags(self) -> None:
        clear_flow(self._tags_flow)
        if self._activity is None:
            return
        for tname in self._activity.tags:
            chip = make_removable_chip(tname, lambda _t=tname: self._remove_tag(_t))
            self._tags_flow.addWidget(chip)
        self._tags_flow.addStretch()

    def _add_tag(self) -> None:
        if self._activity is None:
            return
        from ..tasks.dialogs import AddGroupDialog

        all_tags = [t.name for t in list_tags()]
        dlg = AddGroupDialog(
            all_tags,
            self._activity.tags,
            self,
            title="Add Tag",
            item_label="tag",
            limit_hint=None,
        )
        if (
            dlg.exec()
            and dlg.selected_group
            and add_tag_to_activity(self._activity.id, dlg.selected_group)
        ):  # type: ignore[arg-type]
            self._activity.tags.append(dlg.selected_group)
            self._rebuild_tags()
            self.data_changed.emit()

    def _remove_tag(self, tag_name: str) -> None:
        if self._activity is None:
            return
        remove_tag_from_activity(self._activity.id, tag_name)  # type: ignore[arg-type]
        self._activity.tags = [t for t in self._activity.tags if t != tag_name]
        self._rebuild_tags()
        self.data_changed.emit()

    # -- rename / archive / delete -------------------------------------------

    def _rename_activity(self) -> None:
        if self._activity is None:
            return
        new_name = self._name_input.text().strip()
        if new_name and new_name != self._activity.name:
            rename_activity_by_id(self._activity.id, new_name)  # type: ignore[arg-type]
            self._activity.name = new_name
            self.data_changed.emit()
        else:
            self._name_input.setText(self._activity.name)
        self._name_input.clearFocus()

    def _toggle_archive(self) -> None:
        if self._activity is None:
            return
        if self._activity.is_archived:
            unarchive_activity(self._activity.id)  # type: ignore[arg-type]
            self._activity.is_archived = False
            self._archive_btn.setText("Archive")
        else:
            archive_activity(self._activity.id)  # type: ignore[arg-type]
            self._activity.is_archived = True
            self._archive_btn.setText("Unarchive")
        self.data_changed.emit()

    def _on_delete_click(self) -> None:
        self._armed_delete = True
        self._delete_btn.setProperty("armed", True)
        self._delete_btn.style().unpolish(self._delete_btn)
        self._delete_btn.style().polish(self._delete_btn)
        self._delete_btn.setText("Confirm Delete")
        self._delete_warning.show()

    def eventFilter(self, obj: QWidget, event: QEvent) -> bool:  # type: ignore[override]
        if (
            obj is self._delete_btn
            and event.type() == QEvent.Type.MouseButtonDblClick
            and self._armed_delete
            and self._activity is not None
        ):
            soft_delete_activity(self._activity.id)  # type: ignore[arg-type]
            self._activity = None
            self.hide()
            self.data_changed.emit()
            return True
        return super().eventFilter(obj, event)
