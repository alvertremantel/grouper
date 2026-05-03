"""test_optimizations.py — Tests for optimization-related code.

Covers batch loaders, DRY tag helpers, prerequisite cycle detection,
formatting utilities, and model type safety improvements.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers — create boards/projects/tasks/activities for test setup
# ---------------------------------------------------------------------------


def _make_board(name: str = "Test Board") -> int:
    from desktop.database import create_board

    return create_board(name).id


def _make_project(board_id: int, name: str = "Test Project") -> int:
    from desktop.database import create_project

    return create_project(name, board_id).id


def _make_task(project_id: int, title: str, **kwargs) -> int:
    from desktop.database import create_task

    return create_task(project_id, title, **kwargs).id


def _make_activity(name: str, **kwargs) -> int:
    from desktop.database.activities import create_activity

    return create_activity(name, **kwargs).id


# ===========================================================================
# 1. tags.py — batch loaders and DRY helpers
# ===========================================================================


class TestGetTagsForActivityIds:
    def test_empty_list_returns_empty_dict(self):
        from desktop.database.tags import get_tags_for_activity_ids

        assert get_tags_for_activity_ids([]) == {}

    def test_single_activity_no_tags(self):
        from desktop.database.tags import get_tags_for_activity_ids

        aid = _make_activity("Solo")
        result = get_tags_for_activity_ids([aid])
        assert result == {aid: []}

    def test_single_activity_with_tags(self):
        from desktop.database.tags import (
            add_tag_to_activity,
            get_tags_for_activity_ids,
        )

        aid = _make_activity("Tagged")
        add_tag_to_activity(aid, "alpha")
        add_tag_to_activity(aid, "beta")
        result = get_tags_for_activity_ids([aid])
        assert sorted(result[aid]) == ["alpha", "beta"]

    def test_multiple_activities_batch(self):
        from desktop.database.tags import (
            add_tag_to_activity,
            get_tags_for_activity_ids,
        )

        a1 = _make_activity("A1")
        a2 = _make_activity("A2")
        a3 = _make_activity("A3")
        add_tag_to_activity(a1, "x")
        add_tag_to_activity(a2, "y")
        # a3 gets no tags
        result = get_tags_for_activity_ids([a1, a2, a3])
        assert result[a1] == ["x"]
        assert result[a2] == ["y"]
        assert result[a3] == []


class TestGetTagsForTaskIds:
    def test_empty_list_returns_empty_dict(self):
        from desktop.database.tags import get_tags_for_task_ids

        assert get_tags_for_task_ids([]) == {}

    def test_batch_load_task_tags(self):
        from desktop.database.tags import add_tag_to_task, get_tags_for_task_ids

        bid = _make_board()
        pid = _make_project(bid)
        t1 = _make_task(pid, "Task A")
        t2 = _make_task(pid, "Task B")
        add_tag_to_task(t1, "urgent")
        add_tag_to_task(t2, "later")
        add_tag_to_task(t2, "urgent")
        result = get_tags_for_task_ids([t1, t2])
        assert result[t1] == ["urgent"]
        assert sorted(result[t2]) == ["later", "urgent"]


class TestEntityTagHelpers:
    def test_add_and_get_activity_tags(self):
        from desktop.database.tags import add_tag_to_activity, get_activity_tags

        aid = _make_activity("Act1")
        assert add_tag_to_activity(aid, "foo") is True
        assert get_activity_tags(aid) == ["foo"]

    def test_add_duplicate_tag_returns_false(self):
        from desktop.database.tags import add_tag_to_activity

        aid = _make_activity("Act2")
        assert add_tag_to_activity(aid, "dup") is True
        assert add_tag_to_activity(aid, "dup") is False

    def test_remove_activity_tag(self):
        from desktop.database.tags import (
            add_tag_to_activity,
            get_activity_tags,
            remove_tag_from_activity,
        )

        aid = _make_activity("Act3")
        add_tag_to_activity(aid, "gone")
        assert remove_tag_from_activity(aid, "gone") is True
        assert get_activity_tags(aid) == []

    def test_remove_nonexistent_tag_returns_false(self):
        from desktop.database.tags import remove_tag_from_activity

        aid = _make_activity("Act4")
        assert remove_tag_from_activity(aid, "nope") is False

    def test_add_and_get_task_tags(self):
        from desktop.database.tags import add_tag_to_task, get_task_tags

        bid = _make_board()
        pid = _make_project(bid)
        tid = _make_task(pid, "T1")
        add_tag_to_task(tid, "work")
        assert get_task_tags(tid) == ["work"]

    def test_remove_task_tag(self):
        from desktop.database.tags import (
            add_tag_to_task,
            get_task_tags,
            remove_tag_from_task,
        )

        bid = _make_board()
        pid = _make_project(bid)
        tid = _make_task(pid, "T2")
        add_tag_to_task(tid, "temp")
        assert remove_tag_from_task(tid, "temp") is True
        assert get_task_tags(tid) == []

    def test_add_and_get_project_tags(self):
        from desktop.database.tags import add_tag_to_project, get_project_tags

        bid = _make_board("B-proj")
        pid = _make_project(bid, "P-tags")
        add_tag_to_project(pid, "proj-tag")
        assert get_project_tags(pid) == ["proj-tag"]


# ===========================================================================
# 2. activities.py — batch relation loading
# ===========================================================================


class TestGetGroupsForActivityIds:
    def test_empty_list(self):
        from desktop.database.activities import get_groups_for_activity_ids

        assert get_groups_for_activity_ids([]) == {}

    def test_single_activity_no_groups(self):
        from desktop.database.activities import get_groups_for_activity_ids

        aid = _make_activity("NoGroup")
        result = get_groups_for_activity_ids([aid])
        assert result == {aid: []}

    def test_single_activity_with_groups(self):
        from desktop.database.activities import (
            add_activity_group,
            get_groups_for_activity_ids,
        )

        aid = _make_activity("Grouped")
        add_activity_group(aid, "Dev")
        add_activity_group(aid, "Work")
        result = get_groups_for_activity_ids([aid])
        assert sorted(result[aid]) == ["Dev", "Work"]

    def test_multiple_activities_batch(self):
        from desktop.database.activities import (
            add_activity_group,
            get_groups_for_activity_ids,
        )

        a1 = _make_activity("G1")
        a2 = _make_activity("G2")
        add_activity_group(a1, "Alpha")
        # a2 gets no groups
        result = get_groups_for_activity_ids([a1, a2])
        assert result[a1] == ["Alpha"]
        assert result[a2] == []


class TestListActivitiesBatchRelations:
    def test_list_activities_has_groups_and_tags(self):
        from desktop.database.activities import (
            add_activity_group,
            list_activities,
        )
        from desktop.database.tags import add_tag_to_activity

        aid = _make_activity("WithRelations")
        add_activity_group(aid, "MyGroup")
        add_tag_to_activity(aid, "mytag")

        activities = list_activities()
        match = [a for a in activities if a.name == "WithRelations"]
        assert len(match) == 1
        a = match[0]
        assert "MyGroup" in a.groups
        assert "mytag" in a.tags


# ===========================================================================
# 3. prerequisites.py — recursive CTE cycle detection
# ===========================================================================


class TestPrerequisiteCycleDetection:
    def _setup_tasks(self):
        bid = _make_board("Prereq Board")
        pid = _make_project(bid, "Prereq Project")
        return pid

    def test_valid_prerequisite_succeeds(self):
        from desktop.database.prerequisites import add_prerequisite, get_prerequisite_ids

        pid = self._setup_tasks()
        t1 = _make_task(pid, "Task 1")
        t2 = _make_task(pid, "Task 2")
        add_prerequisite(t1, t2)  # t2 must be done before t1
        assert t2 in get_prerequisite_ids(t1)

    def test_self_reference_rejected(self):
        from desktop.database.prerequisites import add_prerequisite, get_prerequisite_ids

        pid = self._setup_tasks()
        t1 = _make_task(pid, "Self Ref")
        add_prerequisite(t1, t1)
        assert get_prerequisite_ids(t1) == []

    def test_direct_cycle_ab_ba_rejected(self):
        from desktop.database.prerequisites import add_prerequisite, get_prerequisite_ids

        pid = self._setup_tasks()
        ta = _make_task(pid, "A")
        tb = _make_task(pid, "B")
        add_prerequisite(ta, tb)  # B before A
        add_prerequisite(tb, ta)  # A before B  -- cycle!
        # ta->tb exists, but tb->ta must NOT exist
        assert tb in get_prerequisite_ids(ta)
        assert ta not in get_prerequisite_ids(tb)

    def test_transitive_cycle_abc_rejected(self):
        from desktop.database.prerequisites import add_prerequisite, get_prerequisite_ids

        pid = self._setup_tasks()
        ta = _make_task(pid, "X")
        tb = _make_task(pid, "Y")
        tc = _make_task(pid, "Z")
        add_prerequisite(ta, tb)  # B before A
        add_prerequisite(tb, tc)  # C before B
        add_prerequisite(tc, ta)  # A before C  -- cycle A->B->C->A
        # tc->ta must NOT be added
        assert ta not in get_prerequisite_ids(tc)
        # But the valid chain still exists
        assert tb in get_prerequisite_ids(ta)
        assert tc in get_prerequisite_ids(tb)


class TestGetPrerequisiteTasks:
    def test_returns_tasks_with_tags(self):
        from desktop.database.prerequisites import add_prerequisite, get_prerequisite_tasks
        from desktop.database.tags import add_tag_to_task

        bid = _make_board("PT Board")
        pid = _make_project(bid, "PT Project")
        t1 = _make_task(pid, "Main Task")
        t2 = _make_task(pid, "Prereq Task")
        add_tag_to_task(t2, "blocker")
        add_prerequisite(t1, t2)

        prereqs = get_prerequisite_tasks(t1)
        assert len(prereqs) == 1
        assert prereqs[0].title == "Prereq Task"
        assert "blocker" in prereqs[0].tags

    def test_returns_empty_when_no_prereqs(self):
        from desktop.database.prerequisites import get_prerequisite_tasks

        bid = _make_board("Empty Board")
        pid = _make_project(bid, "Empty Project")
        t1 = _make_task(pid, "Lone Task")
        assert get_prerequisite_tasks(t1) == []


class TestGetUnmetPrerequisites:
    def test_returns_only_incomplete(self):
        from desktop.database.prerequisites import add_prerequisite, get_unmet_prerequisites
        from desktop.database.tasks import complete_task

        bid = _make_board("Unmet Board")
        pid = _make_project(bid, "Unmet Project")
        t_main = _make_task(pid, "Main")
        t_done = _make_task(pid, "Done")
        t_pending = _make_task(pid, "Pending")
        add_prerequisite(t_main, t_done)
        add_prerequisite(t_main, t_pending)

        # Complete t_done first (it has no prereqs, so complete_task succeeds)
        complete_task(t_done)

        unmet = get_unmet_prerequisites(t_main)
        titles = [t.title for t in unmet]
        assert "Pending" in titles
        assert "Done" not in titles

    def test_returns_empty_when_all_complete(self):
        from desktop.database.prerequisites import add_prerequisite, get_unmet_prerequisites
        from desktop.database.tasks import complete_task

        bid = _make_board("AllDone Board")
        pid = _make_project(bid, "AllDone Project")
        t_main = _make_task(pid, "Target")
        t_pre = _make_task(pid, "Pre")
        add_prerequisite(t_main, t_pre)
        complete_task(t_pre)

        assert get_unmet_prerequisites(t_main) == []


# ===========================================================================
# 4. formatting.py — shared utilities
# ===========================================================================


class TestFormatDuration:
    def test_zero_seconds(self):
        from desktop.formatting import format_duration

        assert format_duration(0) == "0h 00m 00s"

    def test_sixty_seconds(self):
        from desktop.formatting import format_duration

        assert format_duration(60) == "0h 01m 00s"

    def test_one_hour(self):
        from desktop.formatting import format_duration

        assert format_duration(3600) == "1h 00m 00s"

    def test_complex_duration(self):
        from desktop.formatting import format_duration

        assert format_duration(3661) == "1h 01m 01s"

    def test_large_value(self):
        from desktop.formatting import format_duration

        assert format_duration(86400) == "24h 00m 00s"

    def test_float_input_truncated(self):
        from desktop.formatting import format_duration

        assert format_duration(61.9) == "0h 01m 01s"


class TestDefaultJsonSerializer:
    def test_datetime_serialization(self):
        from desktop.formatting import default_json_serializer

        dt = datetime(2025, 1, 15, 10, 30, 0)
        result = default_json_serializer(dt)
        assert result == "2025-01-15T10:30:00"

    def test_timedelta_serialization(self):
        from desktop.formatting import default_json_serializer

        td = timedelta(hours=1, minutes=30)
        result = default_json_serializer(td)
        assert result == 5400

    def test_unsupported_type_raises(self):
        from desktop.formatting import default_json_serializer

        with pytest.raises(TypeError, match="not JSON serialisable"):
            default_json_serializer({"key": "value"})

    def test_works_with_json_dumps(self):
        from desktop.formatting import default_json_serializer

        data = {
            "when": datetime(2025, 6, 1, 12, 0),
            "elapsed": timedelta(seconds=120),
        }
        output = json.loads(json.dumps(data, default=default_json_serializer))
        assert output["when"] == "2025-06-01T12:00:00"
        assert output["elapsed"] == 120


class TestFilterUpcomingTasks:
    def test_filters_by_due_date_window(self):
        from desktop.formatting import filter_upcoming_tasks
        from desktop.models import Task

        now = datetime.now()
        tasks = [
            Task(title="past", due_date=now - timedelta(days=1)),
            Task(title="tomorrow", due_date=now + timedelta(days=1)),
            Task(title="next week", due_date=now + timedelta(days=6)),
            Task(title="far future", due_date=now + timedelta(days=30)),
        ]
        result = filter_upcoming_tasks(tasks, days=7)
        titles = [t.title for t in result]
        assert "tomorrow" in titles
        assert "next week" in titles
        assert "past" not in titles
        assert "far future" not in titles

    def test_excludes_completed_tasks(self):
        from desktop.formatting import filter_upcoming_tasks
        from desktop.models import Task

        now = datetime.now()
        tasks = [
            Task(title="done", due_date=now + timedelta(days=1), is_completed=True),
            Task(title="active", due_date=now + timedelta(days=1), is_completed=False),
        ]
        result = filter_upcoming_tasks(tasks)
        assert len(result) == 1
        assert result[0].title == "active"

    def test_excludes_tasks_without_due_date(self):
        from desktop.formatting import filter_upcoming_tasks
        from desktop.models import Task

        tasks = [Task(title="no date", due_date=None)]
        assert filter_upcoming_tasks(tasks) == []

    def test_respects_limit(self):
        from desktop.formatting import filter_upcoming_tasks
        from desktop.models import Task

        now = datetime.now()
        tasks = [Task(title=f"t{i}", due_date=now + timedelta(hours=i + 1)) for i in range(20)]
        result = filter_upcoming_tasks(tasks, limit=3)
        assert len(result) == 3

    def test_sorted_by_due_date(self):
        from desktop.formatting import filter_upcoming_tasks
        from desktop.models import Task

        now = datetime.now()
        tasks = [
            Task(title="later", due_date=now + timedelta(days=3)),
            Task(title="sooner", due_date=now + timedelta(days=1)),
            Task(title="soonest", due_date=now + timedelta(hours=1)),
        ]
        result = filter_upcoming_tasks(tasks)
        assert [t.title for t in result] == ["soonest", "sooner", "later"]


# ===========================================================================
# 5. models.py — type safety improvements
# ===========================================================================


class TestDBRowProtocol:
    def test_dict_satisfies_protocol(self):
        from desktop.models import DBRow

        d = {"id": 1, "name": "test"}
        assert isinstance(d, DBRow)

    def test_sqlite_row_like_object(self):
        from desktop.models import DBRow

        class FakeRow:
            def __getitem__(self, key: str):
                return {"id": 1, "name": "fake"}[key]

            def keys(self):
                return ["id", "name"]

        assert isinstance(FakeRow(), DBRow)


class TestCoerceDtAttrs:
    def test_parses_iso_string(self):
        from dataclasses import dataclass

        from desktop.models import _coerce_dt_attrs

        @dataclass
        class Obj:
            ts: datetime | str | None = None

        obj = Obj(ts="2025-03-15T10:30:00")
        _coerce_dt_attrs(obj, ("ts",))
        assert isinstance(obj.ts, datetime)
        assert obj.ts.year == 2025
        assert obj.ts.month == 3
        assert obj.ts.hour == 10

    def test_leaves_none_alone(self):
        from dataclasses import dataclass

        from desktop.models import _coerce_dt_attrs

        @dataclass
        class Obj:
            ts: datetime | str | None = None

        obj = Obj(ts=None)
        _coerce_dt_attrs(obj, ("ts",))
        assert obj.ts is None

    def test_leaves_datetime_alone(self):
        from dataclasses import dataclass

        from desktop.models import _coerce_dt_attrs

        dt = datetime(2025, 1, 1)

        @dataclass
        class Obj:
            ts: datetime | str | None = None

        obj = Obj(ts=dt)
        _coerce_dt_attrs(obj, ("ts",))
        assert obj.ts is dt


class TestTaskPriorityClamping:
    def test_clamp_negative_to_zero(self):
        from desktop.models import Task

        t = Task(priority=-5)
        assert t.priority == 0

    def test_clamp_above_four_to_four(self):
        from desktop.models import Task

        t = Task(priority=10)
        assert t.priority == 4

    def test_valid_priorities_unchanged(self):
        from desktop.models import Task

        for p in range(5):
            assert Task(priority=p).priority == p


class TestPauseEventType:
    def test_accepts_pause(self):
        from desktop.models import PauseEvent

        pe = PauseEvent(event_type="pause")
        assert pe.event_type == "pause"

    def test_accepts_resume(self):
        from desktop.models import PauseEvent

        pe = PauseEvent(event_type="resume")
        assert pe.event_type == "resume"

    def test_coerces_event_time_string(self):
        from desktop.models import PauseEvent

        pe = PauseEvent(event_type="pause", event_time="2025-06-01T12:00:00")
        assert isinstance(pe.event_time, datetime)


# ===========================================================================
# 6. operations.py — sync helpers
# ===========================================================================


class TestSyncTaskTags:
    def _setup(self) -> tuple[int, int]:
        bid = _make_board("SyncTagBoard")
        pid = _make_project(bid, "SyncTagProject")
        tid = _make_task(pid, "SyncTagTask")
        return pid, tid

    def test_sets_tags_on_untagged_task(self):
        from desktop.database.tags import get_task_tags
        from desktop.operations import sync_task_tags

        _, tid = self._setup()
        sync_task_tags(tid, ["alpha", "beta"])
        assert sorted(get_task_tags(tid)) == ["alpha", "beta"]

    def test_replaces_existing_tags(self):
        from desktop.database.tags import add_tag_to_task, get_task_tags
        from desktop.operations import sync_task_tags

        _, tid = self._setup()
        add_tag_to_task(tid, "old1")
        add_tag_to_task(tid, "old2")
        sync_task_tags(tid, ["new1"])
        assert get_task_tags(tid) == ["new1"]

    def test_clears_tags_with_empty_list(self):
        from desktop.database.tags import add_tag_to_task, get_task_tags
        from desktop.operations import sync_task_tags

        _, tid = self._setup()
        add_tag_to_task(tid, "gone")
        sync_task_tags(tid, [])
        assert get_task_tags(tid) == []


class TestSyncTaskPrerequisites:
    def _setup(self) -> tuple[int, int, int, int]:
        bid = _make_board("SyncPrereqBoard")
        pid = _make_project(bid, "SyncPrereqProject")
        t1 = _make_task(pid, "Main")
        t2 = _make_task(pid, "Prereq A")
        t3 = _make_task(pid, "Prereq B")
        return pid, t1, t2, t3

    def test_sets_prerequisites(self):
        from desktop.database.prerequisites import get_prerequisite_ids
        from desktop.operations import sync_task_prerequisites

        _, t1, t2, t3 = self._setup()
        sync_task_prerequisites(t1, [t2, t3])
        assert sorted(get_prerequisite_ids(t1)) == sorted([t2, t3])

    def test_replaces_prerequisites(self):
        from desktop.database.prerequisites import add_prerequisite, get_prerequisite_ids
        from desktop.operations import sync_task_prerequisites

        _, t1, t2, t3 = self._setup()
        add_prerequisite(t1, t2)
        sync_task_prerequisites(t1, [t3])
        ids = get_prerequisite_ids(t1)
        assert t3 in ids
        assert t2 not in ids

    def test_clears_prerequisites_with_empty_list(self):
        from desktop.database.prerequisites import add_prerequisite, get_prerequisite_ids
        from desktop.operations import sync_task_prerequisites

        _, t1, t2, _ = self._setup()
        add_prerequisite(t1, t2)
        sync_task_prerequisites(t1, [])
        assert get_prerequisite_ids(t1) == []


# ===========================================================================
# 7. boards.py — default board protection
# ===========================================================================


class TestDefaultBoardProtection:
    def test_delete_default_board_fails(self):
        from desktop.database.boards import delete_board, get_or_create_default_board

        default = get_or_create_default_board()
        assert delete_board(default.id) is False

    def test_delete_non_default_board_succeeds(self):
        from desktop.database.boards import (
            create_board,
            delete_board,
            get_board_by_id,
        )

        board = create_board("Ephemeral Board")
        assert delete_board(board.id) is True
        assert get_board_by_id(board.id) is None

    def test_default_board_protection_not_hardcoded_to_id_1(self):
        from desktop.database.boards import (
            create_board,
            delete_board,
            get_or_create_default_board,
        )

        # Create a board first so the default board won't get ID 1
        create_board("First Board")
        create_board("Second Board")
        default = get_or_create_default_board()
        # The default board might or might not be ID 1, but it must be protected
        assert delete_board(default.id) is False


# ===========================================================================
# 8. sessions.py — edge cases
# ===========================================================================


class TestSessionsEdgeCases:
    def test_get_sessions_no_matching_activity_returns_empty(self):
        from desktop.database.sessions import get_sessions

        result = get_sessions(activity_name="nonexistent_activity_xyz")
        assert result == []

    def test_get_sessions_date_range_filters_correctly(self):
        from datetime import datetime, timedelta

        from desktop.database.sessions import get_sessions, log_session

        base = datetime(2025, 6, 15, 12, 0, 0)
        log_session("RangeTest", timedelta(minutes=30), date=base)
        log_session("RangeTest", timedelta(minutes=30), date=base + timedelta(days=5))
        log_session("RangeTest", timedelta(minutes=30), date=base + timedelta(days=10))

        result = get_sessions(
            activity_name="RangeTest",
            start_date=base - timedelta(hours=1),
            end_date=base + timedelta(days=6),
        )
        assert len(result) == 2

    def test_stop_session_nonexistent_activity_returns_empty(self):
        from desktop.database.sessions import stop_session

        result = stop_session("totally_fake_activity_999")
        assert result == []

    def test_get_active_sessions_returns_only_without_end_time(self):
        from desktop.database.sessions import (
            get_active_sessions,
            start_session,
            stop_session,
        )

        s1 = start_session("ActiveTest1")
        s2 = start_session("ActiveTest2")
        stop_session("ActiveTest1")

        active = get_active_sessions()
        active_ids = [s.id for s in active]
        assert s2.id in active_ids
        assert s1.id not in active_ids

        # Clean up
        stop_session("ActiveTest2")


# ===========================================================================
# 9. activities.py — edge cases
# ===========================================================================


class TestActivitiesEdgeCases:
    def test_get_activity_nonexistent_returns_none(self):
        from desktop.database.activities import get_activity

        assert get_activity("absolutely_no_such_activity") is None

    def test_rename_activity_with_duplicate_name_returns_none(self):
        from desktop.database.activities import rename_activity_by_id

        a1 = _make_activity("OrigName1")
        _make_activity("OrigName2")
        result = rename_activity_by_id(a1, "OrigName2")
        assert result is None

    def test_list_activities_include_deleted(self):
        from desktop.database.activities import (
            list_activities,
            soft_delete_activity,
        )

        aid = _make_activity("SoonDeleted")
        soft_delete_activity(aid)

        without_deleted = list_activities(include_deleted=False)
        with_deleted = list_activities(include_deleted=True)

        names_without = [a.name for a in without_deleted]
        names_with = [a.name for a in with_deleted]

        assert "SoonDeleted" not in names_without
        assert "SoonDeleted" in names_with

    def test_soft_delete_marks_activity_as_deleted(self):
        from desktop.database.activities import (
            get_activity_by_id,
            soft_delete_activity,
        )

        aid = _make_activity("ToSoftDelete")
        soft_delete_activity(aid)
        a = get_activity_by_id(aid)
        assert a is not None
        assert a.is_deleted is True
        assert a.deleted_at is not None


# ===========================================================================
# 10. events.py — edge cases
# ===========================================================================


class TestEventsEdgeCases:
    def test_list_events_for_range_start_ge_end_returns_empty(self):
        from desktop.database.events import list_events_for_range

        now = datetime(2025, 6, 15, 12, 0, 0)
        assert list_events_for_range(now, now) == []
        assert list_events_for_range(now + timedelta(hours=1), now) == []

    def test_get_event_nonexistent_returns_none(self):
        from desktop.database.events import get_event

        assert get_event(999999) is None

    def test_create_and_get_event_round_trip(self):
        from desktop.database.calendars import get_default_calendar_id
        from desktop.database.events import create_event, get_event

        cal_id = get_default_calendar_id()
        start = datetime(2025, 7, 1, 10, 0, 0)
        end = datetime(2025, 7, 1, 11, 0, 0)

        created = create_event(
            calendar_id=cal_id,
            title="Round Trip Event",
            start_dt=start,
            end_dt=end,
            description="test description",
            location="test location",
        )
        assert created.id is not None

        fetched = get_event(created.id)
        assert fetched is not None
        assert fetched.title == "Round Trip Event"
        assert fetched.description == "test description"
        assert fetched.location == "test location"
        assert fetched.start_dt == start
        assert fetched.end_dt == end


# ===========================================================================
# 11. calendars.py — edge cases
# ===========================================================================


class TestCalendarsEdgeCases:
    def test_get_default_calendar_id_returns_valid_id(self):
        from desktop.database.calendars import get_default_calendar_id

        cal_id = get_default_calendar_id()
        assert isinstance(cal_id, int)
        assert cal_id > 0

    def test_set_and_get_default_calendar_round_trip(self):
        from desktop.database.calendars import (
            create_calendar,
            get_default_calendar_id,
            set_default_calendar,
        )

        cal = create_calendar("My Custom Cal", color="#ff0000")
        set_default_calendar(cal.id)
        assert get_default_calendar_id() == cal.id


# ===========================================================================
# 12. config.py — validation / clamping
# ===========================================================================


class TestConfigValidation:
    def test_port_below_range_clamped(self):
        from desktop.config import Config

        c = Config(web_port=80)
        assert c.web_port == 1024

    def test_port_above_range_clamped(self):
        from desktop.config import Config

        c = Config(web_port=70000)
        assert c.web_port == 65535

    def test_negative_window_width_clamped(self):
        from desktop.config import Config

        c = Config(window_width=-100)
        assert c.window_width == 400

    def test_negative_window_height_clamped(self):
        from desktop.config import Config

        c = Config(window_height=-50)
        assert c.window_height == 300

    def test_priority_above_four_clamped(self):
        from desktop.config import Config

        c = Config(default_priority=10)
        assert c.default_priority == 4

    def test_priority_zero_allowed(self):
        from desktop.config import Config

        c = Config(default_priority=0)
        assert c.default_priority == 0

    def test_priority_below_zero_clamped(self):
        from desktop.config import Config

        c = Config(default_priority=-1)
        assert c.default_priority == 0


# ===========================================================================
# 13. formatting.py — edge cases
# ===========================================================================


class TestFormatSessionEdgeCases:
    def test_active_session_returns_valid_dict(self):
        from desktop.formatting import format_session
        from desktop.models import Session

        s = Session(
            id=1,
            activity_name="Coding",
            start_time=datetime.now() - timedelta(minutes=10),
            end_time=None,
        )
        result = format_session(s)
        assert isinstance(result, dict)
        assert result["activity"] == "Coding"
        assert result["end"] == ""
        assert result["duration_seconds"] > 0
        assert isinstance(result["duration_formatted"], str)

    def test_paused_session_excludes_paused_time(self):
        from desktop.formatting import format_session
        from desktop.models import Session

        now = datetime.now()
        s = Session(
            id=2,
            activity_name="Reading",
            start_time=now - timedelta(minutes=30),
            end_time=now,
            is_paused=False,
            paused_seconds=600,  # 10 minutes paused
        )
        result = format_session(s)
        # 30 minutes total minus 10 minutes paused = ~20 minutes = ~1200 seconds
        assert 1150 <= result["duration_seconds"] <= 1250


class TestFormatDurationEdgeCases:
    def test_negative_input_handled(self):
        from desktop.formatting import format_duration

        result = format_duration(-100)
        # int(-100) divmod produces negative results; the function should
        # still return a string without raising
        assert isinstance(result, str)


class TestFilterUpcomingTasksEdgeCases:
    def test_empty_list_returns_empty(self):
        from desktop.formatting import filter_upcoming_tasks

        assert filter_upcoming_tasks([]) == []


class TestDefaultJsonSerializerEdgeCases:
    def test_date_object_raises_type_error(self):
        from datetime import date

        from desktop.formatting import default_json_serializer

        # date is not datetime, so the isinstance(obj, datetime) check
        # won't match; the function should raise TypeError
        with pytest.raises(TypeError, match="not JSON serialisable"):
            default_json_serializer(date(2025, 6, 15))


# ===========================================================================
# 14. web_server.py — CSS caching
# ===========================================================================


class TestWebServerCSS:
    def test_get_css_returns_nonempty_string(self):
        from desktop.web_server import _get_css

        css = _get_css()
        assert isinstance(css, str)
        assert len(css) > 0

    def test_get_css_returns_same_on_repeated_calls(self):
        from desktop.web_server import _get_css

        first = _get_css()
        second = _get_css()
        assert first is second

    def test_build_css_returns_valid_css_string(self):
        from desktop.web_server import _build_css

        css = _build_css()
        assert isinstance(css, str)
        assert "body" in css
        assert "font-family" in css
        assert "{" in css


# ===========================================================================
# 15. operations.py — edge cases
# ===========================================================================


class TestSyncTaskTagsEdgeCases:
    def _setup(self) -> tuple[int, int]:
        bid = _make_board("SyncEdgeBoard")
        pid = _make_project(bid, "SyncEdgeProject")
        tid = _make_task(pid, "SyncEdgeTask")
        return pid, tid

    def test_empty_list_clears_all_tags(self):
        from desktop.database.tags import add_tag_to_task, get_task_tags
        from desktop.operations import sync_task_tags

        _, tid = self._setup()
        add_tag_to_task(tid, "a")
        add_tag_to_task(tid, "b")
        add_tag_to_task(tid, "c")
        sync_task_tags(tid, [])
        assert get_task_tags(tid) == []

    def test_idempotent_same_list_twice(self):
        from desktop.database.tags import get_task_tags
        from desktop.operations import sync_task_tags

        _, tid = self._setup()
        sync_task_tags(tid, ["x", "y"])
        first = sorted(get_task_tags(tid))
        sync_task_tags(tid, ["x", "y"])
        second = sorted(get_task_tags(tid))
        assert first == second == ["x", "y"]


class TestSyncTaskPrerequisitesEdgeCases:
    def _setup(self) -> tuple[int, int, int]:
        bid = _make_board("PrereqEdgeBoard")
        pid = _make_project(bid, "PrereqEdgeProject")
        t1 = _make_task(pid, "Main")
        t2 = _make_task(pid, "Dep")
        return pid, t1, t2

    def test_add_to_task_with_no_existing_prerequisites(self):
        from desktop.database.prerequisites import get_prerequisite_ids
        from desktop.operations import sync_task_prerequisites

        _, t1, t2 = self._setup()
        # t1 starts with no prerequisites
        assert get_prerequisite_ids(t1) == []
        sync_task_prerequisites(t1, [t2])
        assert get_prerequisite_ids(t1) == [t2]


# ===========================================================================
# 16. version_check.py — _parse_version
# ===========================================================================


class TestParseVersion:
    def test_simple_release(self):
        from desktop.version_check import _parse_version

        assert _parse_version("1.0.0") == (1, 0, 0, 1)

    def test_v_prefix_stripped(self):
        from desktop.version_check import _parse_version

        assert _parse_version("v1.2.3") == (1, 2, 3, 1)

    def test_pep440_prerelease(self):
        from desktop.version_check import _parse_version

        assert _parse_version("1.0.0rc1") == (1, 0, 0, 0)

    def test_semver_prerelease(self):
        from desktop.version_check import _parse_version

        assert _parse_version("1.0.0-rc.1") == (1, 0, 0, 0)

    def test_two_part_version_padded(self):
        from desktop.version_check import _parse_version

        assert _parse_version("1.0") == (1, 0, 0, 1)

    def test_release_greater_than_older_release(self):
        from desktop.version_check import _parse_version

        assert _parse_version("2.0.0") > _parse_version("1.9.9")

    def test_release_greater_than_prerelease(self):
        from desktop.version_check import _parse_version

        assert _parse_version("1.0.0") > _parse_version("1.0.0rc1")

    def test_prerelease_variants_same_bucket(self):
        from desktop.version_check import _parse_version

        pep440 = _parse_version("1.0.0rc2")
        semver = _parse_version("1.0.0-rc.1")
        # Both are pre-release: last element is 0
        assert pep440[-1] == 0
        assert semver[-1] == 0
        # Both share the same numeric base
        assert pep440[:3] == semver[:3] == (1, 0, 0)


# ===========================================================================
# 17. activities.py — set_activity_groups database locking fix
# ===========================================================================


class TestSetActivityGroupsLocking:
    def test_set_groups_with_new_group_names(self):
        from desktop.database.activities import (
            get_activity_groups,
            set_activity_groups,
        )

        aid = _make_activity("LockTest")
        set_activity_groups(aid, ["NewGroup1", "NewGroup2"])
        result = sorted(get_activity_groups(aid))
        assert result == ["NewGroup1", "NewGroup2"]

    def test_set_groups_replaces_existing(self):
        from desktop.database.activities import (
            add_activity_group,
            get_activity_groups,
            set_activity_groups,
        )

        aid = _make_activity("ReplaceTest")
        add_activity_group(aid, "OldGroup")
        set_activity_groups(aid, ["BrandNew1", "BrandNew2"])
        result = sorted(get_activity_groups(aid))
        assert result == ["BrandNew1", "BrandNew2"]
        assert "OldGroup" not in result

    def test_set_groups_empty_list_clears(self):
        from desktop.database.activities import (
            add_activity_group,
            get_activity_groups,
            set_activity_groups,
        )

        aid = _make_activity("ClearTest")
        add_activity_group(aid, "SomeGroup")
        set_activity_groups(aid, [])
        assert get_activity_groups(aid) == []

    def test_set_groups_max_three(self):
        from desktop.database.activities import (
            get_activity_groups,
            set_activity_groups,
        )

        aid = _make_activity("MaxTest")
        set_activity_groups(aid, ["G1", "G2", "G3", "G4"])
        result = get_activity_groups(aid)
        assert len(result) == 3

    def test_set_groups_strips_whitespace(self):
        from desktop.database.activities import (
            get_activity_groups,
            set_activity_groups,
        )

        aid = _make_activity("StripTest")
        set_activity_groups(aid, ["  Padded  "])
        result = get_activity_groups(aid)
        assert result == ["Padded"]

    def test_set_groups_skips_empty_names(self):
        from desktop.database.activities import (
            get_activity_groups,
            set_activity_groups,
        )

        aid = _make_activity("EmptyNameTest")
        set_activity_groups(aid, ["Valid", "", "  "])
        result = get_activity_groups(aid)
        assert result == ["Valid"]

    def test_set_groups_mixed_existing_and_new(self):
        from desktop.database.activities import (
            create_group,
            get_activity_groups,
            set_activity_groups,
        )

        aid = _make_activity("MixedTest")
        create_group("PreExisting")
        set_activity_groups(aid, ["PreExisting", "FreshGroup"])
        result = sorted(get_activity_groups(aid))
        assert result == ["FreshGroup", "PreExisting"]


# ===========================================================================
# 18. connection.py — backup_database
# ===========================================================================


class TestBackupDatabase:
    def test_backup_creates_file_in_specified_directory(self, tmp_path: Path):
        from desktop.database.connection import backup_database

        backup_dir = tmp_path / "backups"
        result = backup_database(backup_dir=backup_dir, filename="test_backup.db")
        assert result is True
        assert (backup_dir / "test_backup.db").exists()

    def test_backup_file_is_valid_sqlite(self, tmp_path: Path):
        import sqlite3 as _sqlite3

        from desktop.database.connection import backup_database

        backup_dir = tmp_path / "backups"
        backup_database(backup_dir=backup_dir, filename="valid.db")
        conn = _sqlite3.connect(backup_dir / "valid.db")
        # A valid SQLite DB should respond to a pragma query
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        assert result[0] == "ok"

    def test_backup_returns_true_on_success(self, tmp_path: Path):
        from desktop.database.connection import backup_database

        result = backup_database(backup_dir=tmp_path, filename="success.db")
        assert result is True

    def test_backup_auto_generates_timestamped_filename(self, tmp_path: Path):
        from desktop.database.connection import backup_database

        backup_database(backup_dir=tmp_path)
        files = list(tmp_path.glob("grouper_backup_*.db"))
        assert len(files) == 1


# ===========================================================================
# 19. connection.py — path accessors
# ===========================================================================


class TestPathAccessors:
    def test_get_data_directory_returns_path(self):
        from desktop.database.connection import get_data_directory

        result = get_data_directory()
        assert isinstance(result, Path)

    def test_get_database_path_returns_path(self):
        from desktop.database.connection import get_database_path

        result = get_database_path()
        assert isinstance(result, Path)

    def test_get_database_path_ends_in_db(self):
        from desktop.database.connection import get_database_path

        result = get_database_path()
        assert result.suffix == ".db"

    def test_database_path_is_inside_data_directory(self):
        from desktop.database.connection import get_data_directory, get_database_path

        data_dir = get_data_directory()
        db_path = get_database_path()
        assert db_path.parent == data_dir


# ===========================================================================
# 20. connection.py — version tracking
# ===========================================================================


class TestVersionTracking:
    def test_get_version_returns_int(self):
        from desktop.database.connection import get_version

        result = get_version()
        assert isinstance(result, int)

    def test_bump_version_increments(self):
        from desktop.database.connection import bump_version, get_version

        before = get_version()
        bump_version()
        after = get_version()
        assert after == before + 1

    def test_multiple_bumps_increment_correctly(self):
        from desktop.database.connection import bump_version, get_version

        before = get_version()
        bump_version()
        bump_version()
        bump_version()
        after = get_version()
        assert after == before + 3


# ===========================================================================
# 21. connection.py — set_archived
# ===========================================================================


class TestSetArchived:
    def test_archive_activity(self):
        from desktop.database.connection import get_connection, set_archived

        aid = _make_activity("ArchiveMe")
        set_archived("activities", aid, True)
        with get_connection() as conn:
            row = conn.execute(
                "SELECT is_archived, archived_at FROM activities WHERE id = ?",
                (aid,),
            ).fetchone()
        assert row["is_archived"] == 1
        assert row["archived_at"] is not None

    def test_unarchive_activity(self):
        from desktop.database.connection import get_connection, set_archived

        aid = _make_activity("UnarchiveMe")
        set_archived("activities", aid, True)
        set_archived("activities", aid, False)
        with get_connection() as conn:
            row = conn.execute(
                "SELECT is_archived, archived_at FROM activities WHERE id = ?",
                (aid,),
            ).fetchone()
        assert row["is_archived"] == 0
        assert row["archived_at"] is None

    def test_invalid_table_raises_value_error(self):
        from desktop.database.connection import set_archived

        with pytest.raises(ValueError, match="Cannot archive table"):
            set_archived("nonexistent_table", 1, True)

    def test_archive_project(self):
        from desktop.database.connection import get_connection, set_archived

        bid = _make_board("ArchBoard")
        pid = _make_project(bid, "ArchProject")
        set_archived("projects", pid, True)
        with get_connection() as conn:
            row = conn.execute(
                "SELECT is_archived, archived_at FROM projects WHERE id = ?",
                (pid,),
            ).fetchone()
        assert row["is_archived"] == 1
        assert row["archived_at"] is not None


# ===========================================================================
# 22. events.py — get_event_for_task, delete_event, update_event
# ===========================================================================


class TestGetEventForTask:
    def _make_calendar(self) -> int:
        from desktop.database.calendars import create_calendar

        return create_calendar("EvtTaskCal").id

    def test_returns_event_linked_to_task(self):
        from desktop.database.events import create_event, get_event_for_task

        cal_id = self._make_calendar()
        bid = _make_board("EvtTaskBoard")
        pid = _make_project(bid, "EvtTaskProject")
        tid = _make_task(pid, "Linked Task")
        start = datetime(2025, 8, 1, 10, 0, 0)
        end = datetime(2025, 8, 1, 11, 0, 0)
        evt = create_event(cal_id, "Task Event", start, end, linked_task_id=tid)
        result = get_event_for_task(tid)
        assert result is not None
        assert result.id == evt.id
        assert result.title == "Task Event"
        assert result.linked_task_id == tid

    def test_returns_none_when_no_linked_event(self):
        from desktop.database.events import get_event_for_task

        bid = _make_board("NoEvtBoard")
        pid = _make_project(bid, "NoEvtProject")
        tid = _make_task(pid, "Unlinked Task")
        assert get_event_for_task(tid) is None


class TestDeleteEvent:
    def test_deletes_existing_event(self):
        from desktop.database.calendars import create_calendar
        from desktop.database.events import create_event, delete_event, get_event

        cal = create_calendar("DelEvtCal")
        start = datetime(2025, 9, 1, 10, 0, 0)
        end = datetime(2025, 9, 1, 11, 0, 0)
        evt = create_event(cal.id, "To Delete", start, end)
        assert get_event(evt.id) is not None
        delete_event(evt.id)
        assert get_event(evt.id) is None

    def test_delete_nonexistent_event_does_not_raise(self):
        from desktop.database.events import delete_event

        delete_event(999999)


class TestUpdateEvent:
    def test_updates_title(self):
        from desktop.database.calendars import create_calendar
        from desktop.database.events import create_event, get_event, update_event

        cal = create_calendar("UpdEvtCal")
        start = datetime(2025, 10, 1, 9, 0, 0)
        end = datetime(2025, 10, 1, 10, 0, 0)
        evt = create_event(cal.id, "Original Title", start, end)
        update_event(evt.id, title="Updated Title")
        fetched = get_event(evt.id)
        assert fetched is not None
        assert fetched.title == "Updated Title"

    def test_updates_description_and_location(self):
        from desktop.database.calendars import create_calendar
        from desktop.database.events import create_event, get_event, update_event

        cal = create_calendar("UpdEvtCal2")
        start = datetime(2025, 10, 2, 9, 0, 0)
        end = datetime(2025, 10, 2, 10, 0, 0)
        evt = create_event(cal.id, "Evt", start, end)
        update_event(evt.id, description="New desc", location="New loc")
        fetched = get_event(evt.id)
        assert fetched.description == "New desc"
        assert fetched.location == "New loc"

    def test_updates_datetime_fields(self):
        from desktop.database.calendars import create_calendar
        from desktop.database.events import create_event, get_event, update_event

        cal = create_calendar("UpdEvtCal3")
        start = datetime(2025, 10, 3, 9, 0, 0)
        end = datetime(2025, 10, 3, 10, 0, 0)
        evt = create_event(cal.id, "Evt DT", start, end)
        new_start = datetime(2025, 11, 1, 14, 0, 0)
        new_end = datetime(2025, 11, 1, 15, 0, 0)
        update_event(evt.id, start_dt=new_start, end_dt=new_end)
        fetched = get_event(evt.id)
        assert fetched.start_dt == new_start
        assert fetched.end_dt == new_end

    def test_ignores_disallowed_keys(self):
        from desktop.database.calendars import create_calendar
        from desktop.database.events import create_event, get_event, update_event

        cal = create_calendar("UpdEvtCal4")
        start = datetime(2025, 10, 4, 9, 0, 0)
        end = datetime(2025, 10, 4, 10, 0, 0)
        evt = create_event(cal.id, "Evt Ign", start, end)
        update_event(evt.id, id=9999, fake_field="nope", title="Allowed")
        fetched = get_event(evt.id)
        assert fetched.id == evt.id
        assert fetched.title == "Allowed"


# ===========================================================================
# 23. calendars.py — CRUD
# ===========================================================================


class TestCalendarCRUD:
    def test_create_and_get_round_trip(self):
        from desktop.database.calendars import create_calendar, get_calendar

        cal = create_calendar("Round Trip Cal", color="#aabbcc")
        assert cal.id is not None
        assert cal.name == "Round Trip Cal"
        assert cal.color == "#aabbcc"
        fetched = get_calendar(cal.id)
        assert fetched is not None
        assert fetched.name == "Round Trip Cal"
        assert fetched.color == "#aabbcc"

    def test_list_calendars_returns_created(self):
        from desktop.database.calendars import create_calendar, list_calendars

        cal = create_calendar("Listed Cal")
        cals = list_calendars()
        names = [c.name for c in cals]
        assert cal.name in names

    def test_update_calendar_changes_fields(self):
        from desktop.database.calendars import create_calendar, get_calendar, update_calendar

        cal = create_calendar("Upd Cal", color="#111111")
        update_calendar(cal.id, name="Renamed Cal", color="#222222")
        fetched = get_calendar(cal.id)
        assert fetched.name == "Renamed Cal"
        assert fetched.color == "#222222"

    def test_archive_calendar_hides_from_default_list(self):
        from desktop.database.calendars import (
            archive_calendar,
            create_calendar,
            list_calendars,
        )

        cal = create_calendar("Archive Me Cal")
        archive_calendar(cal.id)
        default = list_calendars(include_archived=False)
        default_ids = [c.id for c in default]
        assert cal.id not in default_ids

    def test_list_calendars_include_archived_shows_archived(self):
        from desktop.database.calendars import (
            archive_calendar,
            create_calendar,
            list_calendars,
        )

        cal = create_calendar("Archived Visible Cal")
        archive_calendar(cal.id)
        all_cals = list_calendars(include_archived=True)
        all_ids = [c.id for c in all_cals]
        assert cal.id in all_ids


# ===========================================================================
# 24. task_links.py — link CRUD and detect_link_type
# ===========================================================================


class TestTaskLinkCRUD:
    def _setup_task(self) -> int:
        bid = _make_board("LinkBoard")
        pid = _make_project(bid, "LinkProject")
        return _make_task(pid, "Link Task")

    def test_add_and_get_links_round_trip(self):
        from desktop.database.task_links import add_link, get_links_for_task

        tid = self._setup_task()
        link = add_link(tid, "https://example.com", label="Example")
        assert link.id is not None
        assert link.url == "https://example.com"
        assert link.label == "Example"
        assert link.link_type == "url"
        links = get_links_for_task(tid)
        assert len(links) == 1
        assert links[0].url == "https://example.com"

    def test_update_link_changes_url(self):
        from desktop.database.task_links import add_link, get_links_for_task, update_link

        tid = self._setup_task()
        link = add_link(tid, "https://old.com")
        update_link(link.id, url="https://new.com")
        links = get_links_for_task(tid)
        assert len(links) == 1
        assert links[0].url == "https://new.com"

    def test_update_link_changes_label(self):
        from desktop.database.task_links import add_link, get_links_for_task, update_link

        tid = self._setup_task()
        link = add_link(tid, "https://example.com", label="Old Label")
        update_link(link.id, label="New Label")
        links = get_links_for_task(tid)
        assert links[0].label == "New Label"

    def test_delete_link_removes_it(self):
        from desktop.database.task_links import add_link, delete_link, get_links_for_task

        tid = self._setup_task()
        link = add_link(tid, "https://delete-me.com")
        assert len(get_links_for_task(tid)) == 1
        delete_link(link.id)
        assert len(get_links_for_task(tid)) == 0


class TestDetectLinkType:
    def test_http_url(self):
        from desktop.database.task_links import detect_link_type

        assert detect_link_type("https://example.com") == "url"

    def test_http_without_s(self):
        from desktop.database.task_links import detect_link_type

        assert detect_link_type("http://example.com") == "url"

    def test_file_uri(self):
        from desktop.database.task_links import detect_link_type

        assert detect_link_type("file:///home/user/doc.txt") == "file"

    def test_unc_path(self):
        from desktop.database.task_links import detect_link_type

        assert detect_link_type("\\\\server\\share\\file.txt") == "file"

    def test_windows_drive_letter(self):
        from desktop.database.task_links import detect_link_type

        assert detect_link_type("C:\\Users\\doc.txt") == "file"

    def test_unix_absolute_path(self):
        from desktop.database.task_links import detect_link_type

        assert detect_link_type("/home/user/doc.txt") == "file"

    def test_tilde_path(self):
        from desktop.database.task_links import detect_link_type

        assert detect_link_type("~/Documents/file.txt") == "file"

    def test_bare_domain_is_url(self):
        from desktop.database.task_links import detect_link_type

        assert detect_link_type("example.com") == "url"


# ===========================================================================
# 25. projects.py — get_or_create, archive/unarchive, rename
# ===========================================================================


class TestProjectGetOrCreate:
    def test_creates_project_if_not_exists(self):
        from desktop.database.projects import get_or_create_project, get_project

        bid = _make_board("GetOrCreateBoard")
        p = get_or_create_project("BrandNewProject", board_id=bid)
        assert p.name == "BrandNewProject"
        assert p.id is not None
        fetched = get_project("BrandNewProject")
        assert fetched is not None
        assert fetched.id == p.id

    def test_returns_existing_if_exists(self):
        from desktop.database.projects import get_or_create_project

        bid = _make_board("GetOrCreateBoard2")
        p1 = get_or_create_project("ExistingProject", board_id=bid)
        p2 = get_or_create_project("ExistingProject", board_id=bid)
        assert p1.id == p2.id
        assert p1.name == p2.name


class TestProjectArchiveUnarchive:
    def test_archive_and_unarchive_round_trip(self):
        from desktop.database.projects import (
            archive_project,
            get_project_by_id,
            unarchive_project,
        )

        bid = _make_board("ArchProjBoard")
        pid = _make_project(bid, "ArchRoundTrip")
        archive_project(pid)
        p = get_project_by_id(pid)
        assert p is not None
        assert p.is_archived is True
        unarchive_project(pid)
        p = get_project_by_id(pid)
        assert p.is_archived is False


class TestProjectRename:
    def test_rename_with_valid_name_succeeds(self):
        from desktop.database.projects import get_project, rename_project

        bid = _make_board("RenameBoard")
        _make_project(bid, "OldName")
        result = rename_project("OldName", "NewName")
        assert result is not None
        assert result.name == "NewName"
        assert get_project("OldName") is None
        assert get_project("NewName") is not None

    def test_rename_nonexistent_returns_none(self):
        from desktop.database.projects import rename_project

        assert rename_project("NoSuchProject", "Whatever") is None


# ===========================================================================
# 26. activities.py — Group CRUD
# ===========================================================================


class TestGroupCreate:
    def test_create_group_returns_group_with_correct_name(self):
        from desktop.database.activities import create_group

        g = create_group("Development")
        assert g.name == "Development"
        assert g.id is not None

    def test_create_group_strips_whitespace(self):
        from desktop.database.activities import create_group

        g = create_group("  Padded  ")
        assert g.name == "Padded"

    def test_create_duplicate_group_raises(self):
        import sqlite3

        from desktop.database.activities import create_group

        create_group("Unique")
        with pytest.raises(sqlite3.IntegrityError):
            create_group("Unique")


class TestGetOrCreateGroup:
    def test_creates_if_not_exists(self):
        from desktop.database.activities import get_group_by_name, get_or_create_group

        g = get_or_create_group("Brand New")
        assert g.id is not None
        assert g.name == "Brand New"
        fetched = get_group_by_name("Brand New")
        assert fetched is not None
        assert fetched.id == g.id

    def test_returns_existing_if_exists(self):
        from desktop.database.activities import create_group, get_or_create_group

        original = create_group("Existing")
        returned = get_or_create_group("Existing")
        assert returned.id == original.id
        assert returned.name == original.name


class TestGetGroupByName:
    def test_finds_by_name(self):
        from desktop.database.activities import create_group, get_group_by_name

        created = create_group("FindMe")
        found = get_group_by_name("FindMe")
        assert found is not None
        assert found.id == created.id
        assert found.name == "FindMe"

    def test_returns_none_for_unknown(self):
        from desktop.database.activities import get_group_by_name

        assert get_group_by_name("NoSuchGroup") is None

    def test_case_insensitive_lookup(self):
        from desktop.database.activities import create_group, get_group_by_name

        create_group("MixedCase")
        found = get_group_by_name("mixedcase")
        assert found is not None
        assert found.name == "MixedCase"


class TestGetGroupById:
    def test_finds_by_id(self):
        from desktop.database.activities import create_group, get_group_by_id

        created = create_group("ById")
        found = get_group_by_id(created.id)
        assert found is not None
        assert found.name == "ById"

    def test_returns_none_for_unknown_id(self):
        from desktop.database.activities import get_group_by_id

        assert get_group_by_id(999999) is None


class TestRenameGroup:
    def test_rename_succeeds_with_valid_name(self):
        from desktop.database.activities import create_group, get_group_by_id, rename_group

        g = create_group("OldGroupName")
        result = rename_group(g.id, "NewGroupName")
        assert result is True
        fetched = get_group_by_id(g.id)
        assert fetched.name == "NewGroupName"

    def test_rename_returns_false_for_duplicate(self):
        from desktop.database.activities import create_group, rename_group

        create_group("TakenName")
        g2 = create_group("WillRename")
        result = rename_group(g2.id, "TakenName")
        assert result is False

    def test_rename_returns_false_for_empty_name(self):
        from desktop.database.activities import create_group, rename_group

        g = create_group("SomeGroup")
        result = rename_group(g.id, "   ")
        assert result is False

    def test_rename_returns_false_for_nonexistent_id(self):
        from desktop.database.activities import rename_group

        result = rename_group(999999, "Whatever")
        assert result is False


class TestDeleteGroup:
    def test_delete_removes_the_group(self):
        from desktop.database.activities import create_group, delete_group, get_group_by_id

        g = create_group("ToDelete")
        result = delete_group(g.id)
        assert result is True
        assert get_group_by_id(g.id) is None

    def test_delete_nonexistent_returns_false(self):
        from desktop.database.activities import delete_group

        assert delete_group(999999) is False


class TestListAllGroups:
    def test_returns_all_groups(self):
        from desktop.database.activities import create_group, list_all_groups

        create_group("GroupAlpha")
        create_group("GroupBeta")
        create_group("GroupGamma")
        groups = list_all_groups()
        names = [g.name for g in groups]
        assert "GroupAlpha" in names
        assert "GroupBeta" in names
        assert "GroupGamma" in names

    def test_returns_list(self):
        from desktop.database.activities import list_all_groups

        groups = list_all_groups()
        assert isinstance(groups, list)


# ===========================================================================
# 27. activities.py — Activity-group associations
# ===========================================================================


class TestAddActivityGroup:
    def test_links_activity_to_group(self):
        from desktop.database.activities import add_activity_group, get_activity_groups

        aid = _make_activity("LinkedAct")
        result = add_activity_group(aid, "DevGroup")
        assert result is True
        groups = get_activity_groups(aid)
        assert "DevGroup" in groups

    def test_duplicate_link_returns_false(self):
        from desktop.database.activities import add_activity_group

        aid = _make_activity("DupLinkAct")
        assert add_activity_group(aid, "SameGroup") is True
        assert add_activity_group(aid, "SameGroup") is False

    def test_empty_group_name_returns_false(self):
        from desktop.database.activities import add_activity_group

        aid = _make_activity("EmptyGrpAct")
        assert add_activity_group(aid, "") is False
        assert add_activity_group(aid, "   ") is False


class TestRemoveActivityGroup:
    def test_unlinks_activity_from_group(self):
        from desktop.database.activities import (
            add_activity_group,
            get_activity_groups,
            remove_activity_group,
        )

        aid = _make_activity("UnlinkAct")
        add_activity_group(aid, "TempGroup")
        assert "TempGroup" in get_activity_groups(aid)
        result = remove_activity_group(aid, "TempGroup")
        assert result is True
        assert "TempGroup" not in get_activity_groups(aid)

    def test_remove_nonexistent_link_returns_false(self):
        from desktop.database.activities import remove_activity_group

        aid = _make_activity("NoLinkAct")
        result = remove_activity_group(aid, "NeverAdded")
        assert result is False


class TestGetActivityGroups:
    def test_returns_group_names_for_activity(self):
        from desktop.database.activities import add_activity_group, get_activity_groups

        aid = _make_activity("MultiGrpAct")
        add_activity_group(aid, "GroupX")
        add_activity_group(aid, "GroupY")
        groups = get_activity_groups(aid)
        assert sorted(groups) == ["GroupX", "GroupY"]

    def test_returns_empty_for_ungrouped_activity(self):
        from desktop.database.activities import get_activity_groups

        aid = _make_activity("UngroupedAct")
        assert get_activity_groups(aid) == []


class TestSetActivityGroups:
    def test_replaces_all_groups(self):
        from desktop.database.activities import (
            add_activity_group,
            create_group,
            get_activity_groups,
            set_activity_groups,
        )

        aid = _make_activity("ReplaceGrpAct")
        add_activity_group(aid, "OldGroup1")
        add_activity_group(aid, "OldGroup2")
        # Pre-create new groups to avoid database lock inside set_activity_groups
        create_group("NewGroup1")
        create_group("NewGroup2")
        set_activity_groups(aid, ["NewGroup1", "NewGroup2"])
        groups = get_activity_groups(aid)
        assert sorted(groups) == ["NewGroup1", "NewGroup2"]
        assert "OldGroup1" not in groups
        assert "OldGroup2" not in groups

    def test_clears_groups_with_empty_list(self):
        from desktop.database.activities import (
            add_activity_group,
            get_activity_groups,
            set_activity_groups,
        )

        aid = _make_activity("ClearGrpAct")
        add_activity_group(aid, "WillBeCleared")
        set_activity_groups(aid, [])
        assert get_activity_groups(aid) == []

    def test_max_three_groups(self):
        from desktop.database.activities import (
            create_group,
            get_activity_groups,
            set_activity_groups,
        )

        aid = _make_activity("MaxGrpAct")
        # Pre-create groups to avoid database lock inside set_activity_groups
        for name in ["G1", "G2", "G3", "G4", "G5"]:
            create_group(name)
        set_activity_groups(aid, ["G1", "G2", "G3", "G4", "G5"])
        groups = get_activity_groups(aid)
        assert len(groups) == 3


class TestGetActivitiesByGroup:
    def test_returns_activities_in_group(self):
        from desktop.database.activities import add_activity_group, get_activities_by_group

        a1 = _make_activity("InGroupAct1")
        a2 = _make_activity("InGroupAct2")
        _make_activity("NotInGroupAct")
        add_activity_group(a1, "TargetGroup")
        add_activity_group(a2, "TargetGroup")
        activities = get_activities_by_group("TargetGroup")
        names = [a.name for a in activities]
        assert "InGroupAct1" in names
        assert "InGroupAct2" in names
        assert "NotInGroupAct" not in names

    def test_excludes_deleted_activities(self):
        from desktop.database.activities import (
            add_activity_group,
            get_activities_by_group,
            soft_delete_activity,
        )

        aid = _make_activity("DeletedFromGroup")
        add_activity_group(aid, "ActiveGroup")
        soft_delete_activity(aid)
        activities = get_activities_by_group("ActiveGroup")
        names = [a.name for a in activities]
        assert "DeletedFromGroup" not in names

    def test_returns_empty_for_unknown_group(self):
        from desktop.database.activities import get_activities_by_group

        assert get_activities_by_group("NonexistentGroup") == []


class TestGetUngroupedActivities:
    def test_returns_activities_with_no_groups(self):
        from desktop.database.activities import (
            add_activity_group,
            get_ungrouped_activities,
        )

        _make_activity("UngroupedOne")
        grouped = _make_activity("GroupedOne")
        add_activity_group(grouped, "SomeGroup")
        result = get_ungrouped_activities()
        names = [a.name for a in result]
        assert "UngroupedOne" in names
        assert "GroupedOne" not in names

    def test_excludes_deleted_activities(self):
        from desktop.database.activities import (
            get_ungrouped_activities,
            soft_delete_activity,
        )

        aid = _make_activity("DeletedUngrouped")
        soft_delete_activity(aid)
        result = get_ungrouped_activities()
        names = [a.name for a in result]
        assert "DeletedUngrouped" not in names

    def test_excludes_archived_activities(self):
        from desktop.database.activities import (
            archive_activity,
            get_ungrouped_activities,
        )

        aid = _make_activity("ArchivedUngrouped")
        archive_activity(aid)
        result = get_ungrouped_activities()
        names = [a.name for a in result]
        assert "ArchivedUngrouped" not in names


# ===========================================================================
# 28. activities.py — Background group
# ===========================================================================


class TestEnsureBackgroundGroup:
    def test_creates_background_group_idempotently(self):
        from desktop.database.activities import (
            BACKGROUND_GROUP_NAME,
            ensure_background_group,
            get_group_by_name,
        )

        ensure_background_group()
        g1 = get_group_by_name(BACKGROUND_GROUP_NAME)
        assert g1 is not None
        ensure_background_group()
        g2 = get_group_by_name(BACKGROUND_GROUP_NAME)
        assert g2 is not None
        assert g1.id == g2.id

    def test_assigns_background_activities_to_background_group(self):
        from desktop.database.activities import (
            BACKGROUND_GROUP_NAME,
            ensure_background_group,
            get_activity_groups,
        )

        aid = _make_activity("BgActivity", is_background=True)
        ensure_background_group()
        groups = get_activity_groups(aid)
        assert BACKGROUND_GROUP_NAME in groups

    def test_does_not_affect_non_background_activities(self):
        from desktop.database.activities import (
            BACKGROUND_GROUP_NAME,
            ensure_background_group,
            get_activity_groups,
        )

        aid = _make_activity("NormalActivity", is_background=False)
        ensure_background_group()
        groups = get_activity_groups(aid)
        assert BACKGROUND_GROUP_NAME not in groups


# ---------------------------------------------------------------------------
# Section 18: start_of_day helper
# ---------------------------------------------------------------------------


class TestStartOfDay:
    def test_truncates_time(self):
        from desktop.formatting import start_of_day

        dt = datetime(2026, 3, 26, 14, 30, 45, 123456)
        result = start_of_day(dt)
        assert result == datetime(2026, 3, 26, 0, 0, 0, 0)

    def test_midnight_is_noop(self):
        from desktop.formatting import start_of_day

        dt = datetime(2026, 3, 26, 0, 0, 0, 0)
        assert start_of_day(dt) == dt

    def test_preserves_date(self):
        from desktop.formatting import start_of_day

        dt = datetime(2026, 12, 31, 23, 59, 59)
        result = start_of_day(dt)
        assert result.year == 2026
        assert result.month == 12
        assert result.day == 31


# ---------------------------------------------------------------------------
# Section 19: __all__ export validation
# ---------------------------------------------------------------------------


class TestAllExports:
    """Verify __all__ lists match actual module contents."""

    def _check_all(self, module_path: str):
        import importlib

        mod = importlib.import_module(module_path)
        assert hasattr(mod, "__all__"), f"{module_path} missing __all__"
        for name in mod.__all__:
            assert hasattr(mod, name), f"{module_path}.__all__ lists '{name}' but it doesn't exist"

    def test_formatting_all(self):
        self._check_all("desktop.formatting")

    def test_operations_all(self):
        self._check_all("desktop.operations")

    def test_config_all(self):
        self._check_all("desktop.config")

    def test_models_all(self):
        self._check_all("desktop.models")

    def test_version_check_all(self):
        self._check_all("desktop.version_check")
