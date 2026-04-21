"""test_integration.py -- Integration tests for the full session lifecycle.

Tests exercise the complete session workflow end-to-end through the database
layer: create activity -> start session -> pause -> resume -> stop -> verify
all data is consistent.

Uses the ``isolated_db`` fixture from conftest for per-test DB isolation.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

# ===========================================================================
# Full lifecycle: start -> pause -> resume -> stop
# ===========================================================================


class TestFullSessionLifecycle:
    def test_start_pause_resume_stop(self):
        from grouper.database.activities import get_or_create_activity
        from grouper.database.sessions import (
            get_active_session_by_activity,
            get_active_sessions,
            get_sessions,
            pause_session,
            resume_session,
            start_session,
            stop_session,
        )

        # Create activity
        activity = get_or_create_activity("Integration Test")
        assert activity.name == "Integration Test"

        # Start a session
        session = start_session("Integration Test")
        assert session.id is not None
        assert session.activity_name == "Integration Test"
        assert session.start_time is not None
        assert session.end_time is None

        # Verify get_active_sessions returns it
        active = get_active_sessions()
        assert any(s.id == session.id for s in active)

        # Verify get_active_session_by_activity finds it
        found = get_active_session_by_activity("Integration Test")
        assert found is not None
        assert found.id == session.id

        # Pause the session
        time.sleep(0.1)
        paused = pause_session(session.id)
        assert paused is not None
        assert paused.is_paused is True

        # Let enough time pass while paused for int() truncation to yield >= 1
        time.sleep(1.1)

        # Resume the session
        resumed = resume_session(session.id)
        assert resumed is not None
        assert resumed.is_paused is False
        assert resumed.paused_seconds > 0

        # Stop the session with notes
        time.sleep(0.1)
        completed = stop_session("Integration Test", notes="lifecycle test done")
        assert len(completed) > 0

        # The stop_session with pause events splits into segments.
        # Verify segments have end_time and notes on the last segment.
        last_segment = completed[-1]
        assert last_segment.end_time is not None
        assert last_segment.notes == "lifecycle test done"

        # All segments should have positive duration
        for seg in completed:
            assert seg.end_time is not None
            duration = (seg.end_time - seg.start_time).total_seconds()
            assert duration >= 0

        # Verify get_active_sessions no longer returns it
        active_after = get_active_sessions()
        assert not any(s.id == session.id for s in active_after)

        # Verify get_sessions(activity_name=...) returns the completed segments
        history = get_sessions(activity_name="Integration Test")
        assert len(history) > 0
        assert all(s.activity_name == "Integration Test" for s in history)

    def test_start_stop_without_pause(self):
        from grouper.database.activities import get_or_create_activity
        from grouper.database.sessions import (
            get_active_sessions,
            get_sessions,
            start_session,
            stop_session,
        )

        get_or_create_activity("NoPause")
        session = start_session("NoPause")
        time.sleep(0.1)

        # Stop without ever pausing
        completed = stop_session("NoPause", notes="simple session")
        assert len(completed) == 1
        result = completed[0]
        assert result.end_time is not None
        assert result.notes == "simple session"
        assert result.duration_seconds >= 0

        # Should not be active anymore
        active = get_active_sessions()
        assert not any(s.id == session.id for s in active)

        # Should appear in history
        history = get_sessions(activity_name="NoPause")
        assert len(history) == 1


# ===========================================================================
# Multiple concurrent sessions
# ===========================================================================


class TestMultipleConcurrentSessions:
    def test_two_concurrent_sessions(self):
        from grouper.database.activities import get_or_create_activity
        from grouper.database.sessions import (
            get_active_sessions,
            start_session,
            stop_session,
        )

        get_or_create_activity("ActivityA")
        get_or_create_activity("ActivityB")

        session_a = start_session("ActivityA")
        session_b = start_session("ActivityB")

        # Both should be active
        active = get_active_sessions()
        active_ids = {s.id for s in active}
        assert session_a.id in active_ids
        assert session_b.id in active_ids

        # Stop one
        stop_session("ActivityA", notes="done with A")

        # Only B should remain active
        active_after = get_active_sessions()
        active_ids_after = {s.id for s in active_after}
        assert session_a.id not in active_ids_after
        assert session_b.id in active_ids_after

        # Stop the other
        stop_session("ActivityB", notes="done with B")

        # Both should be gone
        final_active = get_active_sessions()
        assert len(final_active) == 0

    def test_stop_all_sessions(self):
        from grouper.database.activities import get_or_create_activity
        from grouper.database.sessions import (
            get_active_sessions,
            start_session,
            stop_all_sessions,
        )

        get_or_create_activity("Alpha")
        get_or_create_activity("Beta")

        start_session("Alpha")
        start_session("Beta")

        active = get_active_sessions()
        assert len(active) == 2

        # Stop all at once
        stopped = stop_all_sessions(notes="batch stop")
        assert len(stopped) >= 2

        # None should remain
        remaining = get_active_sessions()
        assert len(remaining) == 0


# ===========================================================================
# Session with task attribution
# ===========================================================================


class TestSessionTaskAttribution:
    def test_session_with_task_id(self):
        import grouper.database.boards as boards
        import grouper.database.projects as projects
        import grouper.database.tasks as tasks
        from grouper.database.activities import get_or_create_activity
        from grouper.database.sessions import (
            get_sessions,
            start_session,
            stop_session,
        )

        # Create board -> project -> task
        board = boards.get_or_create_default_board()
        project = projects.create_project("TestProject", board_id=board.id)
        task = tasks.create_task(project.id, "Integration task")

        # Start and stop a session with task_id
        get_or_create_activity("TaskWork")
        start_session("TaskWork")
        time.sleep(0.1)
        completed = stop_session("TaskWork", task_id=task.id)

        assert len(completed) == 1
        assert completed[0].task_id == task.id

        # Verify via get_sessions
        history = get_sessions(activity_name="TaskWork")
        assert len(history) == 1
        assert history[0].task_id == task.id


# ===========================================================================
# Retroactive logging
# ===========================================================================


class TestRetroactiveLogging:
    def test_log_session_appears_in_history(self):
        from grouper.database.activities import get_or_create_activity
        from grouper.database.sessions import get_sessions, log_session

        get_or_create_activity("PastWork")

        logged = log_session(
            activity_name="PastWork",
            duration=timedelta(hours=2),
            notes="retroactive entry",
            date=datetime(2026, 3, 20, 14, 0, 0),
        )

        assert logged.id is not None
        assert logged.end_time == datetime(2026, 3, 20, 14, 0, 0)
        assert logged.start_time == datetime(2026, 3, 20, 12, 0, 0)

        # Should appear in get_sessions
        history = get_sessions(activity_name="PastWork")
        assert len(history) == 1
        assert history[0].id == logged.id
        assert history[0].notes == "retroactive entry"

        # Verify duration
        duration = history[0].duration_seconds
        assert duration == 7200  # 2 hours

    def test_log_session_appears_in_summary(self):
        from grouper.database.activities import get_or_create_activity
        from grouper.database.sessions import get_summary, log_session

        get_or_create_activity("SummaryWork")

        log_session(
            activity_name="SummaryWork",
            duration=timedelta(minutes=90),
            date=datetime(2026, 3, 25, 10, 0, 0),
        )

        summary = get_summary(
            start_date=datetime(2026, 3, 25),
            end_date=datetime(2026, 3, 26),
        )

        assert "SummaryWork" in summary
        assert summary["SummaryWork"] == 5400  # 90 minutes

    def test_multiple_retroactive_sessions_sum_correctly(self):
        from grouper.database.activities import get_or_create_activity
        from grouper.database.sessions import get_summary, log_session

        get_or_create_activity("MultiLog")

        log_session(
            activity_name="MultiLog",
            duration=timedelta(hours=1),
            date=datetime(2026, 3, 25, 10, 0, 0),
        )
        log_session(
            activity_name="MultiLog",
            duration=timedelta(hours=2),
            date=datetime(2026, 3, 25, 15, 0, 0),
        )

        summary = get_summary(
            start_date=datetime(2026, 3, 25),
            end_date=datetime(2026, 3, 26),
        )

        assert summary["MultiLog"] == 10800  # 3 hours total


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    def test_pause_already_paused_returns_none(self):
        from grouper.database.sessions import (
            pause_session,
            start_session,
        )

        session = start_session("EdgeCase1")
        pause_session(session.id)

        # Pausing again should return None
        result = pause_session(session.id)
        assert result is None

    def test_resume_not_paused_returns_none(self):
        from grouper.database.sessions import (
            resume_session,
            start_session,
        )

        session = start_session("EdgeCase2")

        # Resuming a session that isn't paused should return None
        result = resume_session(session.id)
        assert result is None

    def test_stop_nonexistent_activity_returns_empty(self):
        from grouper.database.sessions import stop_session

        result = stop_session("NoSuchActivity")
        assert result == []

    def test_get_active_session_by_activity_returns_none_for_unknown(self):
        from grouper.database.sessions import get_active_session_by_activity

        result = get_active_session_by_activity("DoesNotExist")
        assert result is None

    def test_stop_all_with_no_active_sessions(self):
        from grouper.database.sessions import stop_all_sessions

        result = stop_all_sessions()
        assert result == []
