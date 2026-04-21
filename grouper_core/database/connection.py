"""
connection.py — Database connection management, schema creation, and migrations.

Part of grouper_core — zero PySide6 dependencies.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import threading
from collections.abc import Callable
from contextlib import contextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def register_sqlite_functions(conn: sqlite3.Connection) -> None:
    """Register SQLite functions used by sync triggers."""

    def _row_value(row: sqlite3.Row | tuple | None, key: str, index: int) -> Any:
        if row is None:
            return None
        if isinstance(row, sqlite3.Row):
            return row[key]
        return row[index]

    def current_device_id() -> str:
        row = conn.execute("SELECT device_id FROM sync_state WHERE id = 1").fetchone()
        value = _row_value(row, "device_id", 0)
        return str(value or "")

    def next_sync_version() -> int:
        conn.execute(
            "INSERT OR IGNORE INTO sync_state (id, device_id, syncing, logical_clock) "
            "VALUES (1, lower(hex(randomblob(16))), 0, 0)"
        )
        conn.execute("UPDATE sync_state SET logical_clock = logical_clock + 1 WHERE id = 1")
        row = conn.execute("SELECT logical_clock FROM sync_state WHERE id = 1").fetchone()
        value = _row_value(row, "logical_clock", 0)
        return int(value or 0)

    conn.create_function("current_device_id", 0, current_device_id)
    conn.create_function("next_sync_version", 0, next_sync_version)


# ---------------------------------------------------------------------------
# Data directory
# ---------------------------------------------------------------------------

DEFAULT_DATA_DIR = Path.home() / ".grouper"
CONFIG_DIR = Path.home() / ".grouper"
CONFIG_FILE = CONFIG_DIR / "db_path.txt"

DATA_DIR: Path = DEFAULT_DATA_DIR
DATABASE_PATH: Path = DEFAULT_DATA_DIR / "grouper.db"


def _load_data_directory() -> Path:
    """Read the configured data directory, falling back to the default."""
    env_override = os.environ.get("GROUPER_DATA_DIR")
    if env_override:
        p = Path(env_override)
        p.mkdir(parents=True, exist_ok=True)
        return p
    if CONFIG_FILE.exists():
        try:
            p = Path(CONFIG_FILE.read_text().strip())
            if p.exists() and p.is_dir():
                return p
        except Exception:
            logger.warning(
                "Failed to read data directory config from %s", CONFIG_FILE, exc_info=True
            )
    return DEFAULT_DATA_DIR


def _save_data_directory(path: Path) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(str(path))


def _init_paths() -> None:
    global DATA_DIR, DATABASE_PATH
    DATA_DIR = _load_data_directory()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH = DATA_DIR / "grouper.db"


_init_paths()


def get_data_directory() -> Path:
    return DATA_DIR


def get_database_path() -> Path:
    return DATABASE_PATH


def set_data_directory(new_path: Path, copy_existing: bool = False) -> bool:
    """Move the data directory.  Optionally copies the existing DB."""
    global DATA_DIR, DATABASE_PATH
    try:
        new_path = Path(new_path)
        new_path.mkdir(parents=True, exist_ok=True)
        new_db = new_path / "grouper.db"

        if copy_existing and DATABASE_PATH.exists():
            shutil.copy2(DATABASE_PATH, new_db)

        DATA_DIR = new_path
        DATABASE_PATH = new_db
        _save_data_directory(new_path)
        init_database()
        return True
    except Exception:
        logger.warning("Failed to set data directory to %s", new_path, exc_info=True)
        return False


def backup_database(
    backup_dir: Path | None = None,
    filename: str | None = None,
) -> bool:
    """Create a timestamped copy of the database."""
    try:
        dest = Path(backup_dir) if backup_dir else DATA_DIR / "backups"
        dest.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = filename or f"grouper_backup_{ts}.db"
        if DATABASE_PATH.exists():
            shutil.copy2(DATABASE_PATH, dest / name)
            return True
        return False
    except Exception:
        logger.warning("Database backup failed", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Data version counter — incremented on every write, used by UI views to
# skip redundant refreshes when data hasn't changed.
# ---------------------------------------------------------------------------

_data_version: int = 0
_version_lock = threading.Lock()


_data_changed_callbacks: list[Callable[[], None]] = []


def register_data_changed_callback(fn: Callable[[], None]) -> None:
    """Register a callback to be invoked after every data-version bump."""
    _data_changed_callbacks.append(fn)


def unregister_data_changed_callback(fn: Callable[[], None]) -> None:
    """Remove a previously registered data-change callback."""
    with suppress(ValueError):
        _data_changed_callbacks.remove(fn)


_ARCHIVABLE_TABLES = {"activities", "projects"}


def set_archived(table: str, entity_id: int, archived: bool) -> None:
    """Set or clear the is_archived flag and archived_at timestamp."""
    if table not in _ARCHIVABLE_TABLES:
        raise ValueError(f"Cannot archive table {table!r}")
    with get_connection() as conn:
        if archived:
            now = datetime.now().isoformat()
            conn.execute(
                f'UPDATE "{table}" SET is_archived = 1, archived_at = ? WHERE id = ?',
                (now, entity_id),
            )
        else:
            conn.execute(
                f'UPDATE "{table}" SET is_archived = 0, archived_at = NULL WHERE id = ?',
                (entity_id,),
            )
        conn.commit()


def bump_version() -> None:
    """Increment the data version after a DB write."""
    global _data_version
    with _version_lock:
        _data_version += 1
    for cb in _data_changed_callbacks:
        cb()


def get_version() -> int:
    """Return the current data version."""
    with _version_lock:
        return _data_version


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


class _VersionedConnection:
    """Thin wrapper around sqlite3.Connection that bumps the data version
    on every commit, so UI views can skip redundant refreshes."""

    __slots__ = ("_conn",)

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def raw_connection(self) -> sqlite3.Connection:
        """Expose the underlying sqlite3 connection for operations that need it directly."""
        return self._conn

    def commit(self) -> None:
        self._conn.commit()
        bump_version()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


@contextmanager
def get_connection():
    """Context manager yielding a sqlite3 connection with Row factory.

    The returned wrapper automatically bumps the data version counter on
    every ``commit()`` call, so UI code can detect stale data cheaply.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    register_sqlite_functions(conn)
    try:
        yield _VersionedConnection(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema version helpers
# ---------------------------------------------------------------------------


def _get_schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        return row["version"] if row else 0
    except sqlite3.OperationalError:
        return 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        )
    """)
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))


# ---------------------------------------------------------------------------
# Init + migrations
# ---------------------------------------------------------------------------

_INITIAL_SCHEMA = """
-- Activities (time tracking entities)
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    is_background INTEGER DEFAULT 0,
    is_archived INTEGER DEFAULT 0,
    is_deleted INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    archived_at TEXT,
    deleted_at TEXT,
    uuid TEXT DEFAULT (lower(hex(randomblob(16))))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_activities_uuid ON activities(uuid);

-- Boards (top-level containers for projects)
CREATE TABLE IF NOT EXISTS boards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT DEFAULT (lower(hex(randomblob(16))))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_boards_uuid ON boards(uuid);

-- Projects (task management containers)
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    is_archived INTEGER DEFAULT 0,
    is_starred INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    archived_at TEXT,
    uuid TEXT DEFAULT (lower(hex(randomblob(16)))),
    FOREIGN KEY (board_id) REFERENCES boards(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_uuid ON projects(uuid);
CREATE INDEX IF NOT EXISTS idx_projects_board ON projects(board_id);

-- Time tracking sessions (belong to activities)
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_name TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    notes TEXT DEFAULT '',
    is_paused INTEGER DEFAULT 0,
    paused_seconds INTEGER DEFAULT 0,
    pause_started_at TEXT,
    task_id INTEGER,
    uuid TEXT DEFAULT (lower(hex(randomblob(16)))),
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_activity ON sessions(activity_name);
CREATE INDEX IF NOT EXISTS idx_sessions_start    ON sessions(start_time);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_uuid ON sessions(uuid);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(end_time) WHERE end_time IS NULL;

-- Pause / resume events
CREATE TABLE IF NOT EXISTS pause_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_time TEXT NOT NULL,
    uuid TEXT DEFAULT (lower(hex(randomblob(16)))),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pause_session ON pause_events(session_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pause_events_uuid ON pause_events(uuid);

-- Tasks (belong to projects)
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    priority INTEGER DEFAULT 0,
    due_date TEXT,
    is_completed INTEGER DEFAULT 0,
    is_deleted INTEGER DEFAULT 0,
    is_starred INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    completed_at TEXT,
    deleted_at TEXT,
    uuid TEXT DEFAULT (lower(hex(randomblob(16)))),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_uuid ON tasks(uuid);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);

-- Tags + junction table (for projects)
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    uuid TEXT DEFAULT (lower(hex(randomblob(16))))
);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_uuid ON tags(uuid);

CREATE TABLE IF NOT EXISTS project_tags (
    project_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    uuid TEXT DEFAULT (lower(hex(randomblob(16)))),
    PRIMARY KEY (project_id, tag_id),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_tags_uuid ON project_tags(uuid);

CREATE TABLE IF NOT EXISTS task_tags (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    uuid TEXT DEFAULT (lower(hex(randomblob(16)))),
    PRIMARY KEY (task_id, tag_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_task_tags_uuid ON task_tags(uuid);

CREATE TABLE IF NOT EXISTS activity_tags (
    activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    uuid TEXT DEFAULT (lower(hex(randomblob(16)))),
    PRIMARY KEY (activity_id, tag_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_tags_uuid ON activity_tags(uuid);

-- Task prerequisites (dependency relationships)
CREATE TABLE IF NOT EXISTS task_prerequisites (
    task_id              INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    prerequisite_task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    created_at           TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    uuid TEXT DEFAULT (lower(hex(randomblob(16)))),
    PRIMARY KEY (task_id, prerequisite_task_id),
    CHECK (task_id != prerequisite_task_id)
);
CREATE INDEX IF NOT EXISTS idx_prereq_reverse ON task_prerequisites(prerequisite_task_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_task_prerequisites_uuid ON task_prerequisites(uuid);

-- Groups (first-class entities for activity organization)
CREATE TABLE IF NOT EXISTS groups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    uuid TEXT DEFAULT (lower(hex(randomblob(16))))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_groups_uuid ON groups(uuid);

-- Activity groups (many-to-many: activities <-> groups)
CREATE TABLE IF NOT EXISTS activity_groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,
    group_id    INTEGER NOT NULL,
    uuid TEXT DEFAULT (lower(hex(randomblob(16)))),
    FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id)    REFERENCES groups(id)     ON DELETE CASCADE,
    UNIQUE(activity_id, group_id)
);
CREATE INDEX IF NOT EXISTS idx_activity_groups_activity ON activity_groups(activity_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_groups_uuid ON activity_groups(uuid);

-- Calendars
CREATE TABLE IF NOT EXISTS calendars (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    color               TEXT NOT NULL DEFAULT '#7aa2f7',
    type                TEXT NOT NULL DEFAULT 'user',
    is_visible          INTEGER NOT NULL DEFAULT 1,
    weekly_budget_hours REAL,
    is_archived         INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    uuid TEXT DEFAULT (lower(hex(randomblob(16))))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_calendars_uuid ON calendars(uuid);

-- Calendar events
CREATE TABLE IF NOT EXISTS events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    calendar_id         INTEGER NOT NULL REFERENCES calendars(id) ON DELETE CASCADE,
    title               TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    location            TEXT NOT NULL DEFAULT '',
    start_dt            TEXT NOT NULL,
    end_dt              TEXT NOT NULL,
    all_day             INTEGER NOT NULL DEFAULT 0,
    color               TEXT,
    recurrence_rule     TEXT NOT NULL DEFAULT '',
    recurrence_end_dt   TEXT,
    linked_activity_id  INTEGER REFERENCES activities(id) ON DELETE SET NULL,
    linked_task_id      INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    uuid TEXT DEFAULT (lower(hex(randomblob(16))))
);
CREATE INDEX IF NOT EXISTS idx_events_calendar ON events(calendar_id);
CREATE INDEX IF NOT EXISTS idx_events_start    ON events(start_dt);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_uuid ON events(uuid);
CREATE INDEX IF NOT EXISTS idx_events_calendar_start ON events(calendar_id, start_dt);

-- Event exceptions (for recurring event overrides/cancellations)
CREATE TABLE IF NOT EXISTS event_exceptions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    occurrence_dt     TEXT NOT NULL,
    is_cancelled      INTEGER DEFAULT 0,
    override_event_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
    uuid TEXT DEFAULT (lower(hex(randomblob(16))))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_event_exceptions_uuid ON event_exceptions(uuid);

-- Task links
CREATE TABLE IF NOT EXISTS task_links (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    label      TEXT,
    url        TEXT NOT NULL,
    link_type  TEXT NOT NULL DEFAULT 'url',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    uuid TEXT DEFAULT (lower(hex(randomblob(16))))
);
CREATE INDEX IF NOT EXISTS idx_task_links_task ON task_links(task_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_task_links_uuid ON task_links(uuid);

-- Key-value settings
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Sync infrastructure (CDC changelog, device state, peer tracking)
CREATE TABLE IF NOT EXISTS sync_state (
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    device_id TEXT NOT NULL,
    syncing   INTEGER NOT NULL DEFAULT 0,
    logical_clock INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sync_changelog (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id  TEXT    NOT NULL,
    table_name TEXT    NOT NULL,
    row_uuid   TEXT    NOT NULL,
    operation  TEXT    NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    payload    TEXT    NOT NULL DEFAULT '{}',
    timestamp  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sync_cl_device ON sync_changelog(device_id);
CREATE INDEX IF NOT EXISTS idx_sync_cl_table  ON sync_changelog(table_name);

CREATE TABLE IF NOT EXISTS sync_peers (
    peer_device_id    TEXT PRIMARY KEY,
    peer_name         TEXT    NOT NULL DEFAULT '',
    last_changelog_id INTEGER NOT NULL DEFAULT 0,
    last_sync_at      TEXT
);

CREATE TABLE IF NOT EXISTS sync_tombstones (
    table_name      TEXT NOT NULL,
    row_uuid        TEXT NOT NULL,
    sync_version    INTEGER NOT NULL,
    sync_updated_by TEXT NOT NULL,
    deleted_payload TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (table_name, row_uuid)
);

CREATE TABLE IF NOT EXISTS sync_uuid_aliases (
    table_name   TEXT NOT NULL,
    source_uuid  TEXT NOT NULL,
    target_uuid  TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (table_name, source_uuid)
);

CREATE TABLE IF NOT EXISTS sync_conflicts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    peer_device_id TEXT NOT NULL DEFAULT '',
    table_name     TEXT NOT NULL,
    row_uuid       TEXT NOT NULL,
    conflict_type  TEXT NOT NULL,
    natural_key    TEXT,
    payload        TEXT NOT NULL DEFAULT '{}',
    created_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Seed system calendars (IDs 1-3 are reserved; INSERT OR IGNORE keeps them stable)
INSERT OR IGNORE INTO calendars (id, name, color, type) VALUES (1, 'Tasks', '#f7c948', 'system:tasks');
INSERT OR IGNORE INTO calendars (id, name, color, type) VALUES (2, 'Tracked Sessions', '#7aa2f7', 'system:sessions');
INSERT OR IGNORE INTO calendars (id, name, color, type) VALUES (3, 'Personal', '#9ece6a', 'user');
INSERT OR IGNORE INTO settings (key, value) VALUES ('default_calendar_id', '3');
"""


def init_database() -> None:
    """Create tables (idempotent) and run any pending migrations."""
    with get_connection() as conn:
        raw = conn.raw_connection
        # Detect fresh install: no tables exist yet
        is_fresh = not raw.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
        ).fetchone()

        conn.executescript(_INITIAL_SCHEMA)
        conn.commit()

        # Create group_id index only when the column exists (skips old-schema DBs)
        columns = [r[1] for r in raw.execute("PRAGMA table_info(activity_groups)").fetchall()]
        if "group_id" in columns:
            raw.execute(
                "CREATE INDEX IF NOT EXISTS idx_activity_groups_group ON activity_groups(group_id)"
            )
            raw.commit()

        from .migrations import run_pending_migrations, stamp_all_migrations

        if is_fresh:
            # Indexes on columns added by migrations — safe here because
            # the CREATE TABLE includes the column on fresh installs.
            raw.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_linked_task ON events(linked_task_id)"
            )
            raw.commit()
            stamp_all_migrations(raw)
        else:
            run_pending_migrations(raw)

    from .activities import ensure_background_group

    ensure_background_group()
