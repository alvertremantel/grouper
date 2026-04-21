"""
timeline_view.py — Rolling N-day timeline with card-based items and drag-drop.

Replaces the old flat agenda feed.  Each day in the selected range (30/60/90)
gets a section with a date header, event/task cards, and action buttons for
adding new items.  Cards can be dragged between days to reschedule.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from PySide6.QtCore import QByteArray, QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QDrag, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..config import get_config
from ..database.calendars import list_calendars
from ..database.connection import get_notifier
from ..database.events import create_event, list_events_for_range, update_event
from ..database.projects import list_projects
from ..database.tasks import create_task, get_tasks_with_due_dates, update_task
from ..models import Event, Task
from ..styles import TASK_COLOR, theme_colors
from .event_dialog import EventDialog
from .icons import get_themed_icon
from .mime_types import TIMELINE_EVENT_MIME, TIMELINE_TASK_MIME
from .widgets import SegmentedControl, clear_layout

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RANGE_OPTIONS = [30, 60, 90]
_RANGE_LABELS = ["30 days", "60 days", "90 days"]

# ---------------------------------------------------------------------------
# Task quick-add dialog
# ---------------------------------------------------------------------------


class _TaskQuickAddDialog(QDialog):
    """Minimal dialog for creating a scheduled task from the timeline."""

    def __init__(self, prefill_date: date, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Scheduled Task")
        self.setMinimumWidth(340)
        self._prefill_date = prefill_date

        form = QFormLayout(self)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Task title")
        form.addRow("Title:", self._title_edit)

        self._project_combo = QComboBox()
        projects = list_projects()
        for p in projects:
            self._project_combo.addItem(p.name, p.id)
        form.addRow("Project:", self._project_combo)

        date_lbl = QLabel(prefill_date.strftime("%B %d, %Y"))
        date_lbl.setEnabled(False)
        form.addRow("Due date:", date_lbl)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        if not projects:
            ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
            if ok_btn:
                ok_btn.setEnabled(False)
            self._project_combo.setPlaceholderText("No projects available")

        self._title_edit.setFocus()

    def get_values(self) -> dict:
        return {
            "title": self._title_edit.text().strip(),
            "project_id": self._project_combo.currentData(),
            "due_date": datetime(
                self._prefill_date.year,
                self._prefill_date.month,
                self._prefill_date.day,
            ),
        }


# ---------------------------------------------------------------------------
# Timeline card (draggable)
# ---------------------------------------------------------------------------


class _TimelineCard(QFrame):
    """A rounded card representing a single Task or Event."""

    clicked = Signal(object)  # emits the Task or Event

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("timelineCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(10, 6, 10, 6)
        self._lay.setSpacing(8)

        # Color dot
        self._dot = QLabel()
        self._dot.setFixedSize(10, 10)
        self._lay.addWidget(self._dot, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Time label
        self._time_lbl = QLabel()
        self._time_lbl.setObjectName("timelineCardTime")
        self._time_lbl.setFixedWidth(105)
        self._lay.addWidget(self._time_lbl)

        # Title
        self._title_lbl = QLabel()
        self._title_lbl.setObjectName("timelineCardTitle")
        self._lay.addWidget(self._title_lbl, stretch=1)

        self._item: Task | Event | None = None
        self._drag_start_pos: QPoint | None = None

    def populate(
        self,
        item: Task | Event,
        cal_colors: dict[int, str],
        accent_color: str,
    ) -> None:
        """Fill the card with data from *item*."""
        self._item = item

        if isinstance(item, Task):
            dot_color = TASK_COLOR
            time_text = "All day"
            title = item.title
        else:
            dot_color = item.color or cal_colors.get(item.calendar_id, accent_color)
            if item.all_day:
                time_text = "All day"
            elif item.start_dt:
                start = item.start_dt.strftime("%I:%M%p").lstrip("0").lower()
                end = item.end_dt.strftime("%I:%M%p").lstrip("0").lower() if item.end_dt else ""
                time_text = f"{start} - {end}" if end else start
            else:
                time_text = ""
            title = item.title

        self._dot.setStyleSheet(f"background: {dot_color}; border-radius: 5px; border: none;")
        self._time_lbl.setText(time_text)
        self._title_lbl.setText(title)
        self._title_lbl.setToolTip(title)

    # -- Drag support --------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_start_pos is not None
            and self._item is not None
            and (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            drag = QDrag(self)
            mime = QMimeData()

            if isinstance(self._item, Task):
                mime.setData(
                    TIMELINE_TASK_MIME,
                    QByteArray(str(self._item.id).encode()),
                )
            else:
                start_iso = self._item.start_dt.isoformat() if self._item.start_dt else ""
                end_iso = self._item.end_dt.isoformat() if self._item.end_dt else ""
                payload = f"{self._item.id}|{start_iso}|{end_iso}"
                mime.setData(
                    TIMELINE_EVENT_MIME,
                    QByteArray(payload.encode()),
                )

            drag.setMimeData(mime)

            # Semi-transparent drag pixmap
            pixmap = QPixmap(self.size())
            self.render(pixmap)
            pixmap.setDevicePixelRatio(self.devicePixelRatioF())
            drag.setPixmap(pixmap)
            drag.setHotSpot(event.position().toPoint())
            drag.exec(Qt.DropAction.MoveAction)
            self._drag_start_pos = None

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._drag_start_pos is not None
            and self._item is not None
        ):
            # Click (not drag) — emit clicked
            self.clicked.emit(self._item)
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# Day section (drop target)
# ---------------------------------------------------------------------------


class _DaySection(QFrame):
    """One day's slice: date header, cards, action buttons.  Accepts drops."""

    item_dropped = Signal()  # emitted after a successful drop reschedule
    add_event_requested = Signal(object)  # date
    add_task_requested = Signal(object)  # date
    card_clicked = Signal(object)  # Task | Event

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("timelineDaySection")
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._day: date | None = None
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)

        # Date header
        self._header = QLabel()
        self._header.setObjectName("timelineDateHeader")
        self._lay.addWidget(self._header)

        # Cards container
        self._cards_widget = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(4)
        self._lay.addWidget(self._cards_widget)

        # Action buttons row
        actions = QWidget()
        actions_lay = QHBoxLayout(actions)
        actions_lay.setContentsMargins(4, 4, 0, 8)
        actions_lay.setSpacing(6)

        self._add_task_btn = QPushButton()
        self._add_task_btn.setObjectName("timelineActionBtn")
        self._add_task_btn.setFixedSize(28, 28)
        self._add_task_btn.setToolTip("Add scheduled task")
        self._add_task_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_task_btn.setFlat(True)
        self._add_task_btn.clicked.connect(lambda: self.add_task_requested.emit(self._day))
        actions_lay.addWidget(self._add_task_btn)

        self._add_event_btn = QPushButton()
        self._add_event_btn.setObjectName("timelineActionBtn")
        self._add_event_btn.setFixedSize(28, 28)
        self._add_event_btn.setToolTip("Add calendar event")
        self._add_event_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_event_btn.setFlat(True)
        self._add_event_btn.clicked.connect(lambda: self.add_event_requested.emit(self._day))
        actions_lay.addWidget(self._add_event_btn)

        actions_lay.addStretch()
        self._lay.addWidget(actions)

        self._cards: list[_TimelineCard] = []

    def set_icons(self) -> None:
        """Apply themed icons.  Called once after construction or on theme change."""
        self._add_task_btn.setIcon(get_themed_icon("task_add", 18))
        self._add_event_btn.setIcon(get_themed_icon("event_add", 18))

    def populate(
        self,
        day: date,
        items: list[Task | Event],
        is_today: bool,
        cal_colors: dict[int, str],
        accent_color: str,
    ) -> None:
        """Rebuild this section for *day* and its *items*."""
        self._day = day

        # Header text
        header_text = day.strftime("%B %d, %Y")
        if is_today:
            header_text += " — Today"
            self._header.setObjectName("timelineDateHeaderToday")
        else:
            self._header.setObjectName("timelineDateHeader")
        self._header.setText(header_text)
        self._header.style().unpolish(self._header)
        self._header.style().polish(self._header)

        # Clear old cards
        clear_layout(self._cards_layout)
        self._cards.clear()

        # Sort items: timed events by start_dt, then all-day items
        def _sort_key(item: Task | Event) -> tuple[int, datetime]:
            if isinstance(item, Task):
                return (1, datetime.min)
            if item.all_day:
                return (1, datetime.min)
            return (0, item.start_dt or datetime.min)

        items.sort(key=_sort_key)

        for item in items:
            card = _TimelineCard()
            card.populate(item, cal_colors, accent_color)
            card.clicked.connect(self.card_clicked.emit)
            self._cards_layout.addWidget(card)
            self._cards.append(card)

    # -- Drop target ---------------------------------------------------------

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        mime = event.mimeData()
        if mime.hasFormat(TIMELINE_TASK_MIME) or mime.hasFormat(TIMELINE_EVENT_MIME):
            event.acceptProposedAction()
            self.setProperty("dropHighlight", True)
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        mime = event.mimeData()
        if mime.hasFormat(TIMELINE_TASK_MIME) or mime.hasFormat(TIMELINE_EVENT_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        self.setProperty("dropHighlight", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        self.setProperty("dropHighlight", False)
        self.style().unpolish(self)
        self.style().polish(self)

        if self._day is None:
            event.ignore()
            return

        mime = event.mimeData()

        if mime.hasFormat(TIMELINE_TASK_MIME):
            task_id = int(mime.data(TIMELINE_TASK_MIME).data().decode())
            new_due = datetime(self._day.year, self._day.month, self._day.day)
            update_task(task_id, due_date=new_due)
            event.acceptProposedAction()
            self.item_dropped.emit()

        elif mime.hasFormat(TIMELINE_EVENT_MIME):
            raw = mime.data(TIMELINE_EVENT_MIME).data().decode()
            parts = raw.split("|", 2)
            try:
                event_id = int(parts[0])
                old_start_iso = parts[1] if len(parts) > 1 else ""
                old_end_iso = parts[2] if len(parts) > 2 else ""

                if old_start_iso:
                    old_start = datetime.fromisoformat(old_start_iso)
                    delta = datetime(self._day.year, self._day.month, self._day.day) - datetime(
                        old_start.year, old_start.month, old_start.day
                    )
                    new_start = old_start + delta
                    kwargs: dict = {"start_dt": new_start}
                    if old_end_iso:
                        old_end = datetime.fromisoformat(old_end_iso)
                        kwargs["end_dt"] = old_end + delta
                    update_event(event_id, **kwargs)
                event.acceptProposedAction()
                self.item_dropped.emit()
            except (ValueError, IndexError):
                event.ignore()
        else:
            event.ignore()


# ---------------------------------------------------------------------------
# Main timeline view
# ---------------------------------------------------------------------------


class TimelineView(QWidget):
    """Scrollable N-day timeline with day sections and a range selector."""

    event_edit_requested = Signal(object)  # Event
    task_clicked = Signal(object)  # Task (future use)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._day_range: int = 30
        self._cal_colors_cache: dict[int, str] | None = None
        get_notifier().data_changed.connect(self._invalidate_cal_cache)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # Range selector
        selector_row = QWidget()
        sel_lay = QHBoxLayout(selector_row)
        sel_lay.setContentsMargins(4, 0, 0, 0)
        sel_lay.setSpacing(8)

        range_label = QLabel("Show next:")
        range_label.setObjectName("timelineRangeLabel")
        sel_lay.addWidget(range_label)

        self._range_seg = SegmentedControl(_RANGE_LABELS)
        self._range_seg.setObjectName("timelineRangeSelector")
        self._range_seg.index_changed.connect(self._on_range_changed)
        sel_lay.addWidget(self._range_seg)

        sel_lay.addStretch()
        outer.addWidget(selector_row)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._inner = QWidget()
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(0)
        self._inner_layout.addStretch()

        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll)

        self._sections: list[_DaySection] = []

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def day_range(self) -> int:
        return self._day_range

    def get_date_range(self) -> tuple[date, date]:
        """Return (start, end) dates for the current range."""
        today = date.today()
        return today, today + timedelta(days=self._day_range)

    def refresh(self) -> None:
        """Query data and rebuild all day sections."""
        today = date.today()
        start_dt = datetime(today.year, today.month, today.day)
        end_dt = start_dt + timedelta(days=self._day_range)

        # Fetch data — tasks use SQL date bounds to avoid loading everything
        events = list_events_for_range(start_dt, end_dt)
        tasks = get_tasks_with_due_dates(start_dt=start_dt, end_dt=end_dt)

        # Cache calendar colours until the DB changes
        if self._cal_colors_cache is None:
            calendars = list_calendars()
            self._cal_colors_cache = {c.id: c.color for c in calendars if c.id is not None}
        cal_colors = self._cal_colors_cache

        accent_color = theme_colors(get_config().theme)["accent"]

        # Group items by date
        items_by_date: dict[date, list[Task | Event]] = defaultdict(list)

        # Suppress tasks that are already represented as calendar events
        scheduled_ids = {e.linked_task_id for e in events if e.linked_task_id is not None}

        for t in tasks:
            if t.id in scheduled_ids:
                continue  # shown as event block, not as due-task chip
            if t.due_date:
                items_by_date[t.due_date.date()].append(t)

        for e in events:
            if e.start_dt:
                items_by_date[e.start_dt.date()].append(e)

        # Ensure we have enough sections
        self._ensure_sections(self._day_range)

        # Populate each day
        for i in range(self._day_range):
            day = today + timedelta(days=i)
            section = self._sections[i]
            section.populate(
                day,
                items_by_date.get(day, []),
                is_today=(i == 0),
                cal_colors=cal_colors,
                accent_color=accent_color,
            )
            section.setVisible(True)

        # Hide excess sections
        for i in range(self._day_range, len(self._sections)):
            self._sections[i].setVisible(False)

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _on_range_changed(self, index: int) -> None:
        self._day_range = _RANGE_OPTIONS[index]
        self.refresh()

    def _invalidate_cal_cache(self) -> None:
        self._cal_colors_cache = None

    def _ensure_sections(self, count: int) -> None:
        """Grow the section pool to at least *count*."""
        while len(self._sections) < count:
            section = _DaySection()
            section.set_icons()
            section.item_dropped.connect(self.refresh)
            section.card_clicked.connect(self._on_card_clicked)
            section.add_event_requested.connect(self._on_add_event)
            section.add_task_requested.connect(self._on_add_task)
            # Insert before the trailing stretch
            idx = self._inner_layout.count() - 1
            self._inner_layout.insertWidget(idx, section)
            self._sections.append(section)

    def _on_card_clicked(self, item: Task | Event) -> None:
        if isinstance(item, Event):
            self.event_edit_requested.emit(item)

    def _on_add_event(self, day: date | None) -> None:
        """Open EventDialog prefilled to the given day."""
        if day is not None:
            dlg = EventDialog(prefill_date=day, parent=self)
            if dlg.exec():
                vals = dlg.get_values()
                if vals["title"]:
                    create_event(**vals)
                    self.refresh()

    def _on_add_task(self, day: date | None) -> None:
        """Show task quick-add dialog and create the task."""
        if day is None:
            return
        dlg = _TaskQuickAddDialog(day, parent=self)
        if dlg.exec():
            vals = dlg.get_values()
            if vals["title"] and vals["project_id"] is not None:
                create_task(
                    project_id=vals["project_id"],
                    title=vals["title"],
                    due_date=vals["due_date"],
                )
                self.refresh()
