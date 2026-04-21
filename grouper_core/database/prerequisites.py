"""
prerequisites.py — Task prerequisite CRUD operations.

A prerequisite relationship means task B must be completed before task A.
Stored in `task_prerequisites(task_id, prerequisite_task_id)`.
"""

from __future__ import annotations

import logging

from ..models import Task
from .connection import get_connection
from .tags import get_tags_for_task_ids

logger = logging.getLogger(__name__)


def get_prerequisite_ids(task_id: int) -> list[int]:
    """Return IDs of prerequisite tasks (excludes deleted tasks)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT tp.prerequisite_task_id FROM task_prerequisites tp "
            "JOIN tasks t ON tp.prerequisite_task_id = t.id "
            "WHERE tp.task_id = ? AND t.is_deleted = 0",
            (task_id,),
        ).fetchall()
    return [r["prerequisite_task_id"] for r in rows]


def get_prerequisite_tasks(task_id: int) -> list[Task]:
    """Return full Task objects for all (non-deleted) prerequisites."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT t.* FROM tasks t "
            "JOIN task_prerequisites tp ON t.id = tp.prerequisite_task_id "
            "WHERE tp.task_id = ? AND t.is_deleted = 0 "
            "ORDER BY t.title",
            (task_id,),
        ).fetchall()
    if not rows:
        return []
    task_ids = [r["id"] for r in rows]
    tags_by_id = get_tags_for_task_ids(task_ids)
    return [Task.from_row(r, tags=tags_by_id.get(r["id"], [])) for r in rows]


def get_prerequisite_tasks_for_ids(task_ids: list[int]) -> dict[int, list[Task]]:
    """Batch-load prerequisite Task objects for multiple tasks in a single query.

    Returns a dict mapping each task_id to its list of prerequisite Task objects.
    Missing task_ids get an empty list.
    """
    if not task_ids:
        return {}
    result: dict[int, list[Task]] = {tid: [] for tid in task_ids}
    placeholders = ",".join("?" for _ in task_ids)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT tp.task_id AS _requesting_task_id, t.* FROM tasks t "
            "JOIN task_prerequisites tp ON t.id = tp.prerequisite_task_id "
            f"WHERE tp.task_id IN ({placeholders}) AND t.is_deleted = 0 "
            "ORDER BY t.title",
            task_ids,
        ).fetchall()
    if not rows:
        return result
    prereq_task_ids = [r["id"] for r in rows]
    tags_by_id = get_tags_for_task_ids(prereq_task_ids)
    for r in rows:
        requesting_id: int = r["_requesting_task_id"]
        task = Task.from_row(r, tags=tags_by_id.get(r["id"], []))
        result[requesting_id].append(task)
    return result


def get_unmet_prerequisites(task_id: int) -> list[Task]:
    """Return prerequisite tasks that are not yet completed (and not deleted)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT t.* FROM tasks t "
            "JOIN task_prerequisites tp ON t.id = tp.prerequisite_task_id "
            "WHERE tp.task_id = ? AND t.is_completed = 0 AND t.is_deleted = 0 "
            "ORDER BY t.title",
            (task_id,),
        ).fetchall()
    if not rows:
        return []
    task_ids = [r["id"] for r in rows]
    tags_by_id = get_tags_for_task_ids(task_ids)
    return [Task.from_row(r, tags=tags_by_id.get(r["id"], [])) for r in rows]


def _would_create_cycle(task_id: int, prerequisite_task_id: int) -> bool:
    """Return True if adding prerequisite_task_id as a prereq of task_id would create a cycle."""
    with get_connection() as conn:
        row = conn.execute(
            "WITH RECURSIVE ancestors(id) AS ("
            "  SELECT ? "
            "  UNION "
            "  SELECT tp.prerequisite_task_id "
            "  FROM task_prerequisites tp "
            "  JOIN ancestors a ON tp.task_id = a.id"
            ") "
            "SELECT 1 FROM ancestors WHERE id = ? LIMIT 1",
            (prerequisite_task_id, task_id),
        ).fetchone()
    return row is not None


def add_prerequisite(task_id: int, prerequisite_task_id: int) -> None:
    """Add a prerequisite relationship. Silently ignores duplicates, self-refs, and cycles."""
    if task_id == prerequisite_task_id:
        return
    if _would_create_cycle(task_id, prerequisite_task_id):
        return
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO task_prerequisites (task_id, prerequisite_task_id) "
            "VALUES (?, ?)",
            (task_id, prerequisite_task_id),
        )
        conn.commit()


def remove_prerequisite(task_id: int, prerequisite_task_id: int) -> None:
    """Remove a prerequisite relationship."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM task_prerequisites WHERE task_id = ? AND prerequisite_task_id = ?",
            (task_id, prerequisite_task_id),
        )
        conn.commit()


def cleanup_prerequisites_for_deleted_task(deleted_task_id: int) -> None:
    """Remove all prerequisite relationships involving a deleted task.

    Called when a task is soft-deleted so that dependent tasks are unblocked
    and the deleted task's own prerequisites are cleaned up.
    """
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM task_prerequisites WHERE prerequisite_task_id = ?",
            (deleted_task_id,),
        )
        conn.execute(
            "DELETE FROM task_prerequisites WHERE task_id = ?",
            (deleted_task_id,),
        )
        conn.commit()
