"""
tasks.py — Task CRUD operations.

Ported from Setado's DatabaseManager.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..models import Task
from .connection import get_connection
from .prerequisites import (
    add_prerequisite,
    cleanup_prerequisites_for_deleted_task,
    get_prerequisite_ids,
    get_unmet_prerequisites,
)
from .tags import add_tag_to_task, get_tags_for_task_ids, get_task_tags

logger = logging.getLogger(__name__)


def create_task(
    project_id: int,
    title: str,
    priority: int = 0,
    due_date: datetime | None = None,
    description: str = "",
) -> Task:
    now = datetime.now().isoformat()
    due_str = due_date.isoformat() if due_date else None
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (project_id, title, description, priority, due_date, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, title, description, priority, due_str, now),
        )
        conn.commit()
    return Task(
        id=cur.lastrowid,
        project_id=project_id,
        title=title,
        description=description,
        priority=priority,
        due_date=due_date,
        created_at=datetime.fromisoformat(now),
    )


def create_task_with_relations(
    *,
    tags: list[str] | None = None,
    prerequisites: list[int] | None = None,
    **task_kwargs,
) -> Task:
    """Create a task and attach tags and prerequisites in one call."""
    task = create_task(**task_kwargs)
    for tag_name in tags or []:
        add_tag_to_task(task.id, tag_name)
    for prereq_id in prerequisites or []:
        add_prerequisite(task.id, prereq_id)
    task.tags = list(tags or [])
    task.prerequisites = list(prerequisites or [])
    return task


def get_task(task_id: int) -> Task | None:
    """Fetch a single task by ID, or None if not found."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    return Task.from_row(
        row, tags=get_task_tags(row["id"]), prerequisites=get_prerequisite_ids(row["id"])
    )


def _with_batch_tags(rows: list) -> list[Task]:
    """Build Task objects with batch-loaded tags (avoids N+1 queries)."""
    if not rows:
        return []
    tags_map = get_tags_for_task_ids([r["id"] for r in rows])
    return [Task.from_row(r, tags=tags_map.get(r["id"], [])) for r in rows]


def get_tasks(project_id: int, include_deleted: bool = False) -> list[Task]:
    with get_connection() as conn:
        if include_deleted:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE project_id = ? ORDER BY priority, created_at",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE project_id = ? AND is_deleted = 0 "
                "ORDER BY priority, created_at",
                (project_id,),
            ).fetchall()
    return _with_batch_tags(rows)


def get_tasks_by_board(board_id: int, include_deleted: bool = False) -> list[Task]:
    """Fetch all tasks for all projects within a board."""
    with get_connection() as conn:
        if include_deleted:
            rows = conn.execute(
                "SELECT t.* FROM tasks t "
                "JOIN projects p ON t.project_id = p.id "
                "WHERE p.board_id = ? "
                "ORDER BY t.priority, t.created_at",
                (board_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT t.* FROM tasks t "
                "JOIN projects p ON t.project_id = p.id "
                "WHERE p.board_id = ? AND t.is_deleted = 0 "
                "ORDER BY t.priority, t.created_at",
                (board_id,),
            ).fetchall()
    return _with_batch_tags(rows)


def get_tasks_with_due_dates(
    project_id: int | None = None,
    start_dt: datetime | None = None,
    end_dt: datetime | None = None,
) -> list[Task]:
    """Active tasks with due dates, nearest first.

    Optional *start_dt*/*end_dt* push date filtering into SQL so callers
    don't need to fetch the full table and filter in Python.
    """
    with get_connection() as conn:
        if project_id is None:
            q = (
                "SELECT t.* FROM tasks t JOIN projects p ON t.project_id = p.id "
                "WHERE t.due_date IS NOT NULL AND t.is_completed = 0 "
                "AND t.is_deleted = 0 AND p.is_archived = 0"
            )
            params: list = []
        else:
            q = (
                "SELECT * FROM tasks WHERE project_id = ? AND due_date IS NOT NULL "
                "AND is_completed = 0 AND is_deleted = 0"
            )
            params = [project_id]

        if start_dt is not None:
            q += " AND due_date >= ?"
            params.append(start_dt.isoformat())
        if end_dt is not None:
            q += " AND due_date < ?"
            params.append(end_dt.isoformat())

        q += " ORDER BY due_date ASC"
        rows = conn.execute(q, params).fetchall()
    return _with_batch_tags(rows)


def get_completed_tasks(project_id: int | None = None) -> list[Task]:
    """Completed tasks, most recent first."""
    with get_connection() as conn:
        if project_id is None:
            rows = conn.execute(
                "SELECT t.* FROM tasks t JOIN projects p ON t.project_id = p.id "
                "WHERE t.is_completed = 1 AND t.is_deleted = 0 AND p.is_archived = 0 "
                "ORDER BY t.completed_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE project_id = ? AND is_completed = 1 "
                "AND is_deleted = 0 ORDER BY completed_at DESC",
                (project_id,),
            ).fetchall()
    return _with_batch_tags(rows)


def complete_task(task_id: int) -> list[Task]:
    """Mark task as completed. Returns list of unmet prerequisites (empty = success).

    If the returned list is non-empty, the task was NOT completed.
    """
    blockers = get_unmet_prerequisites(task_id)
    if blockers:
        return blockers
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET is_completed = 1, completed_at = ? WHERE id = ?",
            (now, task_id),
        )
        conn.commit()
    return []


def uncomplete_task(task_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET is_completed = 0, completed_at = NULL WHERE id = ?",
            (task_id,),
        )
        conn.commit()


def delete_task(task_id: int) -> None:
    """Soft delete — also removes all prerequisite relationships atomically."""
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET is_deleted = 1, deleted_at = ? WHERE id = ?",
            (now, task_id),
        )
        conn.commit()
    cleanup_prerequisites_for_deleted_task(task_id)


def get_starred_tasks() -> list[Task]:
    """Active starred tasks from non-archived projects."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT t.* FROM tasks t JOIN projects p ON t.project_id = p.id "
            "WHERE t.is_starred = 1 AND t.is_completed = 0 "
            "AND t.is_deleted = 0 AND p.is_archived = 0 "
            "ORDER BY t.priority, t.created_at"
        ).fetchall()
    return _with_batch_tags(rows)


def get_unscheduled_tasks_for_starred_projects() -> list[Task]:
    """Unscheduled (no due_date) tasks from starred, non-archived projects."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT t.* FROM tasks t JOIN projects p ON t.project_id = p.id "
            "WHERE p.is_starred = 1 AND t.due_date IS NULL "
            "AND t.is_completed = 0 AND t.is_deleted = 0 "
            "AND p.is_archived = 0 "
            "ORDER BY t.project_id, t.priority, t.created_at"
        ).fetchall()
    return _with_batch_tags(rows)


def get_unscheduled_starred_tasks() -> list[Task]:
    """Unscheduled (no due_date) individually starred tasks."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT t.* FROM tasks t JOIN projects p ON t.project_id = p.id "
            "WHERE t.is_starred = 1 AND t.due_date IS NULL "
            "AND t.is_completed = 0 AND t.is_deleted = 0 "
            "AND p.is_archived = 0 "
            "ORDER BY t.priority, t.created_at"
        ).fetchall()
    return _with_batch_tags(rows)


def update_task(task_id: int, *, _from_event_sync: bool = False, **kwargs) -> None:
    """Update allowed fields on a task.

    When _from_event_sync is True, the cross-sync to the linked event is skipped
    (prevents infinite recursion).
    """
    allowed = {
        "title",
        "description",
        "priority",
        "due_date",
        "is_completed",
        "is_deleted",
        "project_id",
        "is_starred",
    }
    updates, values = [], []
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        updates.append(f"{k} = ?")
        if k == "due_date" and v is not None and isinstance(v, datetime):
            values.append(v.isoformat())
        else:
            values.append(v)
    if not updates:
        return
    values.append(task_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()

    # Sync due_date change to linked event's start_dt (preserving duration)
    if not _from_event_sync and "due_date" in kwargs:
        from .events import get_event_for_task, update_event

        linked_event = get_event_for_task(task_id)
        if linked_event is not None:
            new_due = kwargs["due_date"]
            if new_due is None:
                # Clearing the task's due date — unlink the event so
                # it keeps valid start/end dates but is no longer tied
                # to this task (mirrors delete_event which clears
                # due_date when the event is removed).
                update_event(
                    linked_event.id,  # type: ignore[arg-type]
                    linked_task_id=None,
                    _from_task_sync=True,
                )
                return
            if isinstance(new_due, str):
                new_due = datetime.fromisoformat(new_due)
            if linked_event.start_dt and linked_event.end_dt:
                duration = linked_event.end_dt - linked_event.start_dt
            else:
                duration = timedelta(hours=1)
            new_end = new_due + duration
            update_event(
                linked_event.id,  # type: ignore[arg-type]
                start_dt=new_due,
                end_dt=new_end,
                _from_task_sync=True,
            )
