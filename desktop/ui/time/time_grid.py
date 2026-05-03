"""
time_grid.py — Reusable hourly time-grid widget for week and day views.

Renders N day columns against a 24-hour y-axis.  Timed events are positioned
and sized proportionally; all-day events and tasks sit in a header row.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import QByteArray, QMimeData, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDrag,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...config import get_config
from ...models import Event, Task
from ...styles import TASK_COLOR, theme_colors
from ..shared.mime_types import TIMELINE_EVENT_MIME, TIMELINE_TASK_MIME

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HOUR_HEIGHT = 48  # pixels per hour row
TIME_COL_WIDTH = 56  # width of the hour-label gutter
_MIN_BLOCK_HEIGHT = 18  # minimum height for very short events
_BOLD_HOURS = {8, 12, 16, 20}  # 8am, 12pm, 4pm, 8pm get solid bold lines
FADE_HEIGHT = 20  # px of fade-in zone at top of scroll area


# ---------------------------------------------------------------------------
# Event block
# ---------------------------------------------------------------------------


class _EventBlock(QFrame):
    """A single timed-event rectangle inside a day column."""

    clicked = Signal(object)  # emits the Event

    def __init__(self, event: Event, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._event = event
        self._drag_start_pos: QPoint | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        colors = theme_colors(get_config().theme)
        bg = event.color or colors["accent"]
        fg = colors["chip_text"]

        # Format time string
        time_str = ""
        if event.start_dt:
            time_str = event.start_dt.strftime("%I:%M%p").lstrip("0").lower()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(0)

        title_lbl = QLabel(event.title)
        title_lbl.setStyleSheet(
            f"color: {fg}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        title_lbl.setWordWrap(False)
        lay.addWidget(title_lbl)

        if time_str:
            time_lbl = QLabel(time_str)
            time_lbl.setStyleSheet(f"color: {fg}; font-size: 10px; background: transparent;")
            lay.addWidget(time_lbl)

        lay.addStretch()

        self.setStyleSheet(
            f"_EventBlock {{ background-color: {bg}; border-radius: 4px; border: none; }}"
        )
        self.setToolTip(f"{event.title}\n{time_str}")

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
            mime_data = QMimeData()
            start_iso = self._event.start_dt.isoformat() if self._event.start_dt else ""
            end_iso = self._event.end_dt.isoformat() if self._event.end_dt else ""
            payload = f"{self._event.id}|{start_iso}|{end_iso}"
            mime_data.setData(TIMELINE_EVENT_MIME, QByteArray(payload.encode()))
            drag.setMimeData(mime_data)

            pixmap = QPixmap(self.size())
            self.render(pixmap)
            pixmap.setDevicePixelRatio(self.devicePixelRatioF())
            drag.setPixmap(pixmap)
            drag.setHotSpot(event.position().toPoint())
            drag.exec(Qt.DropAction.MoveAction)
            self._drag_start_pos = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            self.clicked.emit(self._event)
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# All-day chip
# ---------------------------------------------------------------------------


def _make_allday_chip(
    text: str,
    color: str,
    parent: QWidget | None = None,
) -> QLabel:
    """Small pill for the all-day header row."""
    colors = theme_colors(get_config().theme)
    fg = colors["chip_text"]
    lbl = QLabel(text, parent)
    lbl.setStyleSheet(
        f"background: {color}; color: {fg}; border-radius: 3px; padding: 1px 4px; font-size: 11px;"
    )
    lbl.setMaximumHeight(20)
    lbl.setToolTip(text)
    return lbl


# ---------------------------------------------------------------------------
# Day column (holds event blocks with absolute positioning)
# ---------------------------------------------------------------------------


class _DayColumn(QFrame):
    """A single day column styled like a month-view day cell, with hour gridlines."""

    slot_clicked = Signal(object)  # emits datetime
    item_dropped = Signal()  # emitted after a successful drop

    _TOP = FADE_HEIGHT  # vertical offset for all content
    _BOT = FADE_HEIGHT  # extra space at bottom for closing 12 AM + fade

    def __init__(
        self,
        enable_drops: bool = False,
        emit_slot_clicked: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dayCell")
        total_h = HOUR_HEIGHT * 24 + self._TOP + self._BOT
        self.setMinimumHeight(total_h)
        self.setFixedHeight(total_h)
        self._date: date | None = None
        self._is_today = False
        self._blocks: list[_EventBlock] = []
        self._emit_slot_clicked = emit_slot_clicked
        self._drop_highlight_hour: int | None = None
        if enable_drops:
            self.setAcceptDrops(True)

    def set_date(self, d: date) -> None:
        self._date = d
        self._is_today = d == date.today()
        self.setObjectName("dayCellToday" if self._is_today else "dayCell")
        # Force style refresh
        self.style().unpolish(self)
        self.style().polish(self)

    def clear_blocks(self) -> None:
        for b in self._blocks:
            b.setParent(None)
            b.deleteLater()
        self._blocks.clear()

    def add_block(self, event: Event) -> _EventBlock:
        block = _EventBlock(event, parent=self)
        self._blocks.append(block)
        self._position_block(block, event)
        block.show()
        return block

    def _position_block(self, block: _EventBlock, event: Event) -> None:
        if not event.start_dt:
            return
        start_minutes = event.start_dt.hour * 60 + event.start_dt.minute
        y = int(start_minutes / 60 * HOUR_HEIGHT) + self._TOP

        if event.end_dt and event.end_dt > event.start_dt:
            duration_minutes = (event.end_dt - event.start_dt).total_seconds() / 60
        else:
            duration_minutes = 60  # default 1 hour

        h = max(_MIN_BLOCK_HEIGHT, int(duration_minutes / 60 * HOUR_HEIGHT))
        # Side margins + 1px vertical separation from gridlines
        block.setGeometry(6, y + 1, self.width() - 12, h - 2)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        for block in self._blocks:
            self._position_block(block, block._event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        colors = theme_colors(get_config().theme)
        line_color = QColor(colors["border"])
        w = self.width()

        # Draw hour-slot drop highlight
        if self._drop_highlight_hour is not None:
            accent = QColor(colors["accent"])
            accent.setAlpha(40)
            hy = self._drop_highlight_hour * HOUR_HEIGHT + self._TOP
            painter.fillRect(0, hy, w, HOUR_HEIGHT, accent)
            # Draw top/bottom edges of the highlight band
            edge = QColor(colors["accent"])
            edge.setAlpha(120)
            painter.setPen(QPen(edge, 2, Qt.PenStyle.SolidLine))
            painter.drawLine(0, hy, w, hy)
            painter.drawLine(0, hy + HOUR_HEIGHT, w, hy + HOUR_HEIGHT)

        for h in range(0, 25):  # 0-24: includes closing 12 AM line at bottom
            y = h * HOUR_HEIGHT + self._TOP
            pen = QPen(line_color)

            if h in _BOLD_HOURS:
                pen.setWidth(2)
                pen.setStyle(Qt.PenStyle.SolidLine)
            elif h % 2 == 1:
                pen.setWidth(1)
                pen.setStyle(Qt.PenStyle.DashLine)
            else:
                pen.setWidth(1)
                pen.setStyle(Qt.PenStyle.SolidLine)

            painter.setPen(pen)
            painter.drawLine(0, y, w, y)

        # Current-time indicator (today's column only)
        if self._is_today:
            now = datetime.now()
            now_minutes = now.hour * 60 + now.minute
            now_y = int(now_minutes / 60 * HOUR_HEIGHT) + self._TOP
            now_color = QColor(colors["danger"])
            painter.setPen(QPen(now_color, 2, Qt.PenStyle.SolidLine))
            painter.drawLine(0, now_y, w, now_y)
            # Small circle at the left edge for visual anchor
            painter.setBrush(QBrush(now_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPoint(3, now_y), 3, 3)

        painter.end()

    def _hour_from_y(self, y: float) -> int:
        """Convert a y pixel coordinate to an hour (0-23)."""
        return max(0, min(23, int((y - self._TOP) / HOUR_HEIGHT)))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._emit_slot_clicked and self._date and event.button() == Qt.MouseButton.LeftButton:
            dt = datetime(
                self._date.year,
                self._date.month,
                self._date.day,
                self._hour_from_y(event.position().y()),
            )
            self.slot_clicked.emit(dt)

    # -- Drop target ----------------------------------------------------------

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
            new_hour = self._hour_from_y(event.position().y())
            if new_hour != self._drop_highlight_hour:
                self._drop_highlight_hour = new_hour
                self.update()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        self._drop_highlight_hour = None
        self.setProperty("dropHighlight", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        self._drop_highlight_hour = None
        self.setProperty("dropHighlight", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

        if self._date is None:
            event.ignore()
            return

        from ...database.calendars import get_default_calendar_id
        from ...database.events import (
            create_event,
            get_event_for_task,
            update_event,
        )
        from ...database.tasks import get_task, update_task

        mime = event.mimeData()
        drop_hour = self._hour_from_y(event.position().y())
        drop_dt = datetime(self._date.year, self._date.month, self._date.day, drop_hour)

        if mime.hasFormat(TIMELINE_TASK_MIME):
            task_id = int(mime.data(TIMELINE_TASK_MIME).data().decode())
            task = get_task(task_id)
            if task is None:
                event.ignore()
                return
            update_task(task_id, due_date=drop_dt)
            # Re-schedule existing linked event, or create a new one
            existing = get_event_for_task(task_id)
            if existing and existing.id is not None:
                dur = timedelta(hours=1)
                if existing.start_dt and existing.end_dt:
                    dur = existing.end_dt - existing.start_dt
                update_event(existing.id, start_dt=drop_dt, end_dt=drop_dt + dur)
            else:
                create_event(
                    calendar_id=get_default_calendar_id(),
                    title=task.title,
                    start_dt=drop_dt,
                    end_dt=drop_dt + timedelta(hours=1),
                    linked_task_id=task_id,
                )
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
                    # Preserve event duration, update both day and hour
                    duration = timedelta()
                    if old_end_iso:
                        old_end = datetime.fromisoformat(old_end_iso)
                        duration = old_end - old_start
                    else:
                        duration = timedelta(hours=1)
                    new_start = drop_dt
                    new_end = new_start + duration
                    update_event(event_id, start_dt=new_start, end_dt=new_end)
                event.acceptProposedAction()
                self.item_dropped.emit()
            except (ValueError, IndexError):
                event.ignore()
        else:
            event.ignore()


# ---------------------------------------------------------------------------
# Time grid
# ---------------------------------------------------------------------------


class TimeGrid(QWidget):
    """Hourly time-grid with N day columns.  Used for both week and day views."""

    event_clicked = Signal(object)  # Event
    slot_clicked = Signal(object)  # datetime
    item_dropped = Signal()  # relayed from day columns

    _FOLLOW_LEAD_HOURS = 3  # hours of history above the now-line

    def __init__(
        self,
        columns: int = 7,
        enable_drops: bool = False,
        emit_slot_clicked: bool = True,
        follow_now: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._num_columns = columns
        self._enable_drops = enable_drops
        self._emit_slot_clicked = emit_slot_clicked
        self._follow_now = follow_now

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Day headers ───────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 4, 0, 4)
        header_row.setSpacing(4)

        # "all-day" label in the gutter position, vertically aligned with day names
        allday_label = QLabel("all-day")
        allday_label.setObjectName("dayHeader")
        allday_label.setFixedWidth(TIME_COL_WIDTH)
        allday_label.setFixedHeight(28)
        allday_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(allday_label)

        self._header_labels: list[QLabel] = []
        for _ in range(columns):
            lbl = QLabel()
            lbl.setObjectName("dayHeader")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedHeight(28)
            header_row.addWidget(lbl, stretch=1)
            self._header_labels.append(lbl)

        outer.addLayout(header_row)

        # ── All-day row ───────────────────────────────────────────────────
        self._allday_row = QHBoxLayout()
        self._allday_row.setContentsMargins(0, 0, 0, 12)
        self._allday_row.setSpacing(4)

        # Plain gutter spacer (label is now in header row above)
        allday_gutter = QWidget()
        allday_gutter.setFixedWidth(TIME_COL_WIDTH)
        self._allday_row.addWidget(allday_gutter)

        self._allday_wrappers: list[QWidget] = []
        self._allday_containers: list[QVBoxLayout] = []
        for _ in range(columns):
            wrapper = QWidget()
            container = QVBoxLayout(wrapper)
            container.setContentsMargins(2, 0, 2, 0)
            container.setSpacing(2)
            self._allday_row.addWidget(wrapper, stretch=1)
            self._allday_wrappers.append(wrapper)
            self._allday_containers.append(container)

        outer.addLayout(self._allday_row)

        # ── Scrollable time grid ──────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        grid_inner = QWidget()
        grid_lay = QHBoxLayout(grid_inner)
        grid_lay.setContentsMargins(0, 0, 0, 0)
        grid_lay.setSpacing(4)

        # Hour labels gutter
        self._gutter = _HourGutter()
        grid_lay.addWidget(self._gutter)

        # Day columns
        self._day_columns: list[_DayColumn] = []
        for _ in range(columns):
            col = _DayColumn(enable_drops=enable_drops, emit_slot_clicked=emit_slot_clicked)
            col.slot_clicked.connect(self.slot_clicked.emit)
            col.item_dropped.connect(self.item_dropped.emit)
            grid_lay.addWidget(col, stretch=1)
            self._day_columns.append(col)

        scroll.setWidget(grid_inner)
        self._scroll = scroll

        if self._follow_now:
            full_h = HOUR_HEIGHT * 24 + FADE_HEIGHT * 2
            scroll.setMaximumHeight(int(full_h * 0.75))

        # Fade overlays pinned to top and bottom of scroll area
        self._fade_top = _FadeOverlay(bottom=False, parent=scroll)
        self._fade_top.raise_()
        self._fade_bot = _FadeOverlay(bottom=True, parent=scroll)
        self._fade_bot.raise_()

        # Scroll to ~8 AM on first show (or follow now-line)
        if self._follow_now:
            QTimer.singleShot(50, self._follow_now_scroll)
        else:
            QTimer.singleShot(50, lambda: self._scroll_to_hour(8))

        # Refresh the current-time indicator every 60 seconds
        self._now_timer = QTimer(self)
        self._now_timer.setInterval(60_000)
        self._now_timer.timeout.connect(self._update_now_line)
        self._now_timer.start()

    # -- public API ----------------------------------------------------------

    def set_data(
        self,
        dates: list[date],
        events: list[Event],
        tasks: list[Task],
    ) -> None:
        """Populate the grid with the given dates, events, and tasks."""
        colors = theme_colors(get_config().theme)
        today = date.today()

        # Update headers
        for i, lbl in enumerate(self._header_labels):
            if i < len(dates):
                d = dates[i]
                day_name = d.strftime("%a")
                lbl.setText(f"{day_name} {d.day}")
                if d == today:
                    lbl.setStyleSheet(f"color: {colors['accent']}; font-weight: 700;")
                else:
                    lbl.setStyleSheet("")
            else:
                lbl.setText("")

        # Clear previous data
        for col in self._day_columns:
            col.clear_blocks()
        for container in self._allday_containers:
            while container.count():
                item = container.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        # Build date→column index map
        date_to_col: dict[date, int] = {}
        for i, d in enumerate(dates):
            date_to_col[d] = i
            self._day_columns[i].set_date(d)

        # Tasks with a linked event are shown as event blocks, not all-day chips
        scheduled_ids = {e.linked_task_id for e in events if e.linked_task_id is not None}

        # Place tasks (all-day) — skip those already represented by an event block
        for task in tasks:
            if task.id in scheduled_ids:
                continue
            if task.due_date:
                task_date = (
                    task.due_date.date() if isinstance(task.due_date, datetime) else task.due_date
                )
                col_idx = date_to_col.get(task_date)  # type: ignore[arg-type]
                if col_idx is not None:
                    chip = _make_allday_chip(task.title[:22], TASK_COLOR)
                    self._allday_containers[col_idx].addWidget(chip)

        # Place events
        for event in events:
            if not event.start_dt:
                continue
            event_date = event.start_dt.date()
            col_idx = date_to_col.get(event_date)
            if col_idx is None:
                continue

            if event.all_day:
                bg = event.color or colors["accent"]
                chip = _make_allday_chip(event.title[:22], bg)
                self._allday_containers[col_idx].addWidget(chip)
            else:
                block = self._day_columns[col_idx].add_block(event)
                block.clicked.connect(self.event_clicked.emit)

    def set_visible_columns(self, count: int) -> None:
        """Show only the first *count* columns; hide the rest."""
        for i in range(self._num_columns):
            visible = i < count
            self._header_labels[i].setVisible(visible)
            self._allday_wrappers[i].setVisible(visible)
            self._day_columns[i].setVisible(visible)

    def _update_now_line(self) -> None:
        """Repaint today's column so the current-time indicator moves."""
        for col in self._day_columns:
            if col._is_today:
                col.update()
        if self._follow_now:
            self._follow_now_scroll()

    # -- internals -----------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        w = self._scroll.width()
        h = self._scroll.height()
        # Pin top fade to top edge
        self._fade_top.setFixedWidth(w)
        self._fade_top.move(0, 0)
        # Pin bottom fade to bottom edge
        self._fade_bot.setFixedWidth(w)
        self._fade_bot.move(0, h - FADE_HEIGHT)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._now_timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._now_timer.stop()

    def _scroll_to_hour(self, hour: int) -> None:
        y = hour * HOUR_HEIGHT
        self._scroll.verticalScrollBar().setValue(y)

    def _follow_now_scroll(self) -> None:
        """Auto-scroll so the now-line sits at a fixed position: 3 hours below the top."""
        now = datetime.now()
        now_minutes = now.hour * 60 + now.minute
        now_y = int(now_minutes / 60 * HOUR_HEIGHT) + FADE_HEIGHT
        target = now_y - self._FOLLOW_LEAD_HOURS * HOUR_HEIGHT
        self._scroll.verticalScrollBar().setValue(max(0, target))


# ---------------------------------------------------------------------------
# Fade overlays (top + bottom edges of scroll area)
# ---------------------------------------------------------------------------


class _FadeOverlay(QWidget):
    """Gradient fade: opaque bg → transparent.  *bottom* flips the direction."""

    def __init__(self, bottom: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bottom = bottom
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedHeight(FADE_HEIGHT)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        colors = theme_colors(get_config().theme)
        bg = QColor(colors["bg-primary"])

        grad = QLinearGradient(0, 0, 0, FADE_HEIGHT)
        bg_opaque = QColor(bg)
        bg_opaque.setAlpha(255)
        bg_transparent = QColor(bg)
        bg_transparent.setAlpha(0)

        if self._bottom:
            grad.setColorAt(0.0, bg_transparent)
            grad.setColorAt(1.0, bg_opaque)
        else:
            grad.setColorAt(0.0, bg_opaque)
            grad.setColorAt(1.0, bg_transparent)

        painter.fillRect(self.rect(), QBrush(grad))
        painter.end()


# ---------------------------------------------------------------------------
# Hour gutter (time labels + gridlines)
# ---------------------------------------------------------------------------


class _HourGutter(QWidget):
    """Fixed-width column showing hour labels (12 AM - 11 PM)."""

    _TOP = FADE_HEIGHT  # match day column offset
    _BOT = FADE_HEIGHT

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(TIME_COL_WIDTH)
        total_h = HOUR_HEIGHT * 24 + self._TOP + self._BOT
        self.setMinimumHeight(total_h)
        self.setFixedHeight(total_h)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        colors = theme_colors(get_config().theme)
        text_color = QColor(colors["text-muted"])
        bold_text = QColor(colors["text"])

        font = QFont()
        font.setPixelSize(13)

        for h in range(25):  # 0-24: includes closing 12 AM
            y = h * HOUR_HEIGHT + self._TOP

            if h == 0 or h == 24:
                label = "12 AM"
            elif h < 12:
                label = f"{h} AM"
            elif h == 12:
                label = "12 PM"
            else:
                label = f"{h - 12} PM"

            is_bold = h in _BOLD_HOURS
            font.setBold(is_bold)
            painter.setFont(font)
            painter.setPen(bold_text if is_bold else text_color)
            painter.drawText(4, y + 5, label)

        painter.end()
