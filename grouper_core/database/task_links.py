"""
task_links.py — CRUD functions for task hyperlinks and file links.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..models import TaskLink
from .connection import get_connection

logger = logging.getLogger(__name__)


def detect_link_type(url: str) -> str:
    """Infer whether a URL string is a web URL or a local file path."""
    stripped = url.strip()
    if stripped.startswith("file:///"):
        return "file"
    if len(stripped) >= 2 and stripped[0].isalpha() and stripped[1] == ":":
        # Windows drive letter, e.g. C:\...
        return "file"
    if stripped.startswith("\\\\"):
        # UNC path, e.g. \\server\share
        return "file"
    if stripped.startswith("/") or stripped.startswith("~"):
        return "file"
    return "url"


def get_links_for_task(task_id: int) -> list[TaskLink]:
    """Return all links for a given task, ordered by creation time."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM task_links WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
    return [TaskLink.from_row(r) for r in rows]


def get_links_for_task_ids(task_ids: list[int]) -> dict[int, list[TaskLink]]:
    """Batch-load links for multiple tasks in a single query.

    Returns a dict mapping each task_id to its list of TaskLink objects,
    ordered by creation time.  Missing task_ids get an empty list.
    """
    if not task_ids:
        return {}
    result: dict[int, list[TaskLink]] = {tid: [] for tid in task_ids}
    placeholders = ",".join("?" for _ in task_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM task_links WHERE task_id IN ({placeholders}) ORDER BY created_at ASC",
            task_ids,
        ).fetchall()
    for r in rows:
        link = TaskLink.from_row(r)
        result[link.task_id].append(link)
    return result


def add_link(
    task_id: int,
    url: str,
    label: str | None = None,
    link_type: str | None = None,
) -> TaskLink:
    """Insert a new link record and return the created TaskLink."""
    url = url.strip()
    resolved_type = link_type if link_type is not None else detect_link_type(url)
    label_val = label.strip() if label and label.strip() else None
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO task_links (task_id, url, label, link_type, created_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, url, label_val, resolved_type, now),
        )
        conn.commit()
    return TaskLink(
        id=cur.lastrowid,
        task_id=task_id,
        label=label_val,
        url=url,
        link_type=resolved_type,
        created_at=now,
    )


def delete_link(link_id: int) -> None:
    """Permanently delete a link record."""
    with get_connection() as conn:
        conn.execute("DELETE FROM task_links WHERE id = ?", (link_id,))
        conn.commit()


def update_link(
    link_id: int,
    url: str | None = None,
    label: str | None = None,
) -> None:
    """Update url and/or label of an existing link."""
    updates: dict[str, object] = {}
    if url is not None:
        updates["url"] = url.strip()
        updates["link_type"] = detect_link_type(url)
    if label is not None:
        updates["label"] = label.strip() or None
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = [*updates.values(), link_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE task_links SET {set_clause} WHERE id = ?", values)
        conn.commit()
