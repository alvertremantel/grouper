"""
view_models.py — Typed data containers for each Grouper view.

Each dataclass holds the pre-fetched data a view needs to render, so the
fetch and render steps can be cleanly separated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ...models import Board, Event, Project, Session, Task


@dataclass
class DashboardData:
    """Data for the Dashboard view."""

    active_sessions: list[Session] = field(default_factory=list)
    upcoming_tasks: list[Task] = field(default_factory=list)


@dataclass
class HistoryData:
    """Data for the History view."""

    completed_tasks: list[Task] = field(default_factory=list)
    sessions: list[Session] = field(default_factory=list)


@dataclass
class TaskListData:
    """Data for the flat Task List view."""

    boards: list[Board] = field(default_factory=list)
    active_board_id: int | None = None
    tasks: list[Task] = field(default_factory=list)


@dataclass
class BoardData:
    """Data for the Kanban Task Board view."""

    boards: list[Board] = field(default_factory=list)
    active_board_id: int | None = None
    projects: list[Project] = field(default_factory=list)
    # Maps project_id → list of tasks for that project
    tasks: dict[int, list[Task]] = field(default_factory=dict)


@dataclass
class SummaryData:
    """Data for the analytical Summary view."""

    start: datetime = field(default_factory=datetime.now)
    end: datetime = field(default_factory=datetime.now)
    # Maps activity name → total seconds tracked in range
    activity_totals: dict[str, float] = field(default_factory=dict)
    # Maps day string (YYYY-MM-DD) → total seconds across all activities
    day_totals: dict[str, float] = field(default_factory=dict)
    # Count of tasks created in range
    tasks_created: int = 0
    # Count of tasks completed in range
    tasks_completed: int = 0
    # Calendar events in range
    events: list[Event] = field(default_factory=list)
    # Maps group name → total seconds tracked in range
    group_breakdown: dict[str, float] = field(default_factory=dict)
