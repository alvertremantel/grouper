"""
projects.py — Project CRUD operations.

Projects are task-management containers.  They hold tasks but NOT sessions.
Sessions belong to Activities (see activities.py).
"""

from __future__ import annotations

import logging

from ..models import Project
from .connection import get_connection, set_archived
from .tags import add_tag_to_project, get_project_tags, get_tags_for_project_ids

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Create / Read
# ---------------------------------------------------------------------------


def create_project(
    name: str,
    board_id: int,
    description: str | None = None,
    tags: list[str] | None = None,
) -> Project:
    """Create a new project.

    Raises:
        sqlite3.IntegrityError: if the name already exists.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO projects (name, board_id, description) VALUES (?, ?, ?)",
            (name, board_id, description),
        )
        conn.commit()
        pid = cur.lastrowid

    if tags:
        for t in tags:
            add_tag_to_project(pid, t)

    return Project(
        id=pid,
        board_id=board_id,
        name=name,
        description=description,
        tags=tags or [],
    )


def get_project(name: str) -> Project | None:
    """Fetch a project by name (case-sensitive)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, board_id, name, description, is_archived, is_starred, "
            "created_at, archived_at FROM projects WHERE name = ?",
            (name,),
        ).fetchone()
    if row is None:
        return None
    return Project.from_row(row, tags=get_project_tags(row["id"]))


def get_project_by_id(project_id: int) -> Project | None:
    """Fetch a project by id."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, board_id, name, description, is_archived, is_starred, "
            "created_at, archived_at FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if row is None:
        return None
    return Project.from_row(row, tags=get_project_tags(row["id"]))


def get_or_create_project(name: str, board_id: int = 1) -> Project:
    p = get_project(name)
    if p is not None:
        if p.board_id != board_id:
            logger.debug(
                "get_or_create_project(%r): existing project (id=%s) is on "
                "board_id=%s, not requested board_id=%s",
                name,
                p.id,
                p.board_id,
                board_id,
            )
        return p
    return create_project(name, board_id=board_id)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def _with_batch_tags(projects: list[Project]) -> list[Project]:
    ids = [p.id for p in projects if p.id is not None]
    tag_map = get_tags_for_project_ids(ids)
    for p in projects:
        p.tags = tag_map.get(p.id, [])
    return projects


def list_projects(
    board_id: int | None = None,
    tag: str | None = None,
    include_archived: bool = False,
) -> list[Project]:
    """Return projects with optional filters."""
    with get_connection() as conn:
        q = (
            "SELECT id, board_id, name, description, "
            "is_archived, is_starred, created_at, archived_at FROM projects"
        )
        params: list = []
        conds: list[str] = []

        if board_id is not None:
            conds.append("board_id = ?")
            params.append(board_id)
        if not include_archived:
            conds.append("is_archived = 0")
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY name COLLATE NOCASE"

        rows = conn.execute(q, params).fetchall()

    projects = _with_batch_tags([Project.from_row(r) for r in rows])

    if tag:
        if tag == "Untagged":
            projects = [p for p in projects if not p.tags]
        else:
            tag_lower = tag.lower()
            projects = [p for p in projects if tag_lower in [t.lower() for t in p.tags]]

    return projects


# ---------------------------------------------------------------------------
# Update / Delete
# ---------------------------------------------------------------------------


def get_starred_projects() -> list[Project]:
    """Return non-archived projects that are starred."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, board_id, name, description, "
            "is_archived, is_starred, created_at, archived_at FROM projects "
            "WHERE is_starred = 1 AND is_archived = 0 "
            "ORDER BY name COLLATE NOCASE"
        ).fetchall()

    return _with_batch_tags([Project.from_row(r) for r in rows])


def update_project(project_id: int, **kwargs) -> None:
    """Update allowed project fields (name, description)."""
    allowed = {"name", "description", "is_starred"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = [*updates.values(), project_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE projects SET {cols} WHERE id = ?", vals)
        conn.commit()


def rename_project(old_name: str, new_name: str) -> Project | None:
    p = get_project(old_name)
    if p is None:
        return None
    with get_connection() as conn:
        conn.execute("UPDATE projects SET name = ? WHERE id = ?", (new_name, p.id))
        conn.commit()
    p.name = new_name
    return p


def archive_project(project_id: int) -> None:
    set_archived("projects", project_id, True)


def unarchive_project(project_id: int) -> None:
    set_archived("projects", project_id, False)


def delete_project(project_name: str) -> bool:
    p = get_project(project_name)
    if p is None:
        return False
    return delete_project_by_id(p.id)


def delete_project_by_id(project_id: int) -> bool:
    """Delete a project by its ID. Returns True if a row was deleted."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
    return cur.rowcount > 0
