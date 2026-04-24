"""Tests for SummaryView calculations and display logic."""

from datetime import datetime, timedelta

from grouper.ui.summary import SummaryView
from grouper_core.database.boards import create_board
from grouper_core.database.projects import create_project
from grouper_core.database.tasks import create_task


def _wait_for_refresh(view: SummaryView, qapp) -> None:
    """Run event loop until the refresh timer finishes."""
    while view._refresh_timer.isActive():
        qapp.processEvents()
    qapp.processEvents()


def test_summary_completion_rate_cap(qapp):
    """Test that completion rate does not exceed 100% when many older tasks are completed."""
    b = create_board("Test Board")
    assert b.id is not None
    proj = create_project("Test Proj", b.id)
    assert proj.id is not None
    proj_id = proj.id

    now = datetime.now()

    # Create 1 task recently (in range)
    t1 = create_task(proj_id, "Recent Task")
    from grouper_core.database.connection import get_connection

    with get_connection() as conn:
        conn.execute("UPDATE tasks SET created_at = ? WHERE id = ?", (now.isoformat(), t1.id))
        conn.commit()

    # Create 5 tasks with old creation dates (out of range) but complete them today (in range)
    for i in range(5):
        t = create_task(proj_id, f"Old Task {i}")
        old_date = now - timedelta(days=20)
        with get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET created_at = ?, is_completed = 1, completed_at = ? WHERE id = ?",
                (old_date.isoformat(), now.isoformat(), t.id),
            )
            conn.commit()

    # Complete the recent task too
    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET is_completed = 1, completed_at = ? WHERE id = ?",
            (now.isoformat(), t1.id),
        )
        conn.commit()

    view = SummaryView()
    _wait_for_refresh(view, qapp)

    assert view._task_stats_num_lbl[0].text() == "1"  # Created
    assert view._task_stats_num_lbl[1].text() == "6"  # Completed
    assert view._task_stats_num_lbl[6].text() == "100%"  # Completion Rate


def test_summary_overdue_today(qapp):
    """Test that tasks due today but later in the day are not marked as overdue."""
    b = create_board("Test Board 2")
    assert b.id is not None
    proj = create_project("Test Proj 2", b.id)
    assert proj.id is not None
    proj_id = proj.id

    now = datetime.now()
    t1 = create_task(proj_id, "Due Today Task")
    t2 = create_task(proj_id, "Due Yesterday Task")

    yesterday = now - timedelta(days=1)

    from grouper_core.database.connection import get_connection

    with get_connection() as conn:
        conn.execute("UPDATE tasks SET due_date = ? WHERE id = ?", (now.isoformat(), t1.id))
        conn.execute("UPDATE tasks SET due_date = ? WHERE id = ?", (yesterday.isoformat(), t2.id))
        conn.commit()

    view = SummaryView()
    _wait_for_refresh(view, qapp)

    assert view._task_stats_num_lbl[3].text() == "1"  # Overdue
    assert view._task_stats_num_lbl[4].text() == "1"  # Due Soon


def test_trend_bars_update_on_theme_switch(qapp):
    """MiniBarTrend bars must recompute their inline colors when the theme changes."""
    from unittest.mock import patch

    from grouper.styles import load_theme
    from grouper.ui.summary import MiniBarTrend

    dark_cfg = type("C", (), {"theme": "dark"})()
    light_cfg = type("C", (), {"theme": "light"})()

    with patch("grouper.ui.summary.get_config", return_value=dark_cfg):
        load_theme(qapp, "dark")
        chart = MiniBarTrend()
        chart.update_data([("M", 3600.0), ("T", 7200.0)], bar_width=22)
        old_sheet = chart._bars[0]._bar.styleSheet()

    with patch("grouper.ui.summary.get_config", return_value=light_cfg):
        load_theme(qapp, "light")
        qapp.processEvents()

    new_sheet = chart._bars[0]._bar.styleSheet()
    assert new_sheet != old_sheet, (
        "Trend bar inline stylesheet did not change after theme switch"
    )
