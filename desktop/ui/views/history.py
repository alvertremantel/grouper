"""
history.py — Completed tasks and past sessions feed.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...database import get_sessions
from ...database.connection import get_notifier
from ...database.projects import list_projects
from ...database.sessions import delete_session
from ...database.tasks import get_completed_tasks
from ..shared.base_card import BaseCard
from ..shared.icons import get_themed_icon
from ..shared.widget_pool import WidgetPool
from ..shared.widgets import reconnect


class _TaskHistoryCard(BaseCard):
    """Reusable card for a completed task row."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = self._make_row()
        lay.setSpacing(10)

        check_lbl = QLabel("✓")
        check_lbl.setObjectName("successLabel")
        lay.addWidget(check_lbl)

        self._title = QLabel()
        self._title.setObjectName("completedLabel")
        lay.addWidget(self._title, stretch=1)

        self._proj_lbl = QLabel()
        self._proj_lbl.setObjectName("smallMuted")
        lay.addWidget(self._proj_lbl)

        self._when_lbl = QLabel()
        self._when_lbl.setObjectName("smallMuted")
        lay.addWidget(self._when_lbl)

    def populate(self, task, proj_name: str, when_text: str) -> None:
        self._title.setText(task.title)
        self._proj_lbl.setText(proj_name)
        self._proj_lbl.setVisible(bool(proj_name))
        self._when_lbl.setText(when_text)
        self._when_lbl.setVisible(bool(when_text))


class _SessionHistoryCard(BaseCard):
    """Reusable card for a past session row."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = self._make_row()
        lay.setSpacing(10)

        self._name_lbl = QLabel()
        self._name_lbl.setObjectName("cardTitle")
        lay.addWidget(self._name_lbl)

        self._dur_lbl = QLabel()
        self._dur_lbl.setObjectName("accentLabel")
        lay.addWidget(self._dur_lbl)

        self._when_lbl = QLabel()
        self._when_lbl.setObjectName("smallMuted")
        lay.addWidget(self._when_lbl)

        lay.addStretch()

        self._notes_lbl = QLabel()
        self._notes_lbl.setObjectName("smallMuted")
        lay.addWidget(self._notes_lbl)

        self._del_btn = QPushButton()
        self._del_btn.setIcon(get_themed_icon("trash"))
        self._del_btn.setFixedSize(28, 28)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setToolTip("Delete Session")
        self._del_btn.setObjectName("iconButton")
        lay.addWidget(self._del_btn)

    def populate(self, session, on_delete: Callable[[int], None]) -> None:
        self._name_lbl.setText(f"⏱  {session.activity_name}")
        self._dur_lbl.setText(session.format_duration())
        when = session.start_time.strftime("%b %d, %H:%M") if session.start_time else ""
        self._when_lbl.setText(when)
        self._when_lbl.setVisible(bool(when))
        notes = session.notes[:40] if session.notes else ""
        self._notes_lbl.setText(notes)
        self._notes_lbl.setVisible(bool(notes))
        reconnect(self._del_btn.clicked, lambda: on_delete(session.id))


class HistoryView(QWidget):
    """History view with tabs for completed tasks and past sessions."""

    def __init__(self, parent=None) -> None:
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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._dirty:
            self._dirty = False
            self.refresh()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        heading = QLabel("History")
        heading.setProperty("heading", True)
        outer.addWidget(heading)

        self._tabs = QTabWidget()

        # Completed tasks tab
        self._tasks_tab = QWidget()
        self._tasks_layout = QVBoxLayout(self._tasks_tab)
        self._tasks_layout.setContentsMargins(8, 8, 8, 8)
        self._tasks_layout.setSpacing(4)
        self._tasks_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        tasks_scroll = QScrollArea()
        tasks_scroll.setWidgetResizable(True)
        tasks_scroll.setFrameShape(QFrame.Shape.NoFrame)
        tasks_scroll.setWidget(self._tasks_tab)
        self._tabs.addTab(tasks_scroll, "✓ Completed Tasks")

        # Sessions tab
        self._sessions_tab = QWidget()
        self._sessions_layout = QVBoxLayout(self._sessions_tab)
        self._sessions_layout.setContentsMargins(8, 8, 8, 8)
        self._sessions_layout.setSpacing(4)
        self._sessions_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        sessions_scroll = QScrollArea()
        sessions_scroll.setWidgetResizable(True)
        sessions_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sessions_scroll.setWidget(self._sessions_tab)
        self._tabs.addTab(sessions_scroll, "⏱ Time Sessions")

        outer.addWidget(self._tabs)

        # Pre-allocate widget pools
        self._task_pool: WidgetPool[_TaskHistoryCard] = WidgetPool(
            factory=_TaskHistoryCard,
            layout=self._tasks_layout,
            initial=12,
        )
        self._tasks_empty = QLabel("No completed tasks yet.")
        self._tasks_empty.setObjectName("emptyMessage")
        self._tasks_layout.addWidget(self._tasks_empty)

        self._session_pool: WidgetPool[_SessionHistoryCard] = WidgetPool(
            factory=_SessionHistoryCard,
            layout=self._sessions_layout,
            initial=12,
        )
        self._sessions_empty = QLabel("No recorded sessions yet.")
        self._sessions_empty.setObjectName("emptyMessage")
        self._sessions_layout.addWidget(self._sessions_empty)

    def refresh(self) -> None:
        self.setUpdatesEnabled(False)
        try:
            self._refresh_tasks()
            self._refresh_sessions()
        finally:
            self.setUpdatesEnabled(True)

    def _refresh_tasks(self) -> None:
        tasks = get_completed_tasks()[:50]
        projects = {p.id: p for p in list_projects()}
        self._task_pool.begin_update()
        for t in tasks:
            card = self._task_pool.acquire()
            proj = projects.get(t.project_id)
            proj_name = proj.name if proj else ""
            when_text = t.completed_at.strftime("%b %d, %H:%M") if t.completed_at else ""
            card.populate(t, proj_name, when_text)
        self._tasks_empty.setVisible(len(tasks) == 0)

    def _refresh_sessions(self) -> None:
        sessions = get_sessions(limit=50)
        self._session_pool.begin_update()
        for s in sessions:
            card = self._session_pool.acquire()
            card.populate(s, on_delete=self._delete_session)
        self._sessions_empty.setVisible(len(sessions) == 0)

    def _delete_session(self, session_id: int) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Session",
            "Delete this session? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_session(session_id)
            self.refresh()
