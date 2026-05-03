"""
calendar_view.py — Calendar view with month grid, timeline, and view switcher.

Month grid uses a pre-allocated 6x7 pool of _DayCell widgets that are
populated in-place on refresh, avoiding the deleteLater / recreate cycle that
caused console flash.  Timeline view is delegated to timeline_view.TimelineView.
"""

import calendar as cal_mod
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import IntEnum

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...config import get_config
from ...database.connection import get_notifier
from ...database.events import create_event, delete_event, list_events_for_range, update_event
from ...database.tasks import get_tasks_with_due_dates
from ...models import Event, Task
from ...styles import TASK_COLOR, theme_colors
from ..shared.animated_stack import AnimatedViewStack, SlideAxis
from ..shared.icons import get_icon
from ..shared.widgets import SegmentedControl, reconnect
from ..time.time_grid import TimeGrid
from .agenda_view import AgendaView
from .event_dialog import EventDialog
from .timeline_view import TimelineView

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CELL_HEIGHT = 120
_MAX_CHIPS = 3
_VIEWS = ["Month", "Week", "Agenda", "Timeline"]


class CalView(IntEnum):
    MONTH = 0
    WEEK = 1
    AGENDA = 2
    TIMELINE = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chip(
    text: str,
    color: str,
    parent: QWidget | None = None,
    chip_text: str | None = None,
) -> QLabel:
    """Return a coloured pill-shaped label for event/task display."""
    if chip_text is None:
        chip_text = theme_colors(get_config().theme)["chip_text"]
    lbl = QLabel(text, parent)
    lbl.setObjectName("eventChip")
    lbl.setStyleSheet(
        f"background: {color}; color: {chip_text}; border-radius: 3px; "
        f"padding: 1px 4px; font-size: 11px;"
    )
    lbl.setMaximumWidth(200)
    lbl.setToolTip(text)
    return lbl


def _make_event_chip(
    text: str,
    color: str,
    on_click,
    parent: QWidget | None = None,
    chip_text: str | None = None,
) -> QPushButton:
    """Return a clickable chip button for calendar events."""
    if chip_text is None:
        chip_text = theme_colors(get_config().theme)["chip_text"]
    btn = QPushButton(text, parent)
    btn.setObjectName("eventChip")
    btn.setFlat(True)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(
        f"background: {color}; color: {chip_text}; border-radius: 3px; "
        f"padding: 1px 4px; font-size: 11px; text-align: left; border: none;"
    )
    btn.setMaximumWidth(200)
    btn.setToolTip(text)
    btn.clicked.connect(on_click)
    return btn


@dataclass
class _TaskSummary:
    """Aggregated task counts for a single day in the month grid."""

    due_count: int = 0  # tasks with due_date but no linked event
    scheduled_count: int = 0  # events with linked_task_id


def _month_items_by_day(
    tasks: list[Task],
    events: list[Event],
    year: int,
    month: int,
) -> dict[int, list]:
    """Return {day: [items...]} for the month view.

    Regular events are kept as individual items.  Task-related items (due-only
    tasks and linked-task events) are collapsed into a single _TaskSummary per
    day so the month grid can show summary text instead of individual chips.
    """
    by_day: dict[int, list] = defaultdict(list)

    month_start = datetime(year, month, 1)
    month_end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

    # Identify tasks that have linked events this month
    linked_task_ids: set[int] = set()
    scheduled_by_day: dict[int, int] = defaultdict(int)
    for e in events:
        if e.start_dt and month_start <= e.start_dt < month_end:
            if e.linked_task_id is not None:
                linked_task_ids.add(e.linked_task_id)
                scheduled_by_day[e.start_dt.day] += 1
            else:
                by_day[e.start_dt.day].append(e)

    # Count due-only tasks (those without a linked event)
    due_by_day: dict[int, int] = defaultdict(int)
    for t in tasks:
        if t.due_date and month_start <= t.due_date < month_end and t.id not in linked_task_ids:
            due_by_day[t.due_date.day] += 1

    # Insert one summary per day that has any task-related items
    for day in set(scheduled_by_day) | set(due_by_day):
        by_day[day].append(
            _TaskSummary(
                due_count=due_by_day.get(day, 0),
                scheduled_count=scheduled_by_day.get(day, 0),
            )
        )

    return by_day


# ---------------------------------------------------------------------------
# Pre-allocated day cell
# ---------------------------------------------------------------------------


class _DayCell(QFrame):
    """A calendar day cell that can be populated in-place."""

    MAX_CHIPS = 3

    def __init__(self, parent_view: "CalendarView") -> None:
        super().__init__()
        self._day: int = 0
        self._cell_date: date | None = None
        self._parent_view = parent_view
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(_CELL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(6, 4, 6, 4)
        self._lay.setSpacing(2)

        # Day number label
        self._day_lbl = QLabel()
        self._lay.addWidget(self._day_lbl, alignment=Qt.AlignmentFlag.AlignRight)

        # Pre-allocate MAX_CHIPS chip slots (QLabel as placeholder; replaced in populate)
        self._chip_widgets: list[QWidget] = []
        for _ in range(self.MAX_CHIPS):
            w = QLabel()
            w.setVisible(False)
            self._lay.addWidget(w)
            self._chip_widgets.append(w)

        self._overflow_btn = QPushButton()
        self._overflow_btn.setFlat(True)
        self._overflow_btn.setObjectName("calendarMore")
        self._overflow_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._overflow_btn.setVisible(False)
        self._lay.addWidget(self._overflow_btn)

        self._lay.addStretch()
        self.setVisible(False)

    def populate(
        self,
        day: int,
        cell_date: date,
        items: list,
        is_today: bool,
    ) -> None:
        """Update this cell's contents in-place for the given day."""
        colors = theme_colors(get_config().theme)
        self._day = day
        self._cell_date = cell_date
        self._day_lbl.setText(str(day))
        day_lbl_name = "dayNumberToday" if is_today else "dayNumber"
        self._day_lbl.setObjectName(day_lbl_name)
        self._day_lbl.style().unpolish(self._day_lbl)
        self._day_lbl.style().polish(self._day_lbl)

        cell_name = "dayCellToday" if is_today else "dayCell"
        self.setObjectName(cell_name)
        self.style().unpolish(self)
        self.style().polish(self)

        shown = items[: self.MAX_CHIPS]
        overflow = len(items) - self.MAX_CHIPS

        # Update chip slots — replace widget in the layout slot
        for i in range(self.MAX_CHIPS):
            old_w = self._chip_widgets[i]
            if i < len(shown):
                item = shown[i]
                if isinstance(item, _TaskSummary):
                    parts: list[str] = []
                    if item.due_count:
                        parts.append(f"{item.due_count} due")
                    if item.scheduled_count:
                        parts.append(f"{item.scheduled_count} scheduled")
                    text = ", ".join(parts)
                    new_w: QWidget = QLabel(text)
                    new_w.setStyleSheet(
                        f"color: {colors['text-muted']}; font-size: 10px; "
                        f"padding: 1px 4px; background: transparent;"
                    )
                    new_w.setMaximumHeight(20)
                    new_w.setToolTip(text)
                elif isinstance(item, Task):
                    new_w = _make_chip(item.title[:22], TASK_COLOR, chip_text=colors["chip_text"])
                    new_w.setToolTip(f"Task due: {item.title}")
                else:
                    color = item.color or colors["accent"]
                    time_prefix = ""
                    if item.start_dt and not item.all_day:
                        time_prefix = item.start_dt.strftime("%I:%M%p").lstrip("0").lower() + " "
                    new_w = _make_event_chip(
                        f"{time_prefix}{item.title[:20]}",
                        color,
                        on_click=lambda _, e=item: self._parent_view._open_edit_event(e),
                        chip_text=colors["chip_text"],
                    )
                    new_w.setToolTip(item.title)

                # Replace the placeholder in the layout
                idx = self._lay.indexOf(old_w)
                self._lay.removeWidget(old_w)
                old_w.setParent(None)  # type: ignore[arg-type]
                old_w.deleteLater()
                self._lay.insertWidget(idx, new_w)
                self._chip_widgets[i] = new_w
                new_w.setVisible(True)
            else:
                old_w.setVisible(False)

        # Overflow button
        if overflow > 0:
            self._overflow_btn.setText(f"+{overflow} more")
            hidden_items = items[self.MAX_CHIPS :]
            reconnect(
                self._overflow_btn.clicked,
                lambda _, hi=hidden_items: self._parent_view._show_overflow(hi, self._overflow_btn),
            )
            self._overflow_btn.setVisible(True)
        else:
            self._overflow_btn.setVisible(False)

        self.setVisible(True)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._cell_date:
            self._parent_view._open_new_event(self._cell_date)
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------


class CalendarView(QWidget):
    """Month calendar with agenda, view switcher, and event creation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        now = datetime.now()
        self._current = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        self._month_pos = self._current  # snapped to 1st of month
        self._week_pos = now.replace(hour=0, minute=0, second=0, microsecond=0)  # today
        self._agenda_pos = now.replace(hour=0, minute=0, second=0, microsecond=0)  # today
        self._current_view: CalView = CalView.MONTH
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
        self.installEventFilter(self)

    # ------------------------------------------------------------------ #
    # Build
    # ------------------------------------------------------------------ #

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 24)
        outer.setSpacing(12)

        outer.addWidget(self._build_toolbar())

        self._stack = AnimatedViewStack(axis=SlideAxis.HORIZONTAL)
        outer.addWidget(self._stack)

        # Month view
        self._month_container = QWidget()
        self._month_layout = QVBoxLayout(self._month_container)
        self._month_layout.setContentsMargins(0, 0, 0, 0)
        self._month_layout.setSpacing(0)

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(2)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        for col in range(7):
            self._grid_layout.setColumnStretch(col, 1)

        # Day headers — built once at row 0
        for i, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setObjectName("dayHeader")
            lbl.setFixedHeight(28)
            self._grid_layout.addWidget(lbl, 0, i)

        # Pre-allocate 6x7 = 42 day cells (rows 1-6)
        self._day_cells: list[list[_DayCell]] = []
        for r in range(6):
            row_cells: list[_DayCell] = []
            for c in range(7):
                cell = _DayCell(self)
                self._grid_layout.addWidget(cell, r + 1, c)
                row_cells.append(cell)
            self._day_cells.append(row_cells)
            self._grid_layout.setRowStretch(r + 1, 1)

        # Persistent empty-state label (shown when no items exist this month)
        self._month_empty_lbl = QLabel("Nothing scheduled — click any day to add an event.")
        self._month_empty_lbl.setObjectName("emptyCalendar")
        self._month_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._month_empty_lbl.setVisible(False)
        self._month_layout.addWidget(self._month_empty_lbl)

        self._month_scroll = QScrollArea()
        self._month_scroll.setWidgetResizable(True)
        self._month_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._month_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._month_scroll.setWidget(self._grid_container)
        self._month_layout.addWidget(self._month_scroll)
        self._stack.addWidget(self._month_container)

        # Week view (time grid)
        self._week_grid = TimeGrid(columns=7, enable_drops=True)
        self._week_grid.event_clicked.connect(self._open_edit_event)
        self._week_grid.slot_clicked.connect(
            lambda dt: self._open_new_event(dt.date() if hasattr(dt, "date") else dt)
        )
        self._week_grid.item_dropped.connect(self.refresh)
        self._stack.addWidget(self._week_grid)

        # Agenda view
        self._agenda = AgendaView()
        self._agenda.event_edit_requested.connect(self._open_edit_event)
        self._stack.addWidget(self._agenda)

        # Timeline view
        self._timeline = TimelineView()
        self._timeline.event_edit_requested.connect(self._open_edit_event)
        self._stack.addWidget(self._timeline)

    def _build_toolbar(self) -> QWidget:
        """Build the full toolbar: nav arrows, Today, month label, view switcher, new event."""
        toolbar = QWidget()
        toolbar.setObjectName("calendarToolbar")
        lay = QHBoxLayout(toolbar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        try:
            arrow_color = self.palette().text().color().name()
        except Exception:
            arrow_color = "#a0a0a0"

        today_btn = QPushButton("Today")
        today_btn.clicked.connect(self._go_today)
        lay.addWidget(today_btn)

        self._prev_btn = QPushButton()
        self._prev_btn.setIcon(get_icon("nav_prev", arrow_color))
        self._prev_btn.setFixedWidth(32)
        self._prev_btn.clicked.connect(self._prev_period)
        lay.addWidget(self._prev_btn)

        self._next_btn = QPushButton()
        self._next_btn.setIcon(get_icon("nav_next", arrow_color))
        self._next_btn.setFixedWidth(32)
        self._next_btn.clicked.connect(self._next_period)
        lay.addWidget(self._next_btn)

        lay.addStretch()

        self._month_label = QLabel()
        self._month_label.setObjectName("monthLabel")
        self._month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._month_label)

        lay.addStretch()

        # View switcher (segmented control)
        self._view_seg = SegmentedControl(list(_VIEWS))
        self._view_seg.index_changed.connect(self._switch_view)
        lay.addWidget(self._view_seg)

        lay.addSpacing(12)

        new_btn = QPushButton("+ New Event")
        new_btn.setObjectName("primaryButton")
        new_btn.clicked.connect(lambda: self._open_new_event(None))
        lay.addWidget(new_btn)

        return toolbar

    # ------------------------------------------------------------------ #
    # Visibility
    # ------------------------------------------------------------------ #

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

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self._update_arrow_icons()
            self.refresh()

    def _update_arrow_icons(self) -> None:
        """Re-render nav arrow SVGs with the current palette text color."""
        try:
            color = self.palette().text().color().name()
        except Exception:
            color = "#a0a0a0"
        self._prev_btn.setIcon(get_icon("nav_prev", color))
        self._next_btn.setIcon(get_icon("nav_next", color))

    # ------------------------------------------------------------------ #
    # Navigation
    # ------------------------------------------------------------------ #

    def _prev_period(self) -> None:
        if self._current_view == CalView.TIMELINE:
            return
        if self._current_view == CalView.AGENDA:
            self._current -= timedelta(days=1)
        elif self._current_view == CalView.WEEK:
            self._current -= timedelta(weeks=1)
        else:  # month
            c = self._current
            if c.month == 1:
                self._current = c.replace(year=c.year - 1, month=12)
            else:
                self._current = c.replace(month=c.month - 1)
        self.refresh()

    def _next_period(self) -> None:
        if self._current_view == CalView.TIMELINE:
            return
        if self._current_view == CalView.AGENDA:
            self._current += timedelta(days=1)
        elif self._current_view == CalView.WEEK:
            self._current += timedelta(weeks=1)
        else:  # month
            c = self._current
            if c.month == 12:
                self._current = c.replace(year=c.year + 1, month=1)
            else:
                self._current = c.replace(month=c.month + 1)
        self.refresh()

    def _go_today(self) -> None:
        now = datetime.now()
        if self._current_view == CalView.MONTH:
            self._current = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:  # week, agenda, timeline — snap to today
            self._current = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.refresh()

    def select_view(self, index: int) -> None:
        """Programmatically switch to a sub-view by index."""
        self._view_seg.set_index(index)

    def _switch_view(self, index: int) -> None:
        old_view = self._current_view
        view = CalView(index)
        # Save position for the view we're leaving
        if old_view == CalView.MONTH:
            self._month_pos = self._current
        elif old_view == CalView.WEEK:
            self._week_pos = self._current
        elif old_view == CalView.AGENDA:
            self._agenda_pos = self._current
        # Restore position for the view we're entering
        if view == CalView.MONTH:
            self._current = self._month_pos
        elif view == CalView.WEEK:
            self._current = self._week_pos
        elif view == CalView.AGENDA:
            self._current = self._agenda_pos
        self._current_view = view
        self._stack.setCurrentIndex(index)
        # Disable nav arrows for timeline (always anchored to today)
        self._prev_btn.setEnabled(view != CalView.TIMELINE)
        self._next_btn.setEnabled(view != CalView.TIMELINE)
        self.refresh()

    # ------------------------------------------------------------------ #
    # Refresh (top-level)
    # ------------------------------------------------------------------ #

    def refresh(self) -> None:
        if self._current_view == CalView.WEEK:
            week_start = self._current - timedelta(days=self._current.weekday())
            week_end = week_start + timedelta(days=6)
            if week_start.month == week_end.month:
                self._month_label.setText(
                    f"{week_start.strftime('%B')} {week_start.day}-{week_end.day}, {week_start.year}"
                )
            else:
                self._month_label.setText(
                    f"{week_start.strftime('%b')} {week_start.day} - "
                    f"{week_end.strftime('%b')} {week_end.day}, {week_end.year}"
                )
        elif self._current_view == CalView.AGENDA:
            agenda_start = self._current.date()
            agenda_end = agenda_start + timedelta(days=2)
            if agenda_start.month == agenda_end.month:
                self._month_label.setText(
                    f"{agenda_start.strftime('%B')} {agenda_start.day}-{agenda_end.day}, {agenda_start.year}"
                )
            else:
                self._month_label.setText(
                    f"{agenda_start.strftime('%b')} {agenda_start.day} - "
                    f"{agenda_end.strftime('%b')} {agenda_end.day}, {agenda_end.year}"
                )
        elif self._current_view == CalView.TIMELINE:
            start, end = self._timeline.get_date_range()
            end_display = end - timedelta(days=1)  # inclusive end
            if start.month == end_display.month:
                self._month_label.setText(
                    f"{start.strftime('%b')} {start.day}-{end_display.day}, {start.year}"
                )
            else:
                self._month_label.setText(
                    f"{start.strftime('%b')} {start.day} - "
                    f"{end_display.strftime('%b')} {end_display.day}, {end_display.year}"
                )
        else:
            self._month_label.setText(self._current.strftime("%B %Y"))

        if self._current_view == CalView.MONTH:
            self._refresh_month()
        elif self._current_view == CalView.WEEK:
            self._refresh_week()
        elif self._current_view == CalView.AGENDA:
            anchor = self._current.date()
            self._agenda.set_dates(anchor)
            self._agenda.refresh()
        elif self._current_view == CalView.TIMELINE:
            self._timeline.refresh()

    # ------------------------------------------------------------------ #
    # Month view
    # ------------------------------------------------------------------ #

    def _refresh_month(self) -> None:
        year, month = self._current.year, self._current.month

        month_start = datetime(year, month, 1)
        month_end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
        tasks = get_tasks_with_due_dates()
        events = list_events_for_range(month_start, month_end)
        by_day = _month_items_by_day(tasks, events, year, month)

        first_weekday, days_in_month = cal_mod.monthrange(year, month)
        today = datetime.now().date()

        total_items = sum(len(v) for v in by_day.values())

        # Populate or hide all 42 pre-allocated cells
        day = 1
        for r in range(6):
            for c in range(7):
                grid_pos = r * 7 + c
                cell = self._day_cells[r][c]
                if grid_pos < first_weekday or day > days_in_month:
                    cell.setVisible(False)
                else:
                    cell_date = date(year, month, day)
                    is_today = cell_date == today
                    cell.populate(day, cell_date, by_day.get(day, []), is_today)
                    day += 1

        self._month_empty_lbl.setVisible(total_items == 0)

    def _show_overflow(self, items: list, anchor: QWidget) -> None:
        """Show a popup menu listing all overflow items; click to edit."""
        menu = QMenu(self)
        for item in items:
            if isinstance(item, _TaskSummary):
                parts: list[str] = []
                if item.due_count:
                    parts.append(f"{item.due_count} task(s) due")
                if item.scheduled_count:
                    parts.append(f"{item.scheduled_count} scheduled")
                action = menu.addAction(", ".join(parts))
                action.setEnabled(False)
            elif isinstance(item, Task):
                action = menu.addAction(f"[Task] {item.title}")
                action.setEnabled(False)
            else:
                action = menu.addAction(item.title)
                action.setData(item)
                action.triggered.connect(lambda _, e=item: self._open_edit_event(e))
        menu.exec(anchor.mapToGlobal(QPoint(0, anchor.height())))

    # ------------------------------------------------------------------ #
    # Week view
    # ------------------------------------------------------------------ #

    def _refresh_week(self) -> None:
        # Monday of the current week
        week_start_date = (self._current - timedelta(days=self._current.weekday())).date()
        week_dates = [week_start_date + timedelta(days=i) for i in range(7)]

        week_start = datetime(week_start_date.year, week_start_date.month, week_start_date.day)
        week_end = week_start + timedelta(days=7)

        events = list_events_for_range(week_start, week_end)
        tasks = get_tasks_with_due_dates(start_dt=week_start, end_dt=week_end)

        self._week_grid.set_data(week_dates, events, tasks)

    # ------------------------------------------------------------------ #
    # Event dialog management
    # ------------------------------------------------------------------ #

    def _open_new_event(self, prefill_date: date | None) -> None:
        dlg = EventDialog(prefill_date=prefill_date, parent=self)
        if dlg.exec():
            vals = dlg.get_values()
            if vals["title"]:
                create_event(**vals)
                self.refresh()

    def _open_edit_event(self, event: Event) -> None:
        dlg = EventDialog(event=event, parent=self)
        result = dlg.exec()
        if dlg.was_deleted():
            if event.id is not None:
                delete_event(event.id)
                self.refresh()
        elif result:
            vals = dlg.get_values()
            if event.id is not None:
                update_event(event.id, **vals)
                self.refresh()

    # ------------------------------------------------------------------ #
    # Keyboard shortcuts
    # ------------------------------------------------------------------ #

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            focused = QApplication.focusWidget()
            if isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit)):
                return False
            key = event.key()
            if key == Qt.Key.Key_Left:
                self._prev_period()
                return True
            if key == Qt.Key.Key_Right:
                self._next_period()
                return True
            if key == Qt.Key.Key_T:
                self._go_today()
                return True
            if key == Qt.Key.Key_N:
                self._open_new_event(None)
                return True
            if key == Qt.Key.Key_M:
                self._view_seg.set_index(CalView.MONTH)
                return True
            if key == Qt.Key.Key_W:
                self._view_seg.set_index(CalView.WEEK)
                return True
            if key == Qt.Key.Key_A:
                self._view_seg.set_index(CalView.AGENDA)
                return True
            if key == Qt.Key.Key_L:
                self._view_seg.set_index(CalView.TIMELINE)
                return True
        return super().eventFilter(obj, event)
