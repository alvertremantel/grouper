"""
activity_week.py — Week-at-a-glance activity strip for the dashboard.

Renders seven day columns (Mon-Sun of the current week) with session blocks
positioned proportionally on a 24-hour vertical axis.  Completed sessions
use a deterministic per-activity color; active sessions show as a fixed
one-hour pulsing green block.
"""

from __future__ import annotations

import hashlib
import math
import time as _time
from datetime import date, datetime, timedelta

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..config import get_config
from ..database.activities import list_activities
from ..database.sessions import get_active_sessions, get_sessions
from ..models import Session
from ..styles import theme_colors

# ── constants ────────────────────────────────────────────────────────────────

HOUR_HEIGHT = 48
_TOP = 20  # padding above hour 0
_BOT = 20  # padding below hour 24
_GRID_H = HOUR_HEIGHT * 24 + _TOP + _BOT
_GUTTER_W = 56
_HEADER_H = 28
_MIN_BLOCK_H = 14
_BOLD_HOURS = frozenset({8, 12, 16, 20})

# ── activity color palette ───────────────────────────────────────────────────

_PALETTE = [
    "#7aa2f7",  # blue
    "#f7768e",  # rose
    "#9ece6a",  # green
    "#e0af68",  # amber
    "#bb9af7",  # purple
    "#7dcfff",  # cyan
    "#ff9e64",  # orange
    "#73daca",  # teal
    "#f7c948",  # yellow
    "#db4b4b",  # crimson
    "#449dab",  # dark cyan
    "#c0caf5",  # lavender
]


def _activity_color(name: str) -> str:
    """Deterministic color for an activity name (stable across restarts)."""
    idx = int(hashlib.sha1(name.encode()).hexdigest(), 16) % len(_PALETTE)
    return _PALETTE[idx]


# ── session block ────────────────────────────────────────────────────────────


class _SessionBlock(QWidget):
    """Painted block representing one tracked session."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bg = QColor("#7aa2f7")
        self._is_active = False
        self._pulse_alpha = 1.0
        self.start_min = 0
        self.end_min = 0

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)

    def configure(
        self,
        name: str,
        color: str,
        chip_text: str,
        *,
        is_active: bool = False,
    ) -> None:
        self._bg = QColor(color)
        self._is_active = is_active
        self._label.setText(name)
        self._label.setStyleSheet(
            f"color: {chip_text}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        self.update()

    def set_pulse_alpha(self, alpha: float) -> None:
        if self._is_active:
            self._pulse_alpha = alpha
            self.update()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._label.setGeometry(4, 0, self.width() - 8, self.height())

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(self._bg)
        if self._is_active:
            c.setAlphaF(self._pulse_alpha)
        p.setBrush(c)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(
            QRectF(0.5, 0.5, self.width() - 1, self.height() - 1),
            4,
            4,
        )
        p.end()


# ── day column ───────────────────────────────────────────────────────────────


class _DayCol(QFrame):
    """Single day column with gridlines and absolutely-positioned blocks."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dayCell")
        self.setFixedHeight(_GRID_H)
        self._date: date | None = None
        self._is_today = False
        self._blocks: list[_SessionBlock] = []

    def set_date(self, d: date) -> None:
        self._date = d
        self._is_today = d == date.today()
        self.setObjectName("dayCellToday" if self._is_today else "dayCell")
        self.style().unpolish(self)
        self.style().polish(self)

    def clear_blocks(self) -> None:
        for b in self._blocks:
            b.setParent(None)
            b.deleteLater()
        self._blocks.clear()

    def add_block(self, block: _SessionBlock, start_min: int, end_min: int) -> None:
        block.setParent(self)
        block.start_min = start_min
        block.end_min = end_min
        self._blocks.append(block)
        self._position_block(block, start_min, end_min)
        block.show()

    def _position_block(
        self,
        block: _SessionBlock,
        start_min: int,
        end_min: int,
    ) -> None:
        y = int(start_min / 60 * HOUR_HEIGHT) + _TOP
        h = max(_MIN_BLOCK_H, int((end_min - start_min) / 60 * HOUR_HEIGHT))
        block.setGeometry(4, y + 1, self.width() - 8, h - 2)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        for b in self._blocks:
            self._position_block(b, b.start_min, b.end_min)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        colors = theme_colors(get_config().theme)
        grid_c = QColor(colors.get("border", "#3b3d57"))
        w = self.width()

        for hour in range(25):
            y = hour * HOUR_HEIGHT + _TOP
            if hour in _BOLD_HOURS:
                pen = QPen(grid_c, 2)
            elif hour % 2 == 0:
                pen = QPen(grid_c, 1)
            else:
                pen = QPen(grid_c, 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(0, y, w, y)

        # Now-line on today's column
        if self._is_today:
            now = datetime.now()
            ny = int((now.hour * 60 + now.minute) / 60 * HOUR_HEIGHT) + _TOP
            danger = QColor(colors.get("danger", "#f7768e"))
            p.setPen(QPen(danger, 2))
            p.drawLine(0, ny, w, ny)
            p.setBrush(danger)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(0, ny - 4, 8, 8)

        p.end()


# ── hour gutter ──────────────────────────────────────────────────────────────


class _Gutter(QWidget):
    """Hour labels along the left edge of the grid."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(_GUTTER_W)
        self.setFixedHeight(_GRID_H)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        colors = theme_colors(get_config().theme)
        fg = QColor(colors.get("text", "#c0caf5"))
        muted = QColor(colors.get("text-muted", "#565f89"))
        font = p.font()
        font.setPixelSize(13)

        for hour in range(24):
            y = hour * HOUR_HEIGHT + _TOP
            bold = hour in _BOLD_HOURS
            font.setWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
            p.setFont(font)
            p.setPen(fg if bold else muted)

            if hour == 0:
                txt = "12 AM"
            elif hour < 12:
                txt = f"{hour} AM"
            elif hour == 12:
                txt = "12 PM"
            else:
                txt = f"{hour - 12} PM"

            p.drawText(
                0,
                y - 8,
                _GUTTER_W - 8,
                20,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                txt,
            )
        p.end()


# ── main strip widget ────────────────────────────────────────────────────────


class ActivityWeekStrip(QWidget):
    """Seven-day activity timeline strip.

    Shows completed sessions as colored blocks proportional to their duration,
    and active sessions as fixed one-hour pulsing green cards.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active_blocks: list[_SessionBlock] = []
        self._build()

        # Fixed height: header + full 24-hour grid, no internal scrolling.
        # The parent dashboard's scroll area handles viewport clipping.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(_GRID_H + _HEADER_H + 4)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(200)
        self._pulse_timer.timeout.connect(self._pulse_tick)

    # ── layout ───────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Day-name header row
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 4)
        hdr.setSpacing(0)

        gutter_spacer = QWidget()
        gutter_spacer.setFixedWidth(_GUTTER_W)
        hdr.addWidget(gutter_spacer)

        self._day_lbls: list[QLabel] = []
        for _ in range(7):
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedHeight(_HEADER_H)
            lbl.setObjectName("dayHeader")
            self._day_lbls.append(lbl)
            hdr.addWidget(lbl, 1)

        root.addLayout(hdr)

        # Grid area: gutter + 7 day columns at full 24-hour height.
        # No internal scroll — the parent dashboard scroll area clips.
        g_lay = QHBoxLayout()
        g_lay.setContentsMargins(0, 0, 0, 0)
        g_lay.setSpacing(0)

        self._gutter = _Gutter()
        g_lay.addWidget(self._gutter)

        self._cols: list[_DayCol] = []
        for _ in range(7):
            col = _DayCol()
            self._cols.append(col)
            g_lay.addWidget(col, 1)

        root.addLayout(g_lay)

    # ── data ─────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload session data for the current week and rebuild blocks."""
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        dates = [monday + timedelta(days=i) for i in range(7)]

        colors = theme_colors(get_config().theme)
        chip_text = colors.get("chip_text", "#ffffff")
        active_green = colors.get("success", "#9ece6a")

        # Update day-name headers
        for i, d in enumerate(dates):
            lbl = self._day_lbls[i]
            lbl.setText(f"{d.strftime('%a')} {d.day}")
            if d == today:
                lbl.setStyleSheet(
                    f"color: {colors.get('accent', '#7aa2f7')}; font-weight: 700; font-size: 13px;"
                )
            else:
                lbl.setStyleSheet(f"color: {colors.get('text', '#c0caf5')}; font-size: 13px;")

        # Set dates and clear old blocks
        for col, d in zip(self._cols, dates, strict=False):
            col.set_date(d)
            col.clear_blocks()

        # Build set of background activity names to exclude
        bg_names = {a.name for a in list_activities(is_background=True)}

        # Fetch completed sessions for this week
        next_monday = monday + timedelta(days=7)
        completed = get_sessions(
            start_date=datetime.combine(monday, datetime.min.time()),
            end_date=datetime.combine(next_monday, datetime.min.time()),
            limit=500,
        )
        active = get_active_sessions()

        self._active_blocks.clear()

        for s in completed:
            if s.activity_name in bg_names:
                continue
            self._place(s, dates, chip_text, active_green, is_active=False)
        for s in active:
            if s.activity_name in bg_names:
                continue
            self._place(s, dates, chip_text, active_green, is_active=True)

        # Pulse timer: run only while active sessions exist
        if self._active_blocks and not self._pulse_timer.isActive():
            self._pulse_timer.start()
        elif not self._active_blocks and self._pulse_timer.isActive():
            self._pulse_timer.stop()

    def _place(
        self,
        session: Session,
        dates: list[date],
        chip_text: str,
        active_green: str,
        *,
        is_active: bool,
    ) -> None:
        """Create and position a block for *session* in any overlapping column."""
        if session.start_time is None:
            return
        for i, d in enumerate(dates):
            span = _clip_to_day(session, d, is_active=is_active)
            if span is None:
                continue
            start_min, end_min = span
            block = _SessionBlock()
            color = (
                active_green
                if is_active
                else _activity_color(
                    session.activity_name,
                )
            )
            block.configure(
                session.activity_name,
                color,
                chip_text,
                is_active=is_active,
            )
            self._cols[i].add_block(block, start_min, end_min)
            if is_active:
                self._active_blocks.append(block)

    # ── animation ────────────────────────────────────────────────────────

    def _pulse_tick(self) -> None:
        t = _time.time()
        # Gentle pulse: alpha oscillates between 0.55 and 1.0 over ~2 seconds
        alpha = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(t * math.pi))
        for b in self._active_blocks:
            b.set_pulse_alpha(alpha)


# ── module-level helpers ─────────────────────────────────────────────────────


def _clip_to_day(
    session: Session,
    day: date,
    *,
    is_active: bool,
) -> tuple[int, int] | None:
    """Return (start_minutes, end_minutes) of *session* clipped to *day*.

    Active sessions are rendered as a fixed one-hour block from start_time.
    Returns ``None`` if the session does not overlap with *day*.
    """
    if session.start_time is None:
        return None

    day_start = datetime.combine(day, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    s_start = session.start_time
    s_end = s_start + timedelta(hours=1) if is_active else (session.end_time or datetime.now())

    # No overlap with this day
    if s_start >= day_end or s_end <= day_start:
        return None

    clipped_start = max(s_start, day_start)
    clipped_end = min(s_end, day_end)

    sm = clipped_start.hour * 60 + clipped_start.minute
    em = clipped_end.hour * 60 + clipped_end.minute
    if clipped_end >= day_end:
        em = 24 * 60
    if em <= sm:
        return None
    return (sm, em)
