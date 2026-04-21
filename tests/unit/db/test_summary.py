"""test_summary.py -- Unit tests for SQL-based summary aggregation.

Tests run against an isolated SQLite database via the root conftest's
``isolated_db`` fixture (autouse).
"""

from __future__ import annotations

from datetime import datetime

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_session(
    activity_name: str,
    start_time: str,
    end_time: str,
    paused_seconds: int = 0,
) -> None:
    """Insert a completed session directly into the DB."""
    from grouper.database.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (activity_name, start_time, end_time, paused_seconds) "
            "VALUES (?, ?, ?, ?)",
            (activity_name, start_time, end_time, paused_seconds),
        )
        conn.commit()


def _insert_session_null_pause(
    activity_name: str,
    start_time: str,
    end_time: str,
) -> None:
    """Insert a session with NULL paused_seconds (like split_sessions_at_midnight)."""
    from grouper.database.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (activity_name, start_time, end_time) VALUES (?, ?, ?)",
            (activity_name, start_time, end_time),
        )
        conn.commit()


# ===========================================================================
# get_summary() tests
# ===========================================================================


class TestGetSummary:
    def test_empty_database(self) -> None:
        from grouper.database.sessions import get_summary

        assert get_summary() == {}

    def test_single_session(self) -> None:
        from grouper.database.sessions import get_summary

        # 1-hour session: 10:00 -> 11:00 = 3600s
        _insert_session("Coding", "2026-01-15T10:00:00", "2026-01-15T11:00:00")
        result = get_summary()
        assert result == {"Coding": 3600}

    def test_multiple_sessions_same_activity(self) -> None:
        from grouper.database.sessions import get_summary

        _insert_session("Coding", "2026-01-15T10:00:00", "2026-01-15T11:00:00")  # 3600
        _insert_session("Coding", "2026-01-15T14:00:00", "2026-01-15T14:30:00")  # 1800
        result = get_summary()
        assert result == {"Coding": 5400}

    def test_multiple_activities(self) -> None:
        from grouper.database.sessions import get_summary

        _insert_session("Coding", "2026-01-15T10:00:00", "2026-01-15T11:00:00")  # 3600
        _insert_session("Reading", "2026-01-15T12:00:00", "2026-01-15T12:45:00")  # 2700
        result = get_summary()
        assert result == {"Coding": 3600, "Reading": 2700}

    def test_paused_seconds_subtracted(self) -> None:
        from grouper.database.sessions import get_summary

        # 1-hour session with 600s paused -> 3000s effective
        _insert_session("Coding", "2026-01-15T10:00:00", "2026-01-15T11:00:00", paused_seconds=600)
        result = get_summary()
        assert result == {"Coding": 3000}

    def test_paused_exceeds_elapsed_clamps_to_zero(self) -> None:
        from grouper.database.sessions import get_summary

        # 10-minute session with 9999s paused -> clamped to 0
        _insert_session("Coding", "2026-01-15T10:00:00", "2026-01-15T10:10:00", paused_seconds=9999)
        result = get_summary()
        assert result == {"Coding": 0}

    def test_null_paused_seconds(self) -> None:
        from grouper.database.sessions import get_summary

        # Session with NULL paused_seconds (from split_sessions_at_midnight)
        _insert_session_null_pause("Coding", "2026-01-15T10:00:00", "2026-01-15T11:00:00")
        result = get_summary()
        assert result == {"Coding": 3600}

    def test_date_range_filtering(self) -> None:
        from grouper.database.sessions import get_summary

        _insert_session("Coding", "2026-01-14T10:00:00", "2026-01-14T11:00:00")  # outside
        _insert_session("Coding", "2026-01-15T10:00:00", "2026-01-15T11:00:00")  # inside
        _insert_session("Coding", "2026-01-16T10:00:00", "2026-01-16T11:00:00")  # outside

        start = datetime(2026, 1, 15)
        end = datetime(2026, 1, 16)
        result = get_summary(start_date=start, end_date=end)
        assert result == {"Coding": 3600}

    def test_no_end_date(self) -> None:
        from grouper.database.sessions import get_summary

        _insert_session("Coding", "2026-01-14T10:00:00", "2026-01-14T11:00:00")  # before
        _insert_session("Coding", "2026-01-15T10:00:00", "2026-01-15T11:00:00")  # after

        start = datetime(2026, 1, 15)
        result = get_summary(start_date=start)
        assert result == {"Coding": 3600}

    def test_no_parameters(self) -> None:
        from grouper.database.sessions import get_summary

        _insert_session("A", "2026-01-01T00:00:00", "2026-01-01T01:00:00")
        _insert_session("B", "2026-06-15T00:00:00", "2026-06-15T02:00:00")
        result = get_summary()
        assert result == {"A": 3600, "B": 7200}


# ===========================================================================
# get_summary_by_day() tests
# ===========================================================================


class TestGetSummaryByDay:
    def test_empty_range(self) -> None:
        from grouper.database.sessions import get_summary_by_day

        start = datetime(2026, 1, 15)
        end = datetime(2026, 1, 16)
        assert get_summary_by_day(start, end) == {}

    def test_single_session_single_day(self) -> None:
        from grouper.database.sessions import get_summary_by_day

        _insert_session("Coding", "2026-01-15T10:00:00", "2026-01-15T11:00:00")
        result = get_summary_by_day(datetime(2026, 1, 15), datetime(2026, 1, 16))
        assert result == {"Coding": {"2026-01-15": 3600}}

    def test_same_activity_multiple_days(self) -> None:
        from grouper.database.sessions import get_summary_by_day

        _insert_session("Coding", "2026-01-15T10:00:00", "2026-01-15T11:00:00")  # 3600
        _insert_session("Coding", "2026-01-16T09:00:00", "2026-01-16T09:30:00")  # 1800
        result = get_summary_by_day(datetime(2026, 1, 15), datetime(2026, 1, 17))
        assert result == {"Coding": {"2026-01-15": 3600, "2026-01-16": 1800}}

    def test_multiple_activities_same_day(self) -> None:
        from grouper.database.sessions import get_summary_by_day

        _insert_session("Coding", "2026-01-15T10:00:00", "2026-01-15T11:00:00")
        _insert_session("Reading", "2026-01-15T12:00:00", "2026-01-15T12:30:00")
        result = get_summary_by_day(datetime(2026, 1, 15), datetime(2026, 1, 16))
        assert result == {
            "Coding": {"2026-01-15": 3600},
            "Reading": {"2026-01-15": 1800},
        }

    def test_paused_seconds_subtracted(self) -> None:
        from grouper.database.sessions import get_summary_by_day

        _insert_session("Coding", "2026-01-15T10:00:00", "2026-01-15T11:00:00", paused_seconds=600)
        result = get_summary_by_day(datetime(2026, 1, 15), datetime(2026, 1, 16))
        assert result == {"Coding": {"2026-01-15": 3000}}

    def test_only_sessions_in_range(self) -> None:
        from grouper.database.sessions import get_summary_by_day

        _insert_session("Coding", "2026-01-14T10:00:00", "2026-01-14T11:00:00")  # outside
        _insert_session("Coding", "2026-01-15T10:00:00", "2026-01-15T11:00:00")  # inside
        _insert_session("Coding", "2026-01-16T10:00:00", "2026-01-16T11:00:00")  # outside

        result = get_summary_by_day(datetime(2026, 1, 15), datetime(2026, 1, 16))
        assert result == {"Coding": {"2026-01-15": 3600}}
