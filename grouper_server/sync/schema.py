"""
schema.py — Sync metadata: which tables to sync, FK relationships, and
dependency ordering for safe insert/delete.

This is the single source of truth for sync-aware table knowledge.
"""

from __future__ import annotations

# ── Tables that participate in sync ─────────────────────────────────────
# Excludes internal bookkeeping: schema_version, _migrations,
# sync_changelog, sync_state, sync_peers.

SYNCED_TABLES: list[str] = [
    "activities",
    "boards",
    "projects",
    "sessions",
    "pause_events",
    "tasks",
    "tags",
    "groups",
    "activity_groups",
    "project_tags",
    "task_tags",
    "activity_tags",
    "task_prerequisites",
    "task_links",
    "calendars",
    "events",
    "event_exceptions",
    "settings",
]

# ── Foreign-key map ─────────────────────────────────────────────────────
# {table: {fk_column: referenced_table}}
# Used to resolve integer FKs → UUIDs for transit and back on arrival.

FK_MAP: dict[str, dict[str, str]] = {
    "projects": {"board_id": "boards"},
    "sessions": {"task_id": "tasks"},
    "pause_events": {"session_id": "sessions"},
    "tasks": {"project_id": "projects"},
    "project_tags": {"project_id": "projects", "tag_id": "tags"},
    "task_tags": {"task_id": "tasks", "tag_id": "tags"},
    "activity_tags": {"activity_id": "activities", "tag_id": "tags"},
    "task_prerequisites": {"task_id": "tasks", "prerequisite_task_id": "tasks"},
    "task_links": {"task_id": "tasks"},
    "activity_groups": {"activity_id": "activities", "group_id": "groups"},
    "events": {
        "calendar_id": "calendars",
        "linked_activity_id": "activities",
        "linked_task_id": "tasks",
    },
    "event_exceptions": {
        "parent_event_id": "events",
        "override_event_id": "events",
    },
}

# ── Insert order (topological: parents before children) ─────────────────
# Delete order is the reverse.

INSERT_ORDER: list[str] = [
    "boards",
    "activities",
    "tags",
    "groups",
    "calendars",
    "settings",
    "projects",
    "tasks",
    "sessions",
    "pause_events",
    "events",
    "event_exceptions",
    "project_tags",
    "task_tags",
    "activity_tags",
    "activity_groups",
    "task_prerequisites",
    "task_links",
]

DELETE_ORDER: list[str] = list(reversed(INSERT_ORDER))

# ── Tables that use a composite PK (no single 'id' column) ─────────────
# For these, the UUID is the only stable row identity across devices.

COMPOSITE_PK_TABLES: set[str] = {
    "project_tags",
    "task_tags",
    "activity_tags",
    "task_prerequisites",
}

# ── Tables where 'key' is the PK instead of 'id' ───────────────────────

KEY_PK_TABLES: set[str] = {
    "settings",
}

SYNC_VERSION_COLUMNS: tuple[str, str] = ("sync_version", "sync_updated_by")

NATURAL_KEY_POLICIES: dict[str, tuple[str, str]] = {
    "tags": ("merge", "name"),
    "groups": ("merge", "name"),
    "activities": ("reject", "name"),
    "boards": ("reject", "name"),
    "projects": ("reject", "name"),
}
