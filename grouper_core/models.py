"""
models.py — Data models for Grouper

Separate dataclass models for Activities (time tracking) and Projects (task management).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol, runtime_checkable

__all__ = [
    "Activity",
    "Board",
    "Calendar",
    "DBRow",
    "Event",
    "Group",
    "PauseEvent",
    "Project",
    "Session",
    "Tag",
    "Task",
    "TaskLink",
    "parse_duration_string",
]


# ---------------------------------------------------------------------------
# Row → model helpers
# ---------------------------------------------------------------------------


@runtime_checkable
class DBRow(Protocol):
    def __getitem__(self, key: str) -> Any: ...
    def keys(self) -> list[str]: ...


def _parse_dt(value: str | datetime | None) -> datetime | None:
    """Parse an ISO-formatted string to datetime, pass through datetime/None."""
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def _coerce_dt_attrs(obj: Any, attrs: tuple[str, ...]) -> None:
    for attr in attrs:
        val = getattr(obj, attr)
        if isinstance(val, str):
            setattr(obj, attr, _parse_dt(val))


@dataclass
class Tag:
    """A label that can be applied to projects, tasks, or activities."""

    id: int | None = None
    name: str = ""
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        self.name = self.name.strip()

    @classmethod
    def from_row(cls, row: DBRow) -> Tag:
        return cls(
            id=row["id"],
            name=row["name"],
            created_at=_parse_dt(row["created_at"]),
        )


@dataclass
class Group:
    """A named group for organizing activities in the quadrant grid."""

    id: int | None = None
    name: str = ""
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        self.name = self.name.strip()

    @classmethod
    def from_row(cls, row: DBRow) -> Group:
        return cls(
            id=row["id"],
            name=row["name"],
            created_at=_parse_dt(row["created_at"]),
        )


@dataclass
class PauseEvent:
    """A single pause or resume event within a session.

    When a session is paused and resumed multiple times, each event is
    recorded so the session can later be split into discrete active segments.
    """

    id: int | None = None
    session_id: int = 0
    event_type: Literal["pause", "resume"] = "pause"
    event_time: datetime | None = None

    def __post_init__(self) -> None:
        _coerce_dt_attrs(self, ("event_time",))

    @classmethod
    def from_row(cls, row: DBRow) -> PauseEvent:
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            event_type=row["event_type"],
            event_time=_parse_dt(row["event_time"]),
        )


@dataclass
class Activity:
    """A named activity for time tracking.

    Activities are things you track time against (e.g. "Programming",
    "Reading", "Exercise").  They own sessions but never tasks.

    Background activities skip priority/tag features (e.g. "Music").
    Archived activities are hidden from default views but kept for history.
    Deleted activities are soft-deleted and hidden.
    Activities can belong to up to 3 groups for organization in the time tracker.
    """

    id: int | None = None
    name: str = ""
    description: str | None = None
    is_background: bool = False
    is_archived: bool = False
    is_deleted: bool = False
    groups: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    archived_at: datetime | None = None
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now()

    @classmethod
    def from_row(
        cls,
        row: DBRow,
        *,
        groups: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Activity:
        return cls(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            is_background=bool(row["is_background"]),
            is_archived=bool(row["is_archived"]),
            is_deleted=bool(row["is_deleted"]),
            groups=groups if groups is not None else [],
            tags=tags if tags is not None else [],
            created_at=_parse_dt(row["created_at"]),
            archived_at=_parse_dt(row["archived_at"]),
            deleted_at=_parse_dt(row["deleted_at"]),
        )


@dataclass
class Board:
    """A high-level container that owns projects."""

    id: int | None = None
    name: str = ""
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now()

    @classmethod
    def from_row(cls, row: DBRow) -> Board:
        return cls(
            id=row["id"],
            name=row["name"],
            created_at=_parse_dt(row["created_at"]),
        )


@dataclass
class Project:
    """A named project that owns tasks.

    Projects are containers for task management (e.g. a specific
    deliverable, a course, a goal).  They own tasks but never sessions.

    Archived projects are hidden from default views but kept for history.
    """

    id: int | None = None
    board_id: int = 0
    name: str = ""
    description: str | None = None
    is_archived: bool = False
    is_starred: bool = False
    tags: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    archived_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now()

    @classmethod
    def from_row(cls, row: DBRow, *, tags: list[str] | None = None) -> Project:
        return cls(
            id=row["id"],
            board_id=row["board_id"],
            name=row["name"],
            description=row["description"],
            is_archived=bool(row["is_archived"]),
            is_starred=bool(row["is_starred"]),
            tags=tags if tags is not None else [],
            created_at=_parse_dt(row["created_at"]),
            archived_at=_parse_dt(row["archived_at"]),
        )


@dataclass
class Session:
    """A tracked time block belonging to a project.

    Sessions have a start time and optionally an end time (None while
    still running).  They can be paused/resumed.  On stop, a session
    with pause events is split into multiple completed segments.

    Sessions may optionally be attributed to a specific task via task_id.
    """

    id: int | None = None
    activity_name: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    notes: str = ""
    is_paused: bool = False
    paused_seconds: int = 0
    pause_started_at: datetime | None = None
    task_id: int | None = None  # optional attribution

    def __post_init__(self) -> None:
        _coerce_dt_attrs(self, ("start_time", "end_time", "pause_started_at"))

    @classmethod
    def from_row(cls, row: DBRow) -> Session:
        return cls(
            id=row["id"],
            activity_name=row["activity_name"],
            start_time=_parse_dt(row["start_time"]),
            end_time=_parse_dt(row["end_time"]),
            notes=row["notes"] or "",
            is_paused=bool(row["is_paused"]),
            paused_seconds=row["paused_seconds"] or 0,
            pause_started_at=_parse_dt(row["pause_started_at"]),
            task_id=row["task_id"],
        )

    # -- computed properties -------------------------------------------------

    @property
    def is_active(self) -> bool:
        """True while the session is running (started but not stopped)."""
        return self.start_time is not None and self.end_time is None

    @property
    def duration(self) -> timedelta | None:
        """Elapsed time excluding paused time."""
        if self.start_time is None:
            return None
        end = self.end_time or datetime.now()
        total = end - self.start_time

        paused = timedelta(seconds=self.paused_seconds)
        if self.is_paused and self.pause_started_at:
            paused += datetime.now() - self.pause_started_at

        return max(total - paused, timedelta(0))

    @property
    def duration_seconds(self) -> int:
        d = self.duration
        return int(d.total_seconds()) if d else 0

    def format_duration(self) -> str:
        """Human-readable string like '1h 23m 45s'."""
        d = self.duration
        if d is None:
            return "0h 00m 00s"
        total = int(d.total_seconds())
        h, remainder = divmod(total, 3600)
        m, s = divmod(remainder, 60)
        return f"{h}h {m:02d}m {s:02d}s"


@dataclass
class Task:
    """A to-do item belonging to a project.

    Tasks support priorities, due dates, completion tracking and soft
    deletion (the record is kept but hidden from active views).

    Note: ``prerequisites`` is only populated when loaded via ``get_task()``
    (single-task fetch).  List functions (``get_tasks``, ``get_tasks_by_board``,
    etc.) populate ``tags`` but leave ``prerequisites`` as an empty list for
    performance reasons.
    """

    id: int | None = None
    project_id: int = 0
    title: str = ""
    description: str = ""
    priority: int = 0  # 0 = none, 1 = highest, 4 = lowest
    due_date: datetime | None = None
    is_completed: bool = False
    is_deleted: bool = False
    is_starred: bool = False
    tags: list[str] = field(default_factory=list)
    prerequisites: list[int] = field(default_factory=list)
    created_at: datetime | None = None
    completed_at: datetime | None = None
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        _coerce_dt_attrs(self, ("due_date", "created_at", "completed_at", "deleted_at"))
        self.priority = max(0, min(4, self.priority))
        if self.created_at is None:
            self.created_at = datetime.now()

    @classmethod
    def from_row(
        cls,
        row: DBRow,
        *,
        tags: list[str] | None = None,
        prerequisites: list[int] | None = None,
    ) -> Task:
        return cls(
            id=row["id"],
            project_id=row["project_id"],
            title=row["title"],
            description=row["description"] if "description" in row.keys() else "",  # noqa: SIM118 — sqlite3.Row requires .keys() to check column names
            priority=row["priority"],
            due_date=_parse_dt(row["due_date"]),
            is_completed=bool(row["is_completed"]),
            is_deleted=bool(row["is_deleted"]),
            is_starred=bool(row["is_starred"]),
            tags=tags if tags is not None else [],
            prerequisites=prerequisites if prerequisites is not None else [],
            created_at=_parse_dt(row["created_at"]),
            completed_at=_parse_dt(row["completed_at"]),
            deleted_at=_parse_dt(row["deleted_at"]),
        )


@dataclass
class TaskLink:
    """A hyperlink or file path attached to a task."""

    id: int
    task_id: int
    label: str | None
    url: str
    link_type: Literal["url", "file"]
    created_at: str

    @classmethod
    def from_row(cls, row: DBRow) -> TaskLink:
        return cls(
            id=row["id"],
            task_id=row["task_id"],
            label=row["label"],
            url=row["url"],
            link_type=row["link_type"],
            created_at=row["created_at"],
        )


@dataclass
class Calendar:
    """A named container for events.

    Two system calendars exist by default (type='system:tasks' and
    'system:sessions') and cannot be deleted.  User calendars can be created,
    archived, and assigned a weekly time budget.
    """

    id: int | None = None
    name: str = ""
    color: str = "#7aa2f7"
    type: str = "user"  # 'user' | 'system:tasks' | 'system:sessions'
    is_visible: bool = True
    weekly_budget_hours: float | None = None
    is_archived: bool = False
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now()

    @classmethod
    def from_row(cls, row: DBRow) -> Calendar:
        return cls(
            id=row["id"],
            name=row["name"],
            color=row["color"],
            type=row["type"],
            is_visible=bool(row["is_visible"]),
            weekly_budget_hours=row["weekly_budget_hours"],
            is_archived=bool(row["is_archived"]),
            created_at=_parse_dt(row["created_at"]),
        )


@dataclass
class Event:
    """A scheduled calendar event.

    Recurring events store an RRULE string (RFC 5545); instances are expanded
    at query time by python-dateutil.  Individual occurrences can be
    cancelled or overridden via event_exceptions rows.
    """

    id: int | None = None
    calendar_id: int = 0
    title: str = ""
    description: str = ""
    location: str = ""
    start_dt: datetime | None = None
    end_dt: datetime | None = None
    all_day: bool = False
    color: str | None = None
    recurrence_rule: str = ""
    recurrence_end_dt: datetime | None = None
    linked_activity_id: int | None = None
    linked_task_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        _coerce_dt_attrs(
            self, ("start_dt", "end_dt", "recurrence_end_dt", "created_at", "updated_at")
        )

    @classmethod
    def from_row(cls, row: DBRow) -> Event:
        return cls(
            id=row["id"],
            calendar_id=row["calendar_id"],
            title=row["title"],
            description=row["description"],
            location=row["location"],
            start_dt=_parse_dt(row["start_dt"]),
            end_dt=_parse_dt(row["end_dt"]),
            all_day=bool(row["all_day"]),
            color=row["color"],
            recurrence_rule=row["recurrence_rule"] or "",
            recurrence_end_dt=_parse_dt(row["recurrence_end_dt"]),
            linked_activity_id=row["linked_activity_id"],
            linked_task_id=row["linked_task_id"],
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_duration_string(text: str) -> timedelta:
    """Parse human-friendly duration strings into timedelta.

    Supports: "1h30m", "45m", "2h", "1h 30m 10s", "90" (bare number = minutes).
    """
    import re

    text = text.strip().lower()

    hours = minutes = seconds = 0
    parts = re.findall(r"(\d+)\s*(h|m|s)", text)
    if parts:
        for value, unit in parts:
            n = int(value)
            if unit == "h":
                hours = n
            elif unit == "m":
                minutes = n
            elif unit == "s":
                seconds = n
    else:
        # Bare number -> minutes
        try:
            minutes = int(text)
        except ValueError as err:
            raise ValueError(f"Cannot parse duration: {text!r}") from err

    return timedelta(hours=hours, minutes=minutes, seconds=seconds)
