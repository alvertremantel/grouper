"""
activities.py — Activity CRUD operations.

Activities are the time-tracking entities (renamed from "timed projects").
They can have sessions but never tasks.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

from ..models import Activity, Group
from .connection import get_connection, set_archived
from .tags import get_activity_tags, get_tags_for_activity_ids

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Create / Read
# ---------------------------------------------------------------------------


def create_activity(
    name: str,
    description: str | None = None,
    is_background: bool = False,
) -> Activity:
    """Create a new activity.

    If an activity with the same name exists but was soft-deleted,
    it will be restored (undeleted) with the new description/background settings.

    Raises:
        sqlite3.IntegrityError: if the name already exists for an active (non-deleted) activity.
    """
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id, name, description, is_background, is_archived, is_deleted, "
            "created_at, archived_at, deleted_at FROM activities WHERE name = ?",
            (name,),
        ).fetchone()

        if existing is not None:
            if existing["is_deleted"]:
                conn.execute(
                    "UPDATE activities SET is_deleted = 0, deleted_at = NULL, "
                    "description = ?, is_background = ? WHERE id = ?",
                    (description, 1 if is_background else 0, existing["id"]),
                )
                conn.commit()
                if is_background:
                    add_activity_group(existing["id"], BACKGROUND_GROUP_NAME)
                return Activity(
                    id=existing["id"],
                    name=name,
                    description=description,
                    is_background=is_background,
                    is_archived=bool(existing["is_archived"]),
                    is_deleted=False,
                    created_at=existing["created_at"],
                    archived_at=existing["archived_at"],
                    deleted_at=None,
                )
            else:
                raise sqlite3.IntegrityError(f"activity with name '{name}' already exists")

        cur = conn.execute(
            "INSERT INTO activities (name, description, is_background) VALUES (?, ?, ?)",
            (name, description, 1 if is_background else 0),
        )
        conn.commit()
        aid = cur.lastrowid

    if is_background:
        add_activity_group(aid, BACKGROUND_GROUP_NAME)

    return Activity(
        id=aid,
        name=name,
        description=description,
        is_background=is_background,
    )


def get_activity(name: str) -> Activity | None:
    """Fetch an activity by name (case-sensitive)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, description, is_background, is_archived, is_deleted, "
            "created_at, archived_at, deleted_at FROM activities WHERE name = ?",
            (name,),
        ).fetchone()
    if row is None:
        return None
    return Activity.from_row(
        row, groups=get_activity_groups(row["id"]), tags=get_activity_tags(row["id"])
    )


def get_activity_by_id(activity_id: int) -> Activity | None:
    """Fetch an activity by id."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, description, is_background, is_archived, is_deleted, "
            "created_at, archived_at, deleted_at FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()
    if row is None:
        return None
    return Activity.from_row(
        row, groups=get_activity_groups(activity_id), tags=get_activity_tags(activity_id)
    )


def get_or_create_activity(name: str) -> Activity:
    a = get_activity(name)
    return a if a else create_activity(name)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def list_activities(
    is_background: bool | None = None,
    include_archived: bool = False,
    include_deleted: bool = False,
) -> list[Activity]:
    """Return activities with optional filters."""
    with get_connection() as conn:
        q = (
            "SELECT id, name, description, is_background, "
            "is_archived, is_deleted, created_at, archived_at, deleted_at FROM activities"
        )
        params: list = []
        conds: list[str] = []

        if not include_archived:
            conds.append("is_archived = 0")
        if not include_deleted:
            conds.append("is_deleted = 0")
        if is_background is not None:
            conds.append("is_background = ?")
            params.append(1 if is_background else 0)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY is_background ASC, name COLLATE NOCASE"

        rows = conn.execute(q, params).fetchall()

    activities = [Activity.from_row(row) for row in rows]
    return _with_batch_relations(activities)


# ---------------------------------------------------------------------------
# Update / Delete
# ---------------------------------------------------------------------------


def update_activity(activity_id: int, **kwargs) -> None:
    """Update allowed activity fields (name, description)."""
    allowed = {"name", "description"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = [*updates.values(), activity_id]
    with get_connection() as conn:
        cur = conn.execute(f"UPDATE activities SET {cols} WHERE id = ?", vals)
        conn.commit()
        if cur.rowcount == 0:
            logger.warning("update_activity: no rows affected for activity_id=%d", activity_id)


def archive_activity(activity_id: int) -> None:
    set_archived("activities", activity_id, True)


def unarchive_activity(activity_id: int) -> None:
    set_archived("activities", activity_id, False)


def delete_activity(activity_name: str, delete_sessions: bool = False) -> bool:
    a = get_activity(activity_name)
    if a is None:
        return False
    with get_connection() as conn:
        if delete_sessions:
            conn.execute("DELETE FROM sessions WHERE activity_name = ?", (activity_name,))
        conn.execute("DELETE FROM activities WHERE id = ?", (a.id,))
        conn.commit()
    return True


def soft_delete_activity(activity_id: int) -> None:
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE activities SET is_deleted = 1, deleted_at = ? WHERE id = ?",
            (now, activity_id),
        )
        conn.commit()


def rename_activity_by_id(activity_id: int, new_name: str) -> Activity | None:
    a = get_activity_by_id(activity_id)
    if a is None:
        return None
    old_name = a.name
    try:
        with get_connection() as conn:
            conn.execute("UPDATE activities SET name = ? WHERE id = ?", (new_name, activity_id))
            conn.execute(
                "UPDATE sessions SET activity_name = ? WHERE activity_name = ?",
                (new_name, old_name),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        logger.debug(
            "Cannot rename activity %d to '%s': name already exists",
            activity_id,
            new_name,
        )
        return None
    a.name = new_name
    return a


# ---------------------------------------------------------------------------
# Group CRUD (first-class groups table)
# ---------------------------------------------------------------------------


def create_group(name: str) -> Group:
    """Create a new group. Raises IntegrityError if name already exists."""
    name = name.strip()
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO groups (name) VALUES (?)", (name,))
        conn.commit()
        row = conn.execute(
            "SELECT id, name, created_at FROM groups WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return Group.from_row(row)


def get_or_create_group(name: str) -> Group:
    """Return existing group by name, or create it."""
    name = name.strip()
    g = get_group_by_name(name)
    if g is not None:
        return g
    return create_group(name)


def get_group_by_name(name: str) -> Group | None:
    """Look up a group by name (case-insensitive)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, created_at FROM groups WHERE name = ? COLLATE NOCASE",
            (name.strip(),),
        ).fetchone()
    return Group.from_row(row) if row else None


def get_group_by_id(group_id: int) -> Group | None:
    """Look up a group by id."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, created_at FROM groups WHERE id = ?",
            (group_id,),
        ).fetchone()
    return Group.from_row(row) if row else None


def rename_group(group_id: int, new_name: str) -> bool:
    """Rename a group. Returns True if renamed, False if not found or name conflict."""
    new_name = new_name.strip()
    if not new_name:
        return False
    try:
        with get_connection() as conn:
            cur = conn.execute("UPDATE groups SET name = ? WHERE id = ?", (new_name, group_id))
            conn.commit()
        return cur.rowcount > 0
    except sqlite3.IntegrityError:
        return False


def delete_group(group_id: int) -> bool:
    """Delete a group. CASCADE removes all activity_groups memberships."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        conn.commit()
    return cur.rowcount > 0


def list_all_groups() -> list[Group]:
    """Return all groups, ordered alphabetically."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, created_at FROM groups ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return [Group.from_row(r) for r in rows]


def get_ungrouped_activities() -> list[Activity]:
    """Return non-deleted, non-archived activities with zero group memberships."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT a.id, a.name, a.description, a.is_background,
                      a.is_archived, a.is_deleted, a.created_at,
                      a.archived_at, a.deleted_at
               FROM activities a
               LEFT JOIN activity_groups ag ON a.id = ag.activity_id
               WHERE a.is_deleted = 0 AND a.is_archived = 0
                 AND ag.id IS NULL
               ORDER BY a.is_background ASC, a.name COLLATE NOCASE"""
        ).fetchall()
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    tags_map = get_tags_for_activity_ids(ids)
    return [Activity.from_row(row, groups=[], tags=tags_map.get(row["id"], [])) for row in rows]


BACKGROUND_GROUP_NAME = "Background"


def ensure_background_group() -> None:
    """Ensure a 'Background' group exists and all background activities belong to it.

    Idempotent — safe to call on every startup.
    """
    get_or_create_group(BACKGROUND_GROUP_NAME)
    bg_activities = list_activities(is_background=True)
    for act in bg_activities:
        if BACKGROUND_GROUP_NAME not in act.groups:
            add_activity_group(act.id, BACKGROUND_GROUP_NAME)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Activity-group membership (backward-compatible signatures)
# ---------------------------------------------------------------------------


def add_activity_group(activity_id: int, group_name: str) -> bool:
    """Add a group to an activity. Returns True if added, False if already exists."""
    group_name = group_name.strip()
    if not group_name:
        return False
    try:
        group = get_or_create_group(group_name)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO activity_groups (activity_id, group_id) VALUES (?, ?)",
                (activity_id, group.id),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def remove_activity_group(activity_id: int, group_name: str) -> bool:
    """Remove a group from an activity. Returns True if removed."""
    with get_connection() as conn:
        cur = conn.execute(
            """DELETE FROM activity_groups
               WHERE activity_id = ?
                 AND group_id = (SELECT id FROM groups WHERE name = ? COLLATE NOCASE)""",
            (activity_id, group_name),
        )
        conn.commit()
        return cur.rowcount > 0


def get_activity_groups(activity_id: int) -> list[str]:
    """Get all group names for an activity."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT g.name
               FROM activity_groups ag
               JOIN groups g ON ag.group_id = g.id
               WHERE ag.activity_id = ?
               ORDER BY g.name COLLATE NOCASE""",
            (activity_id,),
        ).fetchall()
    return [row["name"] for row in rows]


def get_groups_for_activity_ids(activity_ids: list[int]) -> dict[int, list[str]]:
    """Batch-load group names for multiple activities in a single query."""
    if not activity_ids:
        return {}
    result: dict[int, list[str]] = {aid: [] for aid in activity_ids}
    placeholders = ",".join("?" for _ in activity_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"""SELECT ag.activity_id, g.name
                FROM activity_groups ag
                JOIN groups g ON ag.group_id = g.id
                WHERE ag.activity_id IN ({placeholders})
                ORDER BY g.name COLLATE NOCASE""",
            activity_ids,
        ).fetchall()
    for r in rows:
        result[r["activity_id"]].append(r["name"])
    return result


def _with_batch_relations(activities: list[Activity]) -> list[Activity]:
    if not activities:
        return activities
    ids = [a.id for a in activities if a.id is not None]
    tags_map = get_tags_for_activity_ids(ids)
    groups_map = get_groups_for_activity_ids(ids)
    for a in activities:
        a.tags = tags_map.get(a.id, [])
        a.groups = groups_map.get(a.id, [])
    return activities


def get_activities_by_group(group_name: str) -> list[Activity]:
    """Get all active activities belonging to a group (by name)."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT a.id, a.name, a.description, a.is_background, a.is_archived, a.is_deleted,
                      a.created_at, a.archived_at, a.deleted_at
               FROM activities a
               JOIN activity_groups ag ON a.id = ag.activity_id
               JOIN groups g ON ag.group_id = g.id
               WHERE g.name = ? COLLATE NOCASE
                 AND a.is_deleted = 0 AND a.is_archived = 0
               ORDER BY a.is_background ASC, a.name COLLATE NOCASE""",
            (group_name,),
        ).fetchall()

    activities = [Activity.from_row(row) for row in rows]
    return _with_batch_relations(activities)


def get_all_groups() -> list[str]:
    """Get group names that have at least one active activity, sorted alphabetically."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT DISTINCT g.name
               FROM groups g
               JOIN activity_groups ag ON g.id = ag.group_id
               JOIN activities a ON ag.activity_id = a.id
               WHERE a.is_deleted = 0 AND a.is_archived = 0
               ORDER BY g.name COLLATE NOCASE"""
        ).fetchall()
    return [row["name"] for row in rows]


def set_activity_groups(activity_id: int, groups: list[str]) -> None:
    """Replace all groups for an activity with the given list (max 3)."""
    resolved: list[Group] = []
    for group_name in groups[:3]:
        group_name = group_name.strip()
        if group_name:
            resolved.append(get_or_create_group(group_name))
    with get_connection() as conn:
        conn.execute("DELETE FROM activity_groups WHERE activity_id = ?", (activity_id,))
        for group in resolved:
            conn.execute(
                "INSERT INTO activity_groups (activity_id, group_id) VALUES (?, ?)",
                (activity_id, group.id),
            )
        conn.commit()
