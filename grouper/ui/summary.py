"""
summary.py — Analytical Summary view for Grouper.

Shows time-tracking totals and task completion stats
over a configurable date range.  Uses pure-widget charts (no external deps).
All section frames are pre-allocated in _build(); refresh() updates them
in-place to avoid widget destruction and console flash.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import ClassVar

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..config import get_config
from ..database import (
    get_activities_by_group,
    get_all_groups,
    get_completed_tasks,
    get_summary,
    get_summary_by_day,
    get_tasks,
    list_events_for_range,
    list_projects,
)
from ..database.connection import get_notifier
from ..styles import lerp_hex, theme_colors
from .widgets import clear_layout, show_or_empty

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_seconds(seconds: float) -> str:
    """Format a duration in seconds as 'Xh Ym' or 'Zm'."""
    s = int(seconds)
    h, m = divmod(s // 60, 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def _parse_dt(val: object) -> datetime | None:
    """Safely parse a datetime from a DB field (may be str or datetime)."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Chart widgets
# ---------------------------------------------------------------------------


class _BarRow(QWidget):
    """A single row in HBarChart: name | bar track | value."""

    LABEL_WIDTH = 140

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._name_lbl = QLabel()
        self._name_lbl.setFixedWidth(self.LABEL_WIDTH)
        self._name_lbl.setObjectName("mutedLabel")
        row.addWidget(self._name_lbl)

        self._track = QFrame()
        self._track.setObjectName("summaryBarBg")
        self._track.setFixedHeight(14)
        self._track.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._track_layout = QHBoxLayout(self._track)
        self._track_layout.setContentsMargins(0, 0, 0, 0)
        self._track_layout.setSpacing(0)

        self._bar = QFrame()
        self._bar.setObjectName("summaryBar")
        self._bar.setFixedHeight(14)
        self._bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Start with 50/50 fill
        self._track_layout.addWidget(self._bar, 500)
        self._track_layout.addStretch(500)
        row.addWidget(self._track)

        self._val_lbl = QLabel()
        self._val_lbl.setObjectName("accentLabel")
        self._val_lbl.setFixedWidth(72)
        self._val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self._val_lbl)

    def populate(self, name: str, fill_ratio: float, label: str) -> None:
        self._name_lbl.setText(name)
        self._name_lbl.setToolTip(name)
        fill = max(1, int(fill_ratio * 1000))
        empty = 1000 - fill
        while self._track_layout.count():
            self._track_layout.takeAt(0)
        self._track_layout.addWidget(self._bar, fill)
        if empty > 0:
            self._track_layout.addStretch(empty)
        self._val_lbl.setText(label)


class HBarChart(QWidget):
    """Horizontal bar chart — pre-allocated rows, updated in-place."""

    MAX_BARS = 20
    VISIBLE_LIMIT = 10

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._rows: list[_BarRow] = []
        for _ in range(self.MAX_BARS):
            row = _BarRow()
            row.setVisible(False)
            layout.addWidget(row)
            self._rows.append(row)

        self._expanded: bool = False
        self._all_rows_data: list[tuple[str, float, str]] = []
        self._total: int = 0

        self._overflow_btn = QPushButton()
        self._overflow_btn.setObjectName("linkButton")
        self._overflow_btn.setVisible(False)
        self._overflow_btn.clicked.connect(self._toggle_expand)
        layout.addWidget(self._overflow_btn)
        layout.addStretch(1)

    def update_data(self, rows: list[tuple[str, float, str]], max_val: float) -> None:
        self._all_rows_data = rows
        self._total = len(rows)
        self._expanded = False
        safe_max = max_val if max_val > 0 else 1.0

        visible_count = min(self.VISIBLE_LIMIT, self._total)
        for i in range(visible_count):
            name, val, label = rows[i]
            self._rows[i].populate(name, val / safe_max, label)
            self._rows[i].setVisible(True)
        for i in range(visible_count, self.MAX_BARS):
            self._rows[i].setVisible(False)

        hidden_count = self._total - self.VISIBLE_LIMIT
        if hidden_count > 0:
            self._overflow_btn.setText(f"+ {hidden_count} more")
            self._overflow_btn.setVisible(True)
        else:
            self._overflow_btn.setVisible(False)

    def _toggle_expand(self) -> None:
        self._expanded = not self._expanded
        safe_max = max((v for _, v, _ in self._all_rows_data), default=1.0) or 1.0

        if self._expanded:
            visible_count = min(self.MAX_BARS, self._total)
            for i in range(self.VISIBLE_LIMIT, visible_count):
                name, val, label = self._all_rows_data[i]
                self._rows[i].populate(name, val / safe_max, label)
                self._rows[i].setVisible(True)
            self._overflow_btn.setText("▲ show less")
        else:
            for i in range(self.VISIBLE_LIMIT, self.MAX_BARS):
                self._rows[i].setVisible(False)
            hidden_count = self._total - self.VISIBLE_LIMIT
            self._overflow_btn.setText(f"+ {hidden_count} more")


class _TrendBar(QWidget):
    """A single vertical bar column in MiniBarTrend."""

    MIN_BAR_FRACTION = 0.07  # minimum bar height as fraction of available space

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("summaryTrendCol")
        col_layout = QVBoxLayout(self)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(0)

        self._spacer = QWidget()
        self._spacer.setObjectName("summaryTrendSpacer")
        self._spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        col_layout.addWidget(self._spacer)

        self._bar = QFrame()
        self._bar.setObjectName("summaryTrendBar")
        self._bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._bar.setMinimumHeight(4)
        col_layout.addWidget(self._bar)

        self._day_lbl = QLabel()
        self._day_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._day_lbl.setObjectName("smallMuted")
        self._day_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col_layout.addWidget(self._day_lbl)

    def populate(self, day_label: str, val: float, max_val: float, color_hex: str = "") -> None:
        ratio = max(self.MIN_BAR_FRACTION, val / max(max_val, 1.0))
        col_layout = self.layout()
        col_layout.setStretch(0, round((1.0 - ratio) * 1000))
        col_layout.setStretch(1, round(ratio * 1000))
        if color_hex:
            self._bar.setStyleSheet(f"background-color: {color_hex}; border-radius: 2px;")
        self._day_lbl.setText(day_label)


class MiniBarTrend(QWidget):
    """Daily sparkline — pre-allocated bar columns, updated in-place."""

    MAX_BARS = 90

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("summaryTrendChart")
        self.setMinimumHeight(120)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        self._bars_row = QHBoxLayout()
        self._bars_row.setContentsMargins(0, 0, 0, 0)
        self._bars_row.setSpacing(2)

        self._bars: list[_TrendBar] = []
        for _ in range(self.MAX_BARS):
            b = _TrendBar()
            b.setVisible(False)
            self._bars_row.addWidget(b, 1)
            self._bars.append(b)

        outer.addLayout(self._bars_row, 1)

    def update_data(self, days: list[tuple[str, float]], bar_width: int = 22) -> None:
        max_val = max((v for _, v in days), default=1.0) or 1.0
        colors = theme_colors(get_config().theme)
        card_bg = colors.get("card_bg", "#24263a")
        accent = colors["accent"]
        gap = 2 if bar_width >= 10 else 1
        self._bars_row.setSpacing(gap)
        for i, (label, val) in enumerate(days[: self.MAX_BARS]):
            ratio = val / max_val
            color = lerp_hex(card_bg, accent, 0.2 + 0.8 * ratio)
            self._bars[i].populate(label, val, max_val, color)
            self._bars[i].setVisible(True)
        for i in range(len(days), self.MAX_BARS):
            self._bars[i].setVisible(False)


# ---------------------------------------------------------------------------
# Summary view
# ---------------------------------------------------------------------------


class SummaryView(QWidget):
    """Analytical view of time, tasks, and calendar over a configurable range."""

    RANGES: ClassVar[list[tuple[str, int]]] = [
        ("Last 7 days", 7),
        ("Last 14 days", 14),
        ("Last 30 days", 30),
        ("Last 90 days", 90),
    ]

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

    # -- layout --------------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        # Header row: title + range selector
        header = QHBoxLayout()
        heading = QLabel("Summary")
        heading.setProperty("heading", True)
        header.addWidget(heading)
        header.addStretch()

        self._range_combo = QComboBox()
        for label, _ in self.RANGES:
            self._range_combo.addItem(label)
        self._range_combo.currentIndexChanged.connect(self.refresh)
        header.addWidget(self._range_combo)

        outer.addLayout(header)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self._content = QVBoxLayout(container)
        self._content.setContentsMargins(0, 0, 0, 0)
        self._content.setSpacing(16)
        scroll.setWidget(container)
        outer.addWidget(scroll)

        # -- Pre-allocate all section cards ----------------------------------

        # Stat strip (no title)
        self._stat_card, self._stat_inner = self._make_card("")
        self._stat_num_lbl: list[QLabel] = []
        stats_row = QHBoxLayout()
        stats_row.setSpacing(0)
        for val_text, sub_text in [
            ("—", "Total Tracked"),
            ("—", "Active Days"),
            ("—", "Calendar Events"),
        ]:
            col = QVBoxLayout()
            num = QLabel(val_text)
            num.setObjectName("accentLabel")
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(num)
            sub = QLabel(sub_text)
            sub.setObjectName("mutedLabel")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(sub)
            stats_row.addLayout(col)
            self._stat_num_lbl.append(num)
        self._stat_inner.addLayout(stats_row)
        self._content.addWidget(self._stat_card)

        # Activity + Group side row
        self._act_card, self._act_inner = self._make_card("Time by Activity")
        self._act_chart = HBarChart()
        self._act_empty = QLabel("No data for this period.")
        self._act_empty.setObjectName("mutedLabel")
        self._act_inner.addWidget(self._act_chart)
        self._act_inner.addWidget(self._act_empty)

        self._group_card, self._group_inner = self._make_card("Time by Group")
        self._group_chart = HBarChart()
        self._group_empty = QLabel("No data for this period.")
        self._group_empty.setObjectName("mutedLabel")
        self._group_inner.addWidget(self._group_chart)
        self._group_inner.addWidget(self._group_empty)

        act_group_row = QHBoxLayout()
        act_group_row.setSpacing(16)
        act_group_row.addWidget(self._act_card, 1)
        act_group_row.addWidget(self._group_card, 1)
        act_group_container = QWidget()
        act_group_container.setLayout(act_group_row)
        self._content.addWidget(act_group_container)

        # Daily trend card
        self._trend_card, self._trend_inner = self._make_card("Daily Time Trend")
        self._trend_chart = MiniBarTrend()
        self._trend_empty = QLabel("No data for this period.")
        self._trend_empty.setObjectName("mutedLabel")
        self._trend_inner.addWidget(self._trend_chart, 1)
        self._trend_inner.addWidget(self._trend_empty)
        self._trend_card.setSizePolicy(
            self._trend_card.sizePolicy().horizontalPolicy(),
            QSizePolicy.Policy.Expanding,
        )
        self._trend_chart.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._content.addWidget(self._trend_card, 1)

        # Full-width task stats card
        self._task_stats_card, self._task_stats_inner = self._make_card("Task Completion")
        self._task_stats_num_lbl: list[QLabel] = []
        self._task_stats_meta_lbl: list[QLabel] = []
        ts_grid = QGridLayout()
        ts_grid.setHorizontalSpacing(24)
        ts_grid.setVerticalSpacing(12)
        ts_grid.setContentsMargins(0, 0, 0, 0)
        for val_text, sub_text in [
            ("—", "Created"),
            ("—", "Completed"),
            ("—", "Remaining"),
            ("—", "Overdue"),
            ("—", "Due Soon"),
            ("—", "Starred"),
            ("—", "Completion Rate"),
            ("—", "Avg Completion"),
        ]:
            col = QVBoxLayout()
            num = QLabel(val_text)
            num.setObjectName("accentLabel")
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(num)

            meta = QLabel("")
            meta.setObjectName("smallMuted")
            meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
            meta.setVisible(False)
            col.addWidget(meta)

            sub = QLabel(sub_text)
            sub.setObjectName("mutedLabel")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(sub)
            index = len(self._task_stats_num_lbl)
            ts_grid.addLayout(col, index // 4, index % 4)
            self._task_stats_num_lbl.append(num)
            self._task_stats_meta_lbl.append(meta)
        self._task_stats_inner.addLayout(ts_grid)

        self._task_stats_bar = QProgressBar()
        self._task_stats_bar.setRange(0, 100)
        self._task_stats_bar.setValue(0)
        self._task_stats_bar.setTextVisible(False)
        self._task_stats_bar.setFixedHeight(8)
        self._task_stats_inner.addWidget(self._task_stats_bar)

        self._task_stats_prio_lbl = QLabel("By priority:")
        self._task_stats_prio_lbl.setObjectName("mutedLabel")
        self._task_stats_inner.addWidget(self._task_stats_prio_lbl)

        self._task_stats_prio_row_widget = QWidget()
        self._task_stats_prio_row = QHBoxLayout(self._task_stats_prio_row_widget)
        self._task_stats_prio_row.setSpacing(8)
        self._task_stats_inner.addWidget(self._task_stats_prio_row_widget)

        self._task_stats_empty = QLabel("No data for this period.")
        self._task_stats_empty.setObjectName("mutedLabel")
        self._task_stats_inner.addWidget(self._task_stats_empty)
        self._content.addWidget(self._task_stats_card)

    def _make_card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        """Create a titled card. Returns (frame, inner_layout)."""
        frame = QFrame()
        frame.setObjectName("card")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        if title:
            lbl = QLabel(title)
            lbl.setProperty("subheading", True)
            lay.addWidget(lbl)
        return frame, lay

    # -- helpers -------------------------------------------------------------

    def _date_range(self) -> tuple[datetime, datetime]:
        days = self.RANGES[self._range_combo.currentIndex()][1]
        end = datetime.now()
        start = end - timedelta(days=days)
        return start, end

    # -- refresh -------------------------------------------------------------

    def refresh(self) -> None:
        self.setUpdatesEnabled(False)
        try:
            self._do_refresh()
        finally:
            self.setUpdatesEnabled(True)

    def _do_refresh(self) -> None:
        start, end = self._date_range()

        # --- Stat strip ---
        data = get_summary(start_date=start, end_date=end)
        events = list_events_for_range(start, end)
        if data or events:
            total_secs = sum(data.values())
            n_days = max(1, (end - start).days)
            by_day = get_summary_by_day(start_date=start, end_date=end)
            active_days = len(
                {d for day_map in by_day.values() for d, v in day_map.items() if v > 0}
            )
            self._stat_num_lbl[0].setText(_fmt_seconds(total_secs))
            self._stat_num_lbl[1].setText(f"{active_days} / {n_days}")
            self._stat_num_lbl[2].setText(str(len(events)))
            self._stat_card.setVisible(True)
        else:
            self._stat_card.setVisible(False)

        # --- Activity chart ---
        if data:
            sorted_items = sorted(data.items(), key=lambda x: x[1], reverse=True)
            max_val = float(sorted_items[0][1])
            rows: list[tuple[str, float, str]] = [
                (name, float(secs), _fmt_seconds(secs)) for name, secs in sorted_items
            ]
            self._act_chart.update_data(rows, max_val)
            show_or_empty(True, self._act_chart, empty=self._act_empty)
        else:
            show_or_empty(False, self._act_chart, empty=self._act_empty)

        # --- Daily trend ---
        by_day_all = get_summary_by_day(start_date=start, end_date=end)
        day_totals: dict[str, float] = {}
        for day_map in by_day_all.values():
            for day_str, secs in day_map.items():
                day_totals[day_str] = day_totals.get(day_str, 0.0) + secs

        if day_totals:
            n_days = max(1, (end - start).days)
            all_days: list[tuple[str, float]] = []
            cursor = start
            for i in range(n_days):
                day_str = cursor.strftime("%Y-%m-%d")
                k = 1 if n_days <= 7 else (2 if n_days <= 14 else (7 if n_days <= 30 else 14))
                label = cursor.strftime("%a")[:1] if i % k == 0 else ""
                all_days.append((label, day_totals.get(day_str, 0.0)))
                cursor += timedelta(days=1)
            bar_w = 22 if n_days <= 7 else (16 if n_days <= 14 else (10 if n_days <= 30 else 6))
            self._trend_chart.update_data(all_days, bar_w)
            show_or_empty(True, self._trend_chart, empty=self._trend_empty)
        else:
            show_or_empty(False, self._trend_chart, empty=self._trend_empty)

        # --- Task stats ---
        tasks_in_range: list = []
        open_tasks: list = []
        for proj in list_projects():
            if getattr(proj, "is_archived", False) or proj.id is None:
                continue
            for task in get_tasks(proj.id):
                if not task.is_completed:
                    open_tasks.append(task)
                created_at = _parse_dt(task.created_at)
                if created_at and start <= created_at <= end:
                    tasks_in_range.append(task)

        completed_in_range = [
            t
            for t in get_completed_tasks(None)
            if (ca := _parse_dt(t.completed_at)) is not None and start <= ca <= end
        ]

        created_count = len(tasks_in_range)
        completed_count = len(completed_in_range)
        remaining = max(0, created_count - completed_count)
        overdue_count = sum(
            1
            for task in open_tasks
            if (due := _parse_dt(task.due_date)) is not None and due.date() < end.date()
        )
        due_soon_cutoff = end + timedelta(days=7)
        due_soon_count = sum(
            1
            for task in open_tasks
            if (due := _parse_dt(task.due_date)) is not None
            and end.date() <= due.date() <= due_soon_cutoff.date()
        )
        starred_count = sum(1 for task in open_tasks if task.is_starred)
        completion_rate = (
            min(100, int(completed_count * 100 / created_count)) if created_count > 0 else 0
        )

        completion_days = [
            max(0.0, (completed_at - created_at).total_seconds() / 86400)
            for task in completed_in_range
            if (created_at := _parse_dt(task.created_at)) is not None
            and (completed_at := _parse_dt(task.completed_at)) is not None
        ]
        avg_completion_days = (
            sum(completion_days) / len(completion_days) if completion_days else None
        )
        has_task_data = any(
            count > 0
            for count in (
                created_count,
                completed_count,
                remaining,
                overdue_count,
                due_soon_count,
                starred_count,
            )
        )

        if not has_task_data:
            for num_lbl in self._task_stats_num_lbl:
                num_lbl.setText("0")
            for meta_lbl in self._task_stats_meta_lbl:
                meta_lbl.clear()
                meta_lbl.setVisible(False)
            self._task_stats_bar.setVisible(False)
            self._task_stats_prio_lbl.setVisible(False)
            self._task_stats_prio_row_widget.setVisible(False)
            self._task_stats_empty.setVisible(True)
        else:
            self._task_stats_num_lbl[0].setText(str(created_count))
            self._task_stats_num_lbl[1].setText(str(completed_count))
            self._task_stats_num_lbl[2].setText(str(remaining))
            self._task_stats_num_lbl[3].setText(str(overdue_count))
            self._task_stats_num_lbl[4].setText(str(due_soon_count))
            self._task_stats_num_lbl[5].setText(str(starred_count))
            self._task_stats_num_lbl[6].setText(f"{completion_rate}%")
            self._task_stats_num_lbl[7].setText(
                f"{avg_completion_days:.1f}d" if avg_completion_days is not None else "—"
            )

            for meta_lbl in self._task_stats_meta_lbl:
                meta_lbl.clear()
                meta_lbl.setVisible(False)

            self._task_stats_meta_lbl[2].setText("Created minus completed")
            self._task_stats_meta_lbl[2].setVisible(True)
            self._task_stats_meta_lbl[3].setText("Needs attention")
            self._task_stats_meta_lbl[3].setVisible(overdue_count > 0)
            self._task_stats_meta_lbl[4].setText("Next 7 days")
            self._task_stats_meta_lbl[4].setVisible(due_soon_count > 0)
            self._task_stats_meta_lbl[5].setText("Open flagged tasks")
            self._task_stats_meta_lbl[5].setVisible(starred_count > 0)
            self._task_stats_meta_lbl[6].setText(f"{completed_count} of {created_count} closed")
            self._task_stats_meta_lbl[6].setVisible(created_count > 0)
            self._task_stats_meta_lbl[7].setText(
                "From tasks completed in range" if avg_completion_days is not None else ""
            )
            self._task_stats_meta_lbl[7].setVisible(avg_completion_days is not None)

            if created_count > 0:
                self._task_stats_bar.setValue(completion_rate)
                self._task_stats_bar.setVisible(True)
            else:
                self._task_stats_bar.setVisible(False)
            # Priority breakdown
            priority_counts: dict[int, int] = {}
            for task in tasks_in_range:
                p = task.priority
                priority_counts[p] = priority_counts.get(p, 0) + 1
            if priority_counts:
                # Clear and repopulate priority chip labels only
                clear_layout(self._task_stats_prio_row)
                for p in sorted(priority_counts):
                    count = priority_counts[p]
                    obj = f"priority{p}" if 1 <= p <= 5 else "mutedLabel"
                    chip = QLabel(f"P{p}: {count}")
                    chip.setObjectName(obj)
                    self._task_stats_prio_row.addWidget(chip)
                self._task_stats_prio_row.addStretch()
                self._task_stats_prio_lbl.setVisible(True)
                self._task_stats_prio_row_widget.setVisible(True)
            else:
                self._task_stats_prio_lbl.setVisible(False)
                self._task_stats_prio_row_widget.setVisible(False)
            self._task_stats_empty.setVisible(False)

        # --- Group breakdown ---
        groups = get_all_groups()
        if groups and data:
            group_totals: dict[str, float] = {}
            for group in groups:
                acts = get_activities_by_group(group)
                total = sum(float(data.get(a.name, 0)) for a in acts)
                if total > 0:
                    group_totals[group] = total
            if group_totals:
                sorted_groups = sorted(group_totals.items(), key=lambda x: x[1], reverse=True)
                max_val_g = sorted_groups[0][1]
                rows2: list[tuple[str, float, str]] = [
                    (name, val, _fmt_seconds(val)) for name, val in sorted_groups
                ]
                self._group_chart.update_data(rows2, max_val_g)
                self._group_chart.setVisible(True)
                self._group_empty.setVisible(False)
                self._group_card.setVisible(True)
            else:
                self._group_card.setVisible(False)
        else:
            self._group_card.setVisible(False)
