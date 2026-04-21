"""operations.py — Shared business-logic helpers.

Used by grouper_cli to avoid duplicating task update operations
(tag sync, prerequisite sync).
"""

from __future__ import annotations

import grouper_core.database.prerequisites as _prereqs
import grouper_core.database.tags as _tags

__all__ = [
    "sync_task_prerequisites",
    "sync_task_tags",
]


def sync_task_tags(task_id: int, desired_tags: list[str]) -> None:
    existing = _tags.get_task_tags(task_id)
    for old_tag in existing:
        _tags.remove_tag_from_task(task_id, old_tag)
    for new_tag in desired_tags:
        _tags.add_tag_to_task(task_id, new_tag)


def sync_task_prerequisites(task_id: int, desired_prerequisite_ids: list[int]) -> None:
    existing = _prereqs.get_prerequisite_ids(task_id)
    for old_pid in existing:
        _prereqs.remove_prerequisite(task_id, old_pid)
    for new_pid in desired_prerequisite_ids:
        _prereqs.add_prerequisite(task_id, new_pid)
