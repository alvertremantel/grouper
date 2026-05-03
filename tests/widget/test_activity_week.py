"""Tests for the activity week strip widget."""

from datetime import date, datetime

from desktop.models import Session
from desktop.ui.time.activity_week import (
    _GRID_H,
    _TOP,
    HOUR_HEIGHT,
    ActivityWeekStrip,
    _activity_color,
    _clip_to_day,
    _DayCol,
    _SessionBlock,
)
from PySide6.QtWidgets import QApplication

# ── color assignment ─────────────────────────────────────────────────────────


class TestActivityColor:
    def test_deterministic(self) -> None:
        assert _activity_color("Code") == _activity_color("Code")

    def test_different_activities_can_differ(self) -> None:
        # Not guaranteed for all pairs, but these two hash differently
        colors = {_activity_color(f"Activity{i}") for i in range(20)}
        assert len(colors) > 1

    def test_returns_hex_string(self) -> None:
        c = _activity_color("Test")
        assert c.startswith("#")
        assert len(c) == 7


# ── day clipping ─────────────────────────────────────────────────────────────


class TestClipToDay:
    def test_session_within_day(self) -> None:
        s = Session(
            id=1,
            activity_name="X",
            start_time=datetime(2026, 3, 25, 9, 0),
            end_time=datetime(2026, 3, 25, 11, 30),
        )
        result = _clip_to_day(s, date(2026, 3, 25), is_active=False)
        assert result == (540, 690)

    def test_no_overlap_returns_none(self) -> None:
        s = Session(
            id=1,
            activity_name="X",
            start_time=datetime(2026, 3, 25, 9, 0),
            end_time=datetime(2026, 3, 25, 11, 0),
        )
        assert _clip_to_day(s, date(2026, 3, 26), is_active=False) is None

    def test_midnight_crossing_first_day(self) -> None:
        s = Session(
            id=1,
            activity_name="Night",
            start_time=datetime(2026, 3, 25, 23, 0),
            end_time=datetime(2026, 3, 26, 2, 0),
        )
        result = _clip_to_day(s, date(2026, 3, 25), is_active=False)
        assert result == (1380, 1440)

    def test_midnight_crossing_second_day(self) -> None:
        s = Session(
            id=1,
            activity_name="Night",
            start_time=datetime(2026, 3, 25, 23, 0),
            end_time=datetime(2026, 3, 26, 2, 0),
        )
        result = _clip_to_day(s, date(2026, 3, 26), is_active=False)
        assert result == (0, 120)

    def test_active_session_fixed_one_hour(self) -> None:
        s = Session(
            id=1,
            activity_name="Active",
            start_time=datetime(2026, 3, 25, 14, 0),
        )
        result = _clip_to_day(s, date(2026, 3, 25), is_active=True)
        assert result == (840, 900)

    def test_active_session_no_overlap_different_day(self) -> None:
        s = Session(
            id=1,
            activity_name="Active",
            start_time=datetime(2026, 3, 25, 14, 0),
        )
        assert _clip_to_day(s, date(2026, 3, 26), is_active=True) is None

    def test_none_start_time_returns_none(self) -> None:
        s = Session(id=1, activity_name="X")
        assert _clip_to_day(s, date(2026, 3, 25), is_active=False) is None


# ── widget structure ─────────────────────────────────────────────────────────


class TestActivityWeekStrip:
    def test_seven_columns(self, qapp: QApplication) -> None:
        strip = ActivityWeekStrip()
        assert len(strip._cols) == 7

    def test_seven_day_labels(self, qapp: QApplication) -> None:
        strip = ActivityWeekStrip()
        assert len(strip._day_lbls) == 7

    def test_refresh_populates_headers(self, qapp: QApplication) -> None:
        strip = ActivityWeekStrip()
        strip.resize(800, 500)
        strip.refresh()
        texts = [lbl.text() for lbl in strip._day_lbls]
        # All 7 labels should have text like "Mon 23"
        assert all(len(t) > 0 for t in texts)
        assert len(texts) == 7

    def test_today_highlighted_in_accent(self, qapp: QApplication) -> None:
        strip = ActivityWeekStrip()
        strip.resize(800, 500)
        strip.refresh()
        today = date.today()
        today_idx = today.weekday()  # 0=Mon
        lbl = strip._day_lbls[today_idx]
        assert "font-weight: 700" in lbl.styleSheet()


class TestDayCol:
    def test_fixed_height(self, qapp: QApplication) -> None:
        col = _DayCol()
        assert col.maximumHeight() == _GRID_H
        assert col.minimumHeight() == _GRID_H

    def test_add_and_clear_blocks(self, qapp: QApplication) -> None:
        col = _DayCol()
        col.resize(120, _GRID_H)
        block = _SessionBlock()
        block.configure("Test", "#7aa2f7", "#ffffff")
        col.add_block(block, 540, 660)
        assert len(col._blocks) == 1
        col.clear_blocks()
        assert len(col._blocks) == 0

    def test_block_geometry(self, qapp: QApplication) -> None:
        col = _DayCol()
        col.resize(120, _GRID_H)
        block = _SessionBlock()
        block.configure("Test", "#7aa2f7", "#ffffff")
        col.add_block(block, 540, 720)  # 9am-12pm = 3 hours
        expected_y = int(540 / 60 * HOUR_HEIGHT) + _TOP + 1
        expected_h = int(180 / 60 * HOUR_HEIGHT) - 2
        assert block.geometry().y() == expected_y
        assert block.geometry().height() == expected_h


class TestSessionBlock:
    def test_configure_sets_label(self, qapp: QApplication) -> None:
        block = _SessionBlock()
        block.configure("Programming", "#7aa2f7", "#ffffff")
        assert block._label.text() == "Programming"

    def test_active_block_responds_to_pulse(self, qapp: QApplication) -> None:
        block = _SessionBlock()
        block.configure("X", "#9ece6a", "#ffffff", is_active=True)
        block.set_pulse_alpha(0.5)
        assert block._pulse_alpha == 0.5

    def test_inactive_block_ignores_pulse(self, qapp: QApplication) -> None:
        block = _SessionBlock()
        block.configure("X", "#7aa2f7", "#ffffff", is_active=False)
        block.set_pulse_alpha(0.5)
        assert block._pulse_alpha == 1.0  # unchanged
