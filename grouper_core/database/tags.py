"""
tags.py — Tag CRUD and entity-tag association operations (projects, tasks, activities).
"""

from __future__ import annotations

import logging
import sqlite3

from ..models import Tag
from .connection import get_connection

logger = logging.getLogger(__name__)


def create_tag(name: str) -> Tag:
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name.strip(),))
        conn.commit()
    return Tag(id=cur.lastrowid, name=name.strip())


def get_tag(name: str) -> Tag | None:
    """Case-insensitive lookup."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, created_at FROM tags WHERE name = ? COLLATE NOCASE",
            (name,),
        ).fetchone()
    if row is None:
        return None
    return Tag.from_row(row)


def get_or_create_tag(name: str) -> Tag:
    t = get_tag(name)
    return t if t else create_tag(name)


def list_tags() -> list[Tag]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, created_at FROM tags ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return [Tag.from_row(r) for r in rows]


# -- Private helpers -----------------------------------------------------------

_VALID_JUNCTION_TABLES = {"activity_tags", "project_tags", "task_tags"}
_VALID_ENTITY_COLUMNS = {"activity_id", "project_id", "task_id"}


def _validate_tag_params(junction_table: str, entity_column: str) -> None:
    """Raise ValueError if junction_table or entity_column is not in the allowlist."""
    if junction_table not in _VALID_JUNCTION_TABLES:
        raise ValueError(f"Invalid junction table: {junction_table!r}")
    if entity_column not in _VALID_ENTITY_COLUMNS:
        raise ValueError(f"Invalid entity column: {entity_column!r}")


def _get_entity_tags(junction_table: str, entity_column: str, entity_id: int) -> list[str]:
    _validate_tag_params(junction_table, entity_column)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT t.name FROM tags t "
            f'JOIN "{junction_table}" jt ON t.id = jt.tag_id '
            f'WHERE jt."{entity_column}" = ? ORDER BY t.name COLLATE NOCASE',
            (entity_id,),
        ).fetchall()
    return [r["name"] for r in rows]


def _add_entity_tag(junction_table: str, entity_column: str, entity_id: int, tag_name: str) -> bool:
    _validate_tag_params(junction_table, entity_column)
    tag = get_or_create_tag(tag_name)
    with get_connection() as conn:
        try:
            conn.execute(
                f'INSERT INTO "{junction_table}" ("{entity_column}", tag_id) VALUES (?, ?)',
                (entity_id, tag.id),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def _remove_entity_tag(
    junction_table: str, entity_column: str, entity_id: int, tag_name: str
) -> bool:
    _validate_tag_params(junction_table, entity_column)
    tag = get_tag(tag_name)
    if tag is None:
        return False
    with get_connection() as conn:
        cur = conn.execute(
            f'DELETE FROM "{junction_table}" WHERE "{entity_column}" = ? AND tag_id = ?',
            (entity_id, tag.id),
        )
        conn.commit()
        return cur.rowcount > 0


def _get_tags_for_entity_ids(
    junction_table: str, entity_column: str, entity_ids: list[int]
) -> dict[int, list[str]]:
    _validate_tag_params(junction_table, entity_column)
    if not entity_ids:
        return {}
    result: dict[int, list[str]] = {eid: [] for eid in entity_ids}
    placeholders = ",".join("?" for _ in entity_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f'SELECT jt."{entity_column}", t.name FROM tags t '
            f'JOIN "{junction_table}" jt ON t.id = jt.tag_id '
            f'WHERE jt."{entity_column}" IN ({placeholders}) '
            f"ORDER BY t.name COLLATE NOCASE",
            entity_ids,
        ).fetchall()
    for r in rows:
        result[r[entity_column]].append(r["name"])
    return result


# -- Project-tag associations -------------------------------------------------


def get_project_tags(project_id: int) -> list[str]:
    return _get_entity_tags("project_tags", "project_id", project_id)


def add_tag_to_project(project_id: int, tag_name: str) -> bool:
    """Returns True if the tag was newly added."""
    return _add_entity_tag("project_tags", "project_id", project_id, tag_name)


def remove_tag_from_project(project_id: int, tag_name: str) -> bool:
    return _remove_entity_tag("project_tags", "project_id", project_id, tag_name)


def get_tags_for_project_ids(project_ids: list[int]) -> dict[int, list[str]]:
    """Batch-load tags for multiple projects in a single query."""
    return _get_tags_for_entity_ids("project_tags", "project_id", project_ids)


# -- Task-tag associations ----------------------------------------------------


def get_tags_for_task_ids(task_ids: list[int]) -> dict[int, list[str]]:
    """Batch-load tags for multiple tasks in a single query."""
    return _get_tags_for_entity_ids("task_tags", "task_id", task_ids)


def get_task_tags(task_id: int) -> list[str]:
    return _get_entity_tags("task_tags", "task_id", task_id)


def add_tag_to_task(task_id: int, tag_name: str) -> bool:
    """Returns True if the tag was newly added."""
    return _add_entity_tag("task_tags", "task_id", task_id, tag_name)


def remove_tag_from_task(task_id: int, tag_name: str) -> bool:
    return _remove_entity_tag("task_tags", "task_id", task_id, tag_name)


# -- Activity-tag associations ------------------------------------------------


def get_tags_for_activity_ids(activity_ids: list[int]) -> dict[int, list[str]]:
    """Batch-load tags for multiple activities in a single query."""
    return _get_tags_for_entity_ids("activity_tags", "activity_id", activity_ids)


def get_activity_tags(activity_id: int) -> list[str]:
    return _get_entity_tags("activity_tags", "activity_id", activity_id)


def add_tag_to_activity(activity_id: int, tag_name: str) -> bool:
    """Returns True if the tag was newly added."""
    return _add_entity_tag("activity_tags", "activity_id", activity_id, tag_name)


def remove_tag_from_activity(activity_id: int, tag_name: str) -> bool:
    return _remove_entity_tag("activity_tags", "activity_id", activity_id, tag_name)
