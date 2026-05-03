"""test_e2e.py — End-to-end CLI tests with a real (temp) database.

No GUI. Each test gets a fresh SQLite DB via the `isolated_db` fixture in conftest.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import desktop.database.boards as _boards
import desktop.database.projects as _projects
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path):
    """Create a board + project for task tests (unique per test)."""
    import uuid

    suffix = uuid.uuid4().hex[:8]
    board = _boards.create_board(f"CLI Board {suffix}")
    return _projects.create_project(board_id=board.id, name="CLI Test Project")


# ---------------------------------------------------------------------------
# Session E2E
# ---------------------------------------------------------------------------


class TestSessionE2E:
    def test_active_empty(self, run_cli):
        r = run_cli("session", "active")
        assert r.code == 0
        assert "(no results)" in r.stdout

    def test_start_and_active(self, run_cli):
        r = run_cli("session", "start", "coding")
        assert r.code == 0
        assert "Started session" in r.stdout
        assert "coding" in r.stdout

        r = run_cli("session", "active")
        assert r.code == 0
        assert "coding" in r.stdout

    def test_start_pause_resume_stop(self, run_cli):
        # Start
        r = run_cli("--json", "session", "start", "flow")
        assert r.code == 0
        session = json.loads(r.stdout)
        sid = session["id"]

        # Pause
        r = run_cli("session", "pause", str(sid))
        assert r.code == 0
        assert "Paused" in r.stdout

        # Resume
        r = run_cli("session", "resume", str(sid))
        assert r.code == 0
        assert "Resumed" in r.stdout

        # Stop
        r = run_cli("session", "stop", "flow")
        assert r.code == 0
        assert "Stopped" in r.stdout

    def test_stop_no_active(self, run_cli):
        r = run_cli("session", "stop")
        assert r.code == 0
        assert "No active sessions" in r.stdout

    def test_pause_nonexistent(self, run_cli):
        r = run_cli("session", "pause", "99999")
        assert r.code == 1
        assert "not found" in r.stderr

    def test_resume_nonexistent(self, run_cli):
        r = run_cli("session", "resume", "99999")
        assert r.code == 1
        assert "not found" in r.stderr

    def test_summary(self, run_cli):
        run_cli("session", "start", "dev")
        run_cli("session", "stop")

        r = run_cli("session", "summary", "--days", "1")
        assert r.code == 0
        assert "dev" in r.stdout

    def test_summary_json(self, run_cli):
        run_cli("session", "start", "dev")
        run_cli("session", "stop")

        r = run_cli("--json", "session", "summary", "--days", "1")
        assert r.code == 0
        data = json.loads(r.stdout)
        assert "dev" in data

    def test_history(self, run_cli):
        run_cli("session", "start", "reading")
        run_cli("session", "stop")

        r = run_cli("session", "history", "--limit", "5")
        assert r.code == 0
        assert "reading" in r.stdout

    def test_history_filter_by_activity(self, run_cli):
        run_cli("session", "start", "reading")
        run_cli("session", "stop")
        run_cli("session", "start", "coding")
        run_cli("session", "stop")

        r = run_cli("session", "history", "--activity", "reading")
        assert r.code == 0
        assert "reading" in r.stdout
        assert "coding" not in r.stdout

    def test_history_json(self, run_cli):
        run_cli("session", "start", "writing")
        run_cli("session", "stop")

        r = run_cli("--json", "session", "history")
        assert r.code == 0
        data = json.loads(r.stdout)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["activity"] == "writing"


# ---------------------------------------------------------------------------
# Task E2E
# ---------------------------------------------------------------------------


class TestTaskE2E:
    def test_list_empty(self, run_cli, project):
        r = run_cli("task", "list")
        assert r.code == 0

    def test_create_and_list(self, run_cli, project):
        r = run_cli("task", "create", "Write tests", "--project-id", str(project.id))
        assert r.code == 0
        assert "Created task" in r.stdout

        r = run_cli("task", "list")
        assert r.code == 0
        assert "Write tests" in r.stdout

    def test_create_with_options(self, run_cli, project):
        r = run_cli(
            "--json",
            "task",
            "create",
            "Urgent fix",
            "--project-id",
            str(project.id),
            "--priority",
            "1",
            "--due-date",
            "2026-04-01",
            "--tags",
            "bug,critical",
        )
        assert r.code == 0
        data = json.loads(r.stdout)
        assert data["title"] == "Urgent fix"
        assert data["priority"] == 1
        assert "2026-04-01" in data["due_date"]
        assert "bug" in data["tags"]
        assert "critical" in data["tags"]

    def test_complete_task(self, run_cli, project):
        run_cli("task", "create", "Task A", "--project-id", str(project.id))
        r = run_cli("task", "complete", "1")
        assert r.code == 0
        assert "Completed" in r.stdout

    def test_complete_json(self, run_cli, project):
        run_cli("task", "create", "Task B", "--project-id", str(project.id))
        r = run_cli("--json", "task", "complete", "1")
        assert r.code == 0
        data = json.loads(r.stdout)
        assert data["status"] == "completed"

    def test_completed_hidden_by_default(self, run_cli, project):
        run_cli("task", "create", "Task C", "--project-id", str(project.id))
        run_cli("task", "complete", "1")

        r = run_cli("--json", "task", "list")
        data = json.loads(r.stdout)
        assert len(data) == 0

        r = run_cli("--json", "task", "list", "--include-completed")
        data = json.loads(r.stdout)
        assert len(data) == 1

    def test_update_task(self, run_cli, project):
        run_cli("task", "create", "Old name", "--project-id", str(project.id))
        r = run_cli("task", "update", "1", "--title", "New name", "--priority", "1")
        assert r.code == 0
        assert "Updated" in r.stdout

        r = run_cli("--json", "task", "list")
        data = json.loads(r.stdout)
        assert data[0]["title"] == "New name"
        assert data[0]["priority"] == 1

    def test_update_tags(self, run_cli, project):
        run_cli("task", "create", "Tagged", "--project-id", str(project.id), "--tags", "alpha,beta")
        run_cli("task", "update", "1", "--tags", "gamma")

        r = run_cli("--json", "task", "list")
        data = json.loads(r.stdout)
        assert data[0]["tags"] == ["gamma"]

    def test_upcoming(self, run_cli, project):
        from datetime import date, timedelta

        soon_date = (date.today() + timedelta(days=3)).isoformat()
        later_date = (date.today() + timedelta(days=60)).isoformat()
        # Task with near due date
        run_cli("task", "create", "Soon", "--project-id", str(project.id), "--due-date", soon_date)
        # Task with far due date
        run_cli(
            "task", "create", "Later", "--project-id", str(project.id), "--due-date", later_date
        )

        r = run_cli("--json", "task", "upcoming", "--days", "7")
        data = json.loads(r.stdout)
        titles = [t["title"] for t in data]
        assert "Soon" in titles
        assert "Later" not in titles

    def test_prerequisite_blocks_completion(self, run_cli, project):
        run_cli("task", "create", "Prereq", "--project-id", str(project.id))
        run_cli(
            "task", "create", "Dependent", "--project-id", str(project.id), "--prerequisites", "1"
        )

        r = run_cli("task", "complete", "2")
        assert r.code == 1
        assert "blocked" in r.stderr.lower() or "blocked" in r.stdout.lower()


# ---------------------------------------------------------------------------
# Activity E2E
# ---------------------------------------------------------------------------


class TestActivityE2E:
    def test_list_empty(self, run_cli):
        r = run_cli("activity", "list")
        assert r.code == 0

    def test_list_after_session(self, run_cli):
        run_cli("session", "start", "design")
        run_cli("session", "stop")

        r = run_cli("activity", "list")
        assert r.code == 0
        assert "design" in r.stdout

    def test_time_no_sessions(self, run_cli):
        r = run_cli("activity", "time", "phantom")
        assert r.code == 0
        assert "0h 00m 00s" in r.stdout

    def test_time_json(self, run_cli):
        run_cli("session", "start", "dev")
        run_cli("session", "stop")

        r = run_cli("--json", "activity", "time", "dev", "--days", "1")
        assert r.code == 0
        data = json.loads(r.stdout)
        assert data["activity_name"] == "dev"
        assert data["days"] == 1
        assert isinstance(data["total_seconds"], int)


# ---------------------------------------------------------------------------
# Event E2E
# ---------------------------------------------------------------------------


class TestEventE2E:
    def test_create_and_list(self, run_cli):
        r = run_cli(
            "event",
            "create",
            "Standup",
            "--start",
            "2026-03-25T09:00:00",
            "--end",
            "2026-03-25T09:30:00",
        )
        assert r.code == 0
        assert "Created event" in r.stdout

        r = run_cli("event", "list", "--start", "2026-03-25", "--end", "2026-03-26")
        assert r.code == 0
        assert "Standup" in r.stdout

    def test_create_json(self, run_cli):
        r = run_cli(
            "--json",
            "event",
            "create",
            "Lunch",
            "--start",
            "2026-03-25T12:00:00",
            "--end",
            "2026-03-25T13:00:00",
        )
        assert r.code == 0
        data = json.loads(r.stdout)
        assert data["title"] == "Lunch"

    def test_update(self, run_cli):
        r = run_cli(
            "--json",
            "event",
            "create",
            "Meeting",
            "--start",
            "2026-03-25T14:00:00",
            "--end",
            "2026-03-25T15:00:00",
        )
        eid = json.loads(r.stdout)["id"]

        r = run_cli(
            "event", "update", str(eid), "--title", "Important Meeting", "--location", "Room A"
        )
        assert r.code == 0
        assert "Updated event" in r.stdout

    def test_delete(self, run_cli):
        r = run_cli(
            "--json",
            "event",
            "create",
            "Temp",
            "--start",
            "2026-03-25T16:00:00",
            "--end",
            "2026-03-25T17:00:00",
        )
        eid = json.loads(r.stdout)["id"]

        r = run_cli("event", "delete", str(eid))
        assert r.code == 0
        assert "Deleted" in r.stdout

        # Verify gone
        r = run_cli("--json", "event", "list", "--start", "2026-03-25", "--end", "2026-03-26")
        data = json.loads(r.stdout)
        assert len(data) == 0

    def test_delete_nonexistent(self, run_cli):
        r = run_cli("event", "delete", "99999")
        assert r.code == 1
        assert "not found" in r.stderr

    def test_update_nonexistent(self, run_cli):
        r = run_cli("event", "update", "99999", "--title", "X")
        assert r.code == 1
        assert "not found" in r.stderr


# ---------------------------------------------------------------------------
# Project / Board E2E
# ---------------------------------------------------------------------------


class TestProjectBoardE2E:
    def test_board_list_empty(self, run_cli):
        r = run_cli("board", "list")
        assert r.code == 0

    def test_board_list_after_create(self, run_cli):
        _boards.create_board("My Board")
        r = run_cli("board", "list")
        assert r.code == 0
        assert "My Board" in r.stdout

    def test_board_list_json(self, run_cli):
        _boards.create_board("JSON Board")
        r = run_cli("--json", "board", "list")
        assert r.code == 0
        data = json.loads(r.stdout)
        assert any(b["name"] == "JSON Board" for b in data)

    def test_project_list(self, run_cli, project):
        r = run_cli("project", "list")
        assert r.code == 0
        assert "CLI Test Project" in r.stdout

    def test_project_list_json(self, run_cli, project):
        r = run_cli("--json", "project", "list")
        assert r.code == 0
        data = json.loads(r.stdout)
        assert any(p["name"] == "CLI Test Project" for p in data)

    def test_project_filter_by_board(self, run_cli):
        b1 = _boards.create_board("Board A")
        b2 = _boards.create_board("Board B")
        _projects.create_project(board_id=b1.id, name="P on A")
        _projects.create_project(board_id=b2.id, name="P on B")

        r = run_cli("--json", "project", "list", "--board-id", str(b1.id))
        data = json.loads(r.stdout)
        names = [p["name"] for p in data]
        assert "P on A" in names
        assert "P on B" not in names


# ---------------------------------------------------------------------------
# Dashboard / Summary E2E
# ---------------------------------------------------------------------------


class TestDashboardE2E:
    def test_dashboard_empty(self, run_cli):
        r = run_cli("dashboard")
        assert r.code == 0
        assert "Active Sessions" in r.stdout
        assert "Upcoming Tasks" in r.stdout

    def test_dashboard_json(self, run_cli):
        r = run_cli("--json", "dashboard")
        assert r.code == 0
        data = json.loads(r.stdout)
        assert "active_sessions" in data
        assert "upcoming_tasks" in data
        assert "generated_at" in data

    def test_dashboard_with_session(self, run_cli):
        run_cli("session", "start", "working")
        r = run_cli("dashboard")
        assert r.code == 0
        assert "working" in r.stdout
        run_cli("session", "stop")

    def test_summary_today(self, run_cli):
        r = run_cli("summary", "today")
        assert r.code == 0
        assert "Today" in r.stdout

    def test_summary_today_json(self, run_cli):
        run_cli("session", "start", "dev")
        run_cli("session", "stop")

        r = run_cli("--json", "summary", "today")
        assert r.code == 0
        data = json.loads(r.stdout)
        assert "date" in data
        assert "activities" in data
        assert "total_seconds" in data

    def test_summary_week(self, run_cli):
        r = run_cli("summary", "week")
        assert r.code == 0
        assert "This Week" in r.stdout

    def test_summary_week_json(self, run_cli):
        r = run_cli("--json", "summary", "week")
        assert r.code == 0
        data = json.loads(r.stdout)
        assert "week_start" in data
        assert "activities" in data


# ---------------------------------------------------------------------------
# Error handling E2E
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_bad_iso_date_in_event_create(self, run_cli):
        r = run_cli(
            "event", "create", "Bad", "--start", "not-a-date", "--end", "2026-03-25T10:00:00"
        )
        assert r.code == 1
        assert "invalid value" in r.stderr.lower()

    def test_bad_iso_date_in_event_list(self, run_cli):
        r = run_cli("event", "list", "--start", "nope", "--end", "2026-03-26")
        assert r.code == 1
        assert "invalid value" in r.stderr.lower()

    def test_bad_iso_date_in_task_create(self, run_cli, project):
        r = run_cli(
            "task", "create", "Bad date", "--project-id", str(project.id), "--due-date", "yesterday"
        )
        assert r.code == 1
        assert "invalid value" in r.stderr.lower()

    def test_bad_iso_date_in_task_update(self, run_cli, project):
        run_cli("task", "create", "Fixable", "--project-id", str(project.id))
        r = run_cli("task", "update", "1", "--due-date", "not-valid")
        assert r.code == 1
        assert "invalid value" in r.stderr.lower()

    def test_graceful_on_nonexistent_project(self, run_cli):
        """Creating a task in a missing project should error, not crash."""
        r = run_cli("task", "create", "Orphan", "--project-id", "99999")
        assert r.code == 1
        assert "error" in r.stderr.lower()

    def test_session_start_json_roundtrip(self, run_cli):
        """JSON output from start should be valid and parseable."""
        r = run_cli("--json", "session", "start", "roundtrip")
        assert r.code == 0
        data = json.loads(r.stdout)
        assert "id" in data
        assert data["activity"] == "roundtrip"
        assert "start" in data

    def test_session_active_json_has_duration(self, run_cli):
        run_cli("session", "start", "check-dur")
        r = run_cli("--json", "session", "active")
        assert r.code == 0
        data = json.loads(r.stdout)
        assert len(data) >= 1
        assert "duration_seconds" in data[0]
        assert "duration_formatted" in data[0]

    def test_empty_tag_list_clears_tags(self, run_cli, project):
        """Passing --tags '' should clear all tags."""
        run_cli("task", "create", "Tagged", "--project-id", str(project.id), "--tags", "alpha,beta")
        # Clear tags by passing empty
        run_cli("task", "update", "1", "--tags", "")
        r = run_cli("--json", "task", "list")
        data = json.loads(r.stdout)
        assert data[0]["tags"] == []
