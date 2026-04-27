"""test_task_event_sync.py -- Integration tests for Bug 164: Calendar/Task Sync Deduplication.

Validates the bidirectional sync between calendar events and tasks:
- update_event() syncs start_dt back to the linked task's due_date
- update_task() syncs due_date back to the linked event's start_dt
- Recursion guards (_from_event_sync / _from_task_sync flags) prevent infinite loops
- Deleting an event clears the linked task's due_date
- Standalone (unlinked) entities are unaffected

These tests are written to pass AFTER the fix is applied; they will fail on
the current unfixed code.

Uses the ``isolated_db`` fixture from conftest (autouse) for per-test DB isolation.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_project(name: str = "Sync Test Project") -> int:
    """Create a default board + project and return the project id."""
    import desktop.database.boards as _boards
    import desktop.database.projects as _projects

    board = _boards.get_or_create_default_board()
    proj = _projects.create_project(name, board_id=board.id)
    return proj.id  # type: ignore[return-value]


def _make_calendar_id() -> int:
    """Return the default calendar id."""
    import desktop.database.calendars as _calendars

    return _calendars.get_default_calendar_id()


def _linked_pair(
    task_due: datetime,
    event_start: datetime,
    event_end: datetime,
) -> tuple[int, int]:
    """Create a task and a linked event; return (task_id, event_id)."""
    import desktop.database.events as _events
    import desktop.database.tasks as _tasks

    project_id = _make_project()
    cal_id = _make_calendar_id()

    task = _tasks.create_task(project_id, "Linked Task", due_date=task_due)
    assert task.id is not None

    event = _events.create_event(
        calendar_id=cal_id,
        title="Linked Event",
        start_dt=event_start,
        end_dt=event_end,
        linked_task_id=task.id,
    )
    assert event.id is not None

    return task.id, event.id


# ---------------------------------------------------------------------------
# 1. Event -> Task sync
# ---------------------------------------------------------------------------


class TestEventToTaskSync:
    """Updating event.start_dt propagates to task.due_date."""

    def test_update_event_syncs_due_date(self) -> None:
        """Moving an event's start_dt should update the linked task's due_date."""
        import desktop.database.events as _events
        import desktop.database.tasks as _tasks

        original = datetime(2026, 3, 15, 9, 0)
        original_end = datetime(2026, 3, 15, 10, 0)
        new_start = datetime(2026, 3, 17, 9, 0)
        new_end = datetime(2026, 3, 17, 10, 0)

        task_id, event_id = _linked_pair(original, original, original_end)

        _events.update_event(event_id, start_dt=new_start, end_dt=new_end)

        task = _tasks.get_task(task_id)
        assert task is not None
        assert task.due_date is not None
        assert task.due_date.date() == new_start.date(), (
            f"Expected due_date {new_start.date()}, got {task.due_date.date()}"
        )

    def test_update_event_preserves_time_component(self) -> None:
        """The synced due_date should carry the new start_dt's time, not the old one."""
        import desktop.database.events as _events
        import desktop.database.tasks as _tasks

        original = datetime(2026, 3, 15, 9, 0)
        original_end = datetime(2026, 3, 15, 10, 0)
        new_start = datetime(2026, 3, 20, 14, 30)
        new_end = datetime(2026, 3, 20, 15, 30)

        task_id, event_id = _linked_pair(original, original, original_end)

        _events.update_event(event_id, start_dt=new_start, end_dt=new_end)

        task = _tasks.get_task(task_id)
        assert task is not None
        assert task.due_date == new_start


# ---------------------------------------------------------------------------
# 2. Task -> Event sync
# ---------------------------------------------------------------------------


class TestTaskToEventSync:
    """Updating task.due_date propagates to event.start_dt."""

    def test_update_task_syncs_event_start(self) -> None:
        """Changing task due_date should update the linked event's start_dt."""
        import desktop.database.events as _events
        import desktop.database.tasks as _tasks

        original = datetime(2026, 3, 15, 9, 0)
        original_end = datetime(2026, 3, 15, 10, 0)
        new_due = datetime(2026, 4, 1, 9, 0)

        task_id, event_id = _linked_pair(original, original, original_end)

        _tasks.update_task(task_id, due_date=new_due)

        event = _events.get_event(event_id)
        assert event is not None
        assert event.start_dt is not None
        assert event.start_dt.date() == new_due.date(), (
            f"Expected event start {new_due.date()}, got {event.start_dt.date()}"
        )

    def test_update_task_preserves_event_duration(self) -> None:
        """After syncing, event.end_dt must preserve the original 1-hour duration."""
        import desktop.database.events as _events
        import desktop.database.tasks as _tasks

        original = datetime(2026, 3, 15, 9, 0)
        original_end = datetime(2026, 3, 15, 11, 0)  # 2-hour event
        new_due = datetime(2026, 4, 5, 14, 0)

        task_id, event_id = _linked_pair(original, original, original_end)

        _tasks.update_task(task_id, due_date=new_due)

        event = _events.get_event(event_id)
        assert event is not None
        assert event.start_dt is not None
        assert event.end_dt is not None

        duration = event.end_dt - event.start_dt
        assert duration == timedelta(hours=2), f"Expected 2-hour duration, got {duration}"

    def test_clear_task_due_date_unlinks_event(self) -> None:
        """Clearing task due_date (setting to None) must unlink the event.

        The events table has NOT NULL on start_dt/end_dt, so we cannot
        null those out. Instead, the event's linked_task_id is cleared,
        breaking the association while keeping the event structurally valid.
        """
        import desktop.database.events as _events
        import desktop.database.tasks as _tasks

        original = datetime(2026, 3, 15, 9, 0)
        original_end = datetime(2026, 3, 15, 10, 0)

        task_id, event_id = _linked_pair(original, original, original_end)

        # Confirm the event is linked before clearing
        event_before = _events.get_event(event_id)
        assert event_before is not None
        assert event_before.linked_task_id == task_id

        # Clear the task's due_date
        _tasks.update_task(task_id, due_date=None)

        # Task due_date should be cleared
        task_after = _tasks.get_task(task_id)
        assert task_after is not None
        assert task_after.due_date is None

        # Event should be unlinked but still exist with valid dates
        event_after = _events.get_event(event_id)
        assert event_after is not None
        assert event_after.linked_task_id is None, (
            f"Expected event to be unlinked (linked_task_id=None), "
            f"got linked_task_id={event_after.linked_task_id}"
        )
        assert event_after.start_dt == original, (
            "Event should retain its original start_dt after unlinking"
        )
        assert event_after.end_dt == original_end, (
            "Event should retain its original end_dt after unlinking"
        )


# ---------------------------------------------------------------------------
# 3. Recursion guard
# ---------------------------------------------------------------------------


class TestRecursionGuard:
    """Bidirectional sync must not recurse infinitely."""

    def test_update_event_no_recursion(self) -> None:
        """update_event on a linked event must complete without RecursionError."""
        import desktop.database.events as _events

        original = datetime(2026, 3, 15, 9, 0)
        _task_id, event_id = _linked_pair(
            original,
            original,
            datetime(2026, 3, 15, 10, 0),
        )

        new_start = datetime(2026, 3, 18, 9, 0)
        new_end = datetime(2026, 3, 18, 10, 0)

        # Must not raise RecursionError
        _events.update_event(event_id, start_dt=new_start, end_dt=new_end)

    def test_update_task_no_recursion(self) -> None:
        """update_task on a linked task must complete without RecursionError."""
        import desktop.database.tasks as _tasks

        original = datetime(2026, 3, 15, 9, 0)
        task_id, _event_id = _linked_pair(
            original,
            original,
            datetime(2026, 3, 15, 10, 0),
        )

        new_due = datetime(2026, 3, 22, 9, 0)

        # Must not raise RecursionError
        _tasks.update_task(task_id, due_date=new_due)


# ---------------------------------------------------------------------------
# 4. Delete event clears task due_date
# ---------------------------------------------------------------------------


class TestDeleteEventClearsTaskDueDate:
    """Deleting an event that is linked to a task must null out task.due_date."""

    def test_delete_event_clears_due_date(self) -> None:
        """After deleting the linked event, task.due_date should be None."""
        import desktop.database.events as _events
        import desktop.database.tasks as _tasks

        original = datetime(2026, 3, 15, 9, 0)
        task_id, event_id = _linked_pair(
            original,
            original,
            datetime(2026, 3, 15, 10, 0),
        )

        # Confirm due_date is set before delete
        task_before = _tasks.get_task(task_id)
        assert task_before is not None
        assert task_before.due_date is not None

        _events.delete_event(event_id)

        task_after = _tasks.get_task(task_id)
        assert task_after is not None
        assert task_after.due_date is None, (
            f"Expected due_date=None after event deletion, got {task_after.due_date}"
        )

    def test_delete_event_task_otherwise_intact(self) -> None:
        """Deleting the event should not affect other task fields."""
        import desktop.database.events as _events
        import desktop.database.tasks as _tasks

        original = datetime(2026, 3, 15, 9, 0)
        project_id = _make_project("Intact Test Project")
        cal_id = _make_calendar_id()

        task = _tasks.create_task(
            project_id,
            "Important Task",
            priority=2,
            due_date=original,
            description="Do not lose me",
        )
        assert task.id is not None

        event = _events.create_event(
            calendar_id=cal_id,
            title="Linked Event",
            start_dt=original,
            end_dt=datetime(2026, 3, 15, 10, 0),
            linked_task_id=task.id,
        )
        assert event.id is not None

        _events.delete_event(event.id)

        task_after = _tasks.get_task(task.id)
        assert task_after is not None
        assert task_after.title == "Important Task"
        assert task_after.priority == 2
        assert task_after.description == "Do not lose me"
        assert task_after.due_date is None


# ---------------------------------------------------------------------------
# 5. No sync when unlinked
# ---------------------------------------------------------------------------


class TestNoSyncWhenUnlinked:
    """Standalone events and tasks must not crash or affect other records."""

    def test_standalone_event_update_no_crash(self) -> None:
        """Updating a non-linked event's start_dt must not raise."""
        import desktop.database.events as _events

        cal_id = _make_calendar_id()
        event = _events.create_event(
            calendar_id=cal_id,
            title="Standalone Event",
            start_dt=datetime(2026, 3, 15, 9, 0),
            end_dt=datetime(2026, 3, 15, 10, 0),
            # no linked_task_id
        )
        assert event.id is not None

        # Must not raise
        _events.update_event(
            event.id,
            start_dt=datetime(2026, 3, 20, 9, 0),
            end_dt=datetime(2026, 3, 20, 10, 0),
        )

        updated = _events.get_event(event.id)
        assert updated is not None
        assert updated.start_dt == datetime(2026, 3, 20, 9, 0)

    def test_standalone_task_update_no_crash(self) -> None:
        """Updating a task that has no linked event must not raise."""
        import desktop.database.tasks as _tasks

        project_id = _make_project("Standalone Task Project")
        task = _tasks.create_task(
            project_id,
            "Standalone Task",
            due_date=datetime(2026, 3, 15, 9, 0),
        )
        assert task.id is not None

        new_due = datetime(2026, 4, 1, 9, 0)

        # Must not raise
        _tasks.update_task(task.id, due_date=new_due)

        updated = _tasks.get_task(task.id)
        assert updated is not None
        assert updated.due_date == new_due


# ---------------------------------------------------------------------------
# 6. Ghost problem regression (Bug 164 root cause)
# ---------------------------------------------------------------------------


class TestGhostProblemRegression:
    """Regression test for the original ghost-task symptom.

    Before the fix: moving an event to a new date left the task's due_date on
    the old date, causing the task to reappear as a ghost on the old date slot
    in the timeline view.
    """

    def test_move_event_ghost_eliminated(self) -> None:
        """After moving the event, the task must NOT still show on the old date."""
        import desktop.database.events as _events
        import desktop.database.tasks as _tasks

        march_15 = datetime(2026, 3, 15, 9, 0)
        march_15_end = datetime(2026, 3, 15, 10, 0)
        march_17 = datetime(2026, 3, 17, 9, 0)
        march_17_end = datetime(2026, 3, 17, 10, 0)

        task_id, event_id = _linked_pair(march_15, march_15, march_15_end)

        # Confirm initial state
        task_before = _tasks.get_task(task_id)
        assert task_before is not None
        assert task_before.due_date is not None
        assert task_before.due_date.date() == march_15.date()

        # Move the event to March 17
        _events.update_event(event_id, start_dt=march_17, end_dt=march_17_end)

        # Task must track the new date, not the old one
        task_after = _tasks.get_task(task_id)
        assert task_after is not None
        assert task_after.due_date is not None
        assert task_after.due_date.date() == march_17.date(), (
            f"Ghost detected: due_date is still {task_after.due_date.date()}, "
            f"expected {march_17.date()}"
        )

    @pytest.mark.parametrize("days_offset", [1, 3, 7, 14])
    def test_move_event_various_offsets(self, days_offset: int) -> None:
        """Parameterized: moving event by N days should shift due_date by N days."""
        import desktop.database.events as _events
        import desktop.database.tasks as _tasks

        base = datetime(2026, 3, 10, 9, 0)
        base_end = datetime(2026, 3, 10, 10, 0)
        new_start = base + timedelta(days=days_offset)
        new_end = base_end + timedelta(days=days_offset)

        task_id, event_id = _linked_pair(base, base, base_end)

        _events.update_event(event_id, start_dt=new_start, end_dt=new_end)

        task = _tasks.get_task(task_id)
        assert task is not None
        assert task.due_date is not None
        assert task.due_date.date() == new_start.date(), (
            f"offset={days_offset}: expected {new_start.date()}, got {task.due_date.date()}"
        )


# ---------------------------------------------------------------------------
# 7. Sync flag isolation
# ---------------------------------------------------------------------------


class TestSyncFlagIsolation:
    """_from_event_sync and _from_task_sync flags prevent the reverse sync."""

    def test_update_task_from_event_sync_no_reverse(self) -> None:
        """update_task(..., _from_event_sync=True) must NOT sync back to the event."""
        import desktop.database.events as _events
        import desktop.database.tasks as _tasks

        original = datetime(2026, 3, 15, 9, 0)
        original_end = datetime(2026, 3, 15, 10, 0)
        new_due = datetime(2026, 4, 10, 9, 0)

        task_id, event_id = _linked_pair(original, original, original_end)

        # Simulate the "already called from event sync" path
        _tasks.update_task(task_id, due_date=new_due, _from_event_sync=True)

        # Task due_date must update
        task = _tasks.get_task(task_id)
        assert task is not None
        assert task.due_date is not None
        assert task.due_date.date() == new_due.date()

        # Event start_dt must remain on the original date (no reverse sync triggered)
        event = _events.get_event(event_id)
        assert event is not None
        assert event.start_dt is not None
        assert event.start_dt.date() == original.date(), (
            f"Reverse sync occurred: event.start_dt became {event.start_dt.date()}, "
            f"expected it to stay {original.date()}"
        )

    def test_update_event_from_task_sync_no_reverse(self) -> None:
        """update_event(..., _from_task_sync=True) must NOT sync back to the task."""
        import desktop.database.events as _events
        import desktop.database.tasks as _tasks

        original = datetime(2026, 3, 15, 9, 0)
        original_end = datetime(2026, 3, 15, 10, 0)
        new_start = datetime(2026, 4, 20, 9, 0)
        new_end = datetime(2026, 4, 20, 10, 0)

        task_id, event_id = _linked_pair(original, original, original_end)

        # Simulate the "already called from task sync" path
        _events.update_event(event_id, start_dt=new_start, end_dt=new_end, _from_task_sync=True)

        # Event start_dt must update
        event = _events.get_event(event_id)
        assert event is not None
        assert event.start_dt is not None
        assert event.start_dt.date() == new_start.date()

        # Task due_date must remain on the original date (no reverse sync triggered)
        task = _tasks.get_task(task_id)
        assert task is not None
        assert task.due_date is not None
        assert task.due_date.date() == original.date(), (
            f"Reverse sync occurred: task.due_date became {task.due_date.date()}, "
            f"expected it to stay {original.date()}"
        )

    def test_sync_flag_does_not_suppress_db_write(self) -> None:
        """The _from_*_sync flag suppresses reverse sync only, not the write itself."""
        import desktop.database.tasks as _tasks

        project_id = _make_project("Flag DB Write Project")
        task = _tasks.create_task(project_id, "Flag Test Task")
        assert task.id is not None

        new_due = datetime(2026, 5, 1, 8, 0)
        _tasks.update_task(task.id, due_date=new_due, _from_event_sync=True)

        reloaded = _tasks.get_task(task.id)
        assert reloaded is not None
        assert reloaded.due_date == new_due
