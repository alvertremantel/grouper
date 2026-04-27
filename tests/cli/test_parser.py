"""test_parser.py — Unit tests for CLI argument parsing."""

from __future__ import annotations

import pytest
from cli.main import build_parser


@pytest.fixture
def parser():
    return build_parser()


class TestGlobalFlags:
    def test_json_flag_default_false(self, parser):
        args = parser.parse_args(["session", "active"])
        assert args.json is False

    def test_json_flag_set(self, parser):
        args = parser.parse_args(["--json", "session", "active"])
        assert args.json is True

    def test_no_command_shows_error(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args([])


class TestSessionParser:
    def test_active(self, parser):
        args = parser.parse_args(["session", "active"])
        assert args.command == "session"
        assert args.session_action == "active"

    def test_summary_default_days(self, parser):
        args = parser.parse_args(["session", "summary"])
        assert args.days == 7

    def test_summary_custom_days(self, parser):
        args = parser.parse_args(["session", "summary", "--days", "30"])
        assert args.days == 30

    def test_history_defaults(self, parser):
        args = parser.parse_args(["session", "history"])
        assert args.activity is None
        assert args.limit == 20

    def test_history_with_filters(self, parser):
        args = parser.parse_args(["session", "history", "--activity", "dev", "--limit", "5"])
        assert args.activity == "dev"
        assert args.limit == 5

    def test_start_requires_activity(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["session", "start"])

    def test_start_with_activity(self, parser):
        args = parser.parse_args(["session", "start", "coding"])
        assert args.activity == "coding"

    def test_pause_requires_id(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["session", "pause"])

    def test_pause_with_id(self, parser):
        args = parser.parse_args(["session", "pause", "42"])
        assert args.session_id == 42

    def test_resume_with_id(self, parser):
        args = parser.parse_args(["session", "resume", "7"])
        assert args.session_id == 7

    def test_stop_no_activity(self, parser):
        args = parser.parse_args(["session", "stop"])
        assert args.activity is None

    def test_stop_with_activity(self, parser):
        args = parser.parse_args(["session", "stop", "coding"])
        assert args.activity == "coding"


class TestTaskParser:
    def test_list_defaults(self, parser):
        args = parser.parse_args(["task", "list"])
        assert args.board_id is None
        assert args.include_completed is False

    def test_list_with_flags(self, parser):
        args = parser.parse_args(["task", "list", "--board-id", "3", "--include-completed"])
        assert args.board_id == 3
        assert args.include_completed is True

    def test_upcoming_default_days(self, parser):
        args = parser.parse_args(["task", "upcoming"])
        assert args.days == 7

    def test_create_requires_title_and_project(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["task", "create", "Title"])  # missing --project-id

    def test_create_full(self, parser):
        args = parser.parse_args(
            [
                "task",
                "create",
                "Fix bug",
                "--project-id",
                "1",
                "--priority",
                "1",
                "--due-date",
                "2026-04-01",
                "--tags",
                "bug,urgent",
                "--prerequisites",
                "3,5",
            ]
        )
        assert args.title == "Fix bug"
        assert args.project_id == 1
        assert args.priority == 1
        assert args.due_date == "2026-04-01"
        assert args.tags == "bug,urgent"
        assert args.prerequisites == "3,5"

    def test_complete_requires_id(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["task", "complete"])

    def test_update_optional_fields(self, parser):
        args = parser.parse_args(["task", "update", "5", "--title", "New name"])
        assert args.task_id == 5
        assert args.title == "New name"
        assert args.priority is None
        assert args.due_date is None
        assert args.tags is None
        assert args.prerequisites is None


class TestEventParser:
    def test_list_requires_dates(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["event", "list"])

    def test_list_with_dates(self, parser):
        args = parser.parse_args(["event", "list", "--start", "2026-03-01", "--end", "2026-03-31"])
        assert args.start == "2026-03-01"
        assert args.end == "2026-03-31"

    def test_create_requires_title_and_times(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["event", "create", "Meeting"])

    def test_create_full(self, parser):
        args = parser.parse_args(
            [
                "event",
                "create",
                "Meeting",
                "--start",
                "2026-03-25T09:00:00",
                "--end",
                "2026-03-25T10:00:00",
                "--calendar-id",
                "2",
            ]
        )
        assert args.title == "Meeting"
        assert args.calendar_id == 2

    def test_delete_requires_id(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["event", "delete"])

    def test_update_optional_fields(self, parser):
        args = parser.parse_args(["event", "update", "3", "--title", "Renamed"])
        assert args.event_id == 3
        assert args.title == "Renamed"
        assert args.location is None


class TestActivityParser:
    def test_list_default_includes_background(self, parser):
        args = parser.parse_args(["activity", "list"])
        assert args.include_background is True

    def test_list_no_background(self, parser):
        args = parser.parse_args(["activity", "list", "--no-background"])
        assert args.include_background is False

    def test_time_requires_name(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["activity", "time"])

    def test_time_with_days(self, parser):
        args = parser.parse_args(["activity", "time", "coding", "--days", "14"])
        assert args.name == "coding"
        assert args.days == 14


class TestProjectBoardParser:
    def test_project_list(self, parser):
        args = parser.parse_args(["project", "list"])
        assert args.command == "project"
        assert args.project_action == "list"
        assert args.board_id is None

    def test_project_list_with_board(self, parser):
        args = parser.parse_args(["project", "list", "--board-id", "2"])
        assert args.board_id == 2

    def test_board_list(self, parser):
        args = parser.parse_args(["board", "list"])
        assert args.command == "board"
        assert args.board_action == "list"


class TestDashboardSummaryParser:
    def test_dashboard(self, parser):
        args = parser.parse_args(["dashboard"])
        assert args.command == "dashboard"

    def test_summary_today(self, parser):
        args = parser.parse_args(["summary", "today"])
        assert args.command == "summary"
        assert args.summary_action == "today"

    def test_summary_week(self, parser):
        args = parser.parse_args(["summary", "week"])
        assert args.command == "summary"
        assert args.summary_action == "week"
