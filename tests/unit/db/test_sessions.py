"""test_sessions.py -- Unit tests for session operations.

Tests cover:
  - split_sessions_at_midnight()
  - export_sessions_csv()
  - get_summary() / get_summary_by_day() (supplementary to test_summary.py)

Tests run against an isolated SQLite database via the root conftest's
``isolated_db`` fixture (autouse).
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_session(
    activity_name: str,
    start_time: str,
    end_time: str,
    notes: str = "",
    task_id: int | None = None,
    paused_seconds: int = 0,
) -> int:
    """Insert a completed session directly into the DB, return the row id."""
    from grouper.database.connection import get_connection

    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO sessions "
            "(activity_name, start_time, end_time, notes, task_id, paused_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (activity_name, start_time, end_time, notes, task_id, paused_seconds),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]


def _get_all_sessions() -> list[dict]:
    """Return every session row as a dict."""
    from grouper.database.connection import get_connection

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE end_time IS NOT NULL ORDER BY start_time"
        ).fetchall()
    return [dict(r) for r in rows]


def _ensure_activity(name: str) -> None:
    """Create an activity if it doesn't already exist."""
    from grouper.database.activities import get_or_create_activity

    get_or_create_activity(name)


# ===========================================================================
# split_sessions_at_midnight()
# ===========================================================================


class TestSplitSessionsAtMidnight:
    def test_same_day_session_not_split(self) -> None:
        _ensure_activity("Coding")
        _insert_session("Coding", "2026-03-15T10:00:00", "2026-03-15T18:00:00")

        from grouper.database.sessions import split_sessions_at_midnight

        created = split_sessions_at_midnight()
        assert created == 0

        sessions = _get_all_sessions()
        assert len(sessions) == 1

    def test_span_one_midnight_produces_two_segments(self) -> None:
        _ensure_activity("Coding")
        _insert_session("Coding", "2026-03-15T23:00:00", "2026-03-16T01:00:00")

        from grouper.database.sessions import split_sessions_at_midnight

        created = split_sessions_at_midnight()
        assert created == 1  # one new segment inserted

        sessions = _get_all_sessions()
        assert len(sessions) == 2

        # First segment: original day, ends at 23:59:59
        s0 = sessions[0]
        assert s0["start_time"] == "2026-03-15T23:00:00"
        assert s0["end_time"] == "2026-03-15T23:59:59"

        # Second segment: next day, starts at 00:00:00
        s1 = sessions[1]
        assert s1["start_time"] == "2026-03-16T00:00:00"
        assert s1["end_time"] == "2026-03-16T01:00:00"

    def test_span_two_midnights_produces_three_segments(self) -> None:
        _ensure_activity("Coding")
        # Monday 23:00 -> Wednesday 01:00 spans two midnights
        _insert_session("Coding", "2026-03-16T23:00:00", "2026-03-18T01:00:00")

        from grouper.database.sessions import split_sessions_at_midnight

        created = split_sessions_at_midnight()
        assert created == 2  # two new segments

        sessions = _get_all_sessions()
        assert len(sessions) == 3

        # Day 1: original truncated
        assert sessions[0]["start_time"] == "2026-03-16T23:00:00"
        assert sessions[0]["end_time"] == "2026-03-16T23:59:59"

        # Day 2: full day segment
        assert sessions[1]["start_time"] == "2026-03-17T00:00:00"
        assert sessions[1]["end_time"] == "2026-03-17T23:59:59"

        # Day 3: partial
        assert sessions[2]["start_time"] == "2026-03-18T00:00:00"
        assert sessions[2]["end_time"] == "2026-03-18T01:00:00"

    def test_segments_within_same_calendar_day(self) -> None:
        _ensure_activity("Reading")
        _insert_session("Reading", "2026-03-20T22:00:00", "2026-03-21T06:00:00")

        from grouper.database.sessions import split_sessions_at_midnight

        split_sessions_at_midnight()

        sessions = _get_all_sessions()
        for s in sessions:
            start = datetime.fromisoformat(s["start_time"])
            end = datetime.fromisoformat(s["end_time"])
            assert start.date() == end.date(), f"Segment crosses day boundary: {start} -> {end}"

    def test_notes_preserved_on_all_segments(self) -> None:
        _ensure_activity("Coding")
        _insert_session(
            "Coding",
            "2026-03-15T23:00:00",
            "2026-03-16T01:00:00",
            notes="important note",
        )

        from grouper.database.sessions import split_sessions_at_midnight

        split_sessions_at_midnight()

        sessions = _get_all_sessions()
        assert len(sessions) == 2
        # Notes are on original (updated in place) and copied to new segments
        for s in sessions:
            assert s["notes"] == "important note"

    def test_task_id_preserved_on_all_segments(self) -> None:
        _ensure_activity("Coding")

        # Create a real task so FK constraint is satisfied
        import grouper.database.boards as _boards
        import grouper.database.projects as _projects
        import grouper.database.tasks as _tasks

        board = _boards.get_or_create_default_board()
        proj = _projects.create_project("TestProj", board_id=board.id)
        task = _tasks.create_task(proj.id, "test task")  # type: ignore[arg-type]
        task_id = task.id

        _insert_session(
            "Coding",
            "2026-03-15T23:00:00",
            "2026-03-16T01:00:00",
            task_id=task_id,
        )

        from grouper.database.sessions import split_sessions_at_midnight

        split_sessions_at_midnight()

        sessions = _get_all_sessions()
        assert len(sessions) == 2
        for s in sessions:
            assert s["task_id"] == task_id

    def test_original_session_updated_not_deleted(self) -> None:
        _ensure_activity("Coding")
        original_id = _insert_session("Coding", "2026-03-15T23:00:00", "2026-03-16T01:00:00")

        from grouper.database.sessions import split_sessions_at_midnight

        split_sessions_at_midnight()

        sessions = _get_all_sessions()
        # The original session should still exist (updated end_time)
        original = [s for s in sessions if s["id"] == original_id]
        assert len(original) == 1
        assert original[0]["end_time"] == "2026-03-15T23:59:59"

    def test_activity_name_preserved(self) -> None:
        _ensure_activity("Reading")
        _insert_session("Reading", "2026-03-15T23:30:00", "2026-03-16T00:30:00")

        from grouper.database.sessions import split_sessions_at_midnight

        split_sessions_at_midnight()

        sessions = _get_all_sessions()
        for s in sessions:
            assert s["activity_name"] == "Reading"

    def test_idempotent_no_double_split(self) -> None:
        _ensure_activity("Coding")
        _insert_session("Coding", "2026-03-15T23:00:00", "2026-03-16T01:00:00")

        from grouper.database.sessions import split_sessions_at_midnight

        first = split_sessions_at_midnight()
        assert first == 1

        # Running again should find no more sessions to split
        second = split_sessions_at_midnight()
        assert second == 0

        sessions = _get_all_sessions()
        assert len(sessions) == 2

    def test_paused_seconds_stays_on_original(self) -> None:
        _ensure_activity("Coding")
        _insert_session(
            "Coding",
            "2026-03-15T23:00:00",
            "2026-03-16T01:00:00",
            paused_seconds=300,
        )

        from grouper.database.sessions import split_sessions_at_midnight

        split_sessions_at_midnight()

        sessions = _get_all_sessions()
        # The original (first segment) keeps its paused_seconds;
        # new segments get whatever the INSERT defaults to (0 or NULL).
        original = sessions[0]
        assert original["paused_seconds"] == 300


# ===========================================================================
# export_sessions_csv()
# ===========================================================================


class TestExportSessionsCsv:
    def test_export_with_sessions(self, tmp_path: Path) -> None:
        _ensure_activity("Coding")
        _ensure_activity("Reading")
        _insert_session("Coding", "2026-03-15T10:00:00", "2026-03-15T11:00:00", notes="work")
        _insert_session("Reading", "2026-03-15T14:00:00", "2026-03-15T15:00:00")

        filepath = str(tmp_path / "sessions.csv")

        from grouper.database.sessions import export_sessions_csv

        export_sessions_csv(filepath)

        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Header + 2 data rows
        assert len(rows) == 3
        assert rows[0] == ["id", "activity", "start", "end", "duration_s", "notes"]

    def test_export_empty_database(self, tmp_path: Path) -> None:
        filepath = str(tmp_path / "empty.csv")

        from grouper.database.sessions import export_sessions_csv

        export_sessions_csv(filepath)

        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Header only
        assert len(rows) == 1
        assert rows[0] == ["id", "activity", "start", "end", "duration_s", "notes"]

    def test_csv_correct_row_count(self, tmp_path: Path) -> None:
        _ensure_activity("Coding")
        for i in range(5):
            hour = 10 + i
            _insert_session(
                "Coding",
                f"2026-03-15T{hour:02d}:00:00",
                f"2026-03-15T{hour:02d}:30:00",
            )

        filepath = str(tmp_path / "five.csv")

        from grouper.database.sessions import export_sessions_csv

        export_sessions_csv(filepath)

        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        assert len(rows) == 6  # 1 header + 5 data

    def test_csv_headers_match_expected(self, tmp_path: Path) -> None:
        filepath = str(tmp_path / "headers.csv")

        from grouper.database.sessions import export_sessions_csv

        export_sessions_csv(filepath)

        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)

        assert header == ["id", "activity", "start", "end", "duration_s", "notes"]

    def test_csv_contains_notes(self, tmp_path: Path) -> None:
        _ensure_activity("Coding")
        _insert_session(
            "Coding",
            "2026-03-15T10:00:00",
            "2026-03-15T11:00:00",
            notes="fixed the bug",
        )

        filepath = str(tmp_path / "notes.csv")

        from grouper.database.sessions import export_sessions_csv

        export_sessions_csv(filepath)

        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        data_row = rows[1]
        # notes is the last column
        assert data_row[-1] == "fixed the bug"

    def test_csv_contains_correct_activity_name(self, tmp_path: Path) -> None:
        _ensure_activity("Reading")
        _insert_session("Reading", "2026-03-15T09:00:00", "2026-03-15T10:00:00")

        filepath = str(tmp_path / "activity.csv")

        from grouper.database.sessions import export_sessions_csv

        export_sessions_csv(filepath)

        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # activity is column index 1
        assert rows[1][1] == "Reading"


# ===========================================================================
# get_summary() -- supplementary tests
# ===========================================================================


class TestGetSummarySupplementary:
    def test_returns_total_seconds_per_activity(self) -> None:
        _ensure_activity("Coding")
        _ensure_activity("Reading")
        _insert_session("Coding", "2026-03-15T10:00:00", "2026-03-15T11:00:00")  # 3600
        _insert_session("Reading", "2026-03-15T12:00:00", "2026-03-15T12:30:00")  # 1800

        from grouper.database.sessions import get_summary

        result = get_summary()
        assert result["Coding"] == 3600
        assert result["Reading"] == 1800

    def test_date_range_filters_correctly(self) -> None:
        _ensure_activity("Coding")
        _insert_session("Coding", "2026-03-14T10:00:00", "2026-03-14T11:00:00")  # before
        _insert_session("Coding", "2026-03-15T10:00:00", "2026-03-15T11:00:00")  # in range
        _insert_session("Coding", "2026-03-16T10:00:00", "2026-03-16T11:00:00")  # after

        from grouper.database.sessions import get_summary

        result = get_summary(
            start_date=datetime(2026, 3, 15),
            end_date=datetime(2026, 3, 16),
        )
        assert result == {"Coding": 3600}

    def test_empty_database_returns_empty_dict(self) -> None:
        from grouper.database.sessions import get_summary

        assert get_summary() == {}

    def test_start_date_only(self) -> None:
        _ensure_activity("Coding")
        _insert_session("Coding", "2026-03-14T10:00:00", "2026-03-14T11:00:00")
        _insert_session("Coding", "2026-03-15T10:00:00", "2026-03-15T11:00:00")

        from grouper.database.sessions import get_summary

        result = get_summary(start_date=datetime(2026, 3, 15))
        assert result == {"Coding": 3600}


# ===========================================================================
# get_summary_by_day() -- supplementary tests
# ===========================================================================


class TestGetSummaryByDaySupplementary:
    def test_returns_per_day_breakdown(self) -> None:
        _ensure_activity("Coding")
        _insert_session("Coding", "2026-03-15T10:00:00", "2026-03-15T11:00:00")
        _insert_session("Coding", "2026-03-16T09:00:00", "2026-03-16T09:30:00")

        from grouper.database.sessions import get_summary_by_day

        result = get_summary_by_day(datetime(2026, 3, 15), datetime(2026, 3, 17))
        assert result == {
            "Coding": {
                "2026-03-15": 3600,
                "2026-03-16": 1800,
            }
        }

    def test_empty_range_returns_empty(self) -> None:
        from grouper.database.sessions import get_summary_by_day

        result = get_summary_by_day(datetime(2026, 3, 15), datetime(2026, 3, 16))
        assert result == {}

    def test_multiple_activities_per_day(self) -> None:
        _ensure_activity("Coding")
        _ensure_activity("Reading")
        _insert_session("Coding", "2026-03-15T10:00:00", "2026-03-15T11:00:00")
        _insert_session("Reading", "2026-03-15T14:00:00", "2026-03-15T15:00:00")

        from grouper.database.sessions import get_summary_by_day

        result = get_summary_by_day(datetime(2026, 3, 15), datetime(2026, 3, 16))
        assert "Coding" in result
        assert "Reading" in result
        assert result["Coding"]["2026-03-15"] == 3600
        assert result["Reading"]["2026-03-15"] == 3600

    def test_sessions_outside_range_excluded(self) -> None:
        _ensure_activity("Coding")
        _insert_session("Coding", "2026-03-14T10:00:00", "2026-03-14T11:00:00")
        _insert_session("Coding", "2026-03-15T10:00:00", "2026-03-15T11:00:00")
        _insert_session("Coding", "2026-03-17T10:00:00", "2026-03-17T11:00:00")

        from grouper.database.sessions import get_summary_by_day

        result = get_summary_by_day(datetime(2026, 3, 15), datetime(2026, 3, 16))
        assert result == {"Coding": {"2026-03-15": 3600}}
