"""
migrations — File-based database migration system.

Each migration lives in its own ``v00N_description.py`` file and exports
``VERSION``, ``DESCRIPTION``, and ``upgrade(conn)``.  The runner discovers
them via an explicit registry, applies pending ones in order, and records
each in a ``_migrations`` audit table.
"""

import contextlib
import importlib
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from types import ModuleType

from ..connection import (
    _get_schema_version,
    _set_schema_version,
    backup_database,
    get_data_directory,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registry — one entry per migration module (no auto-discovery)
# ---------------------------------------------------------------------------

_REGISTRY: list[str] = [
    "v001_stamp_initial",
    "v002_add_boards",
    "v003_soft_delete_activities",
    "v004_activity_groups",
    "v005_calendar_system",
    "v006_task_links",
    "v007_fix_projects_fk",
    "v008_add_starred",
    "v009_add_task_due_date",
    "v010_tasks_schema_upgrade",
    "v011_activities_schema_upgrade",
    "v012_entity_tags",
    "v013_task_prerequisites",
    "v014_event_linked_task",
    "v015_backfill_linked_task",
    "v016_formalize_groups",
    "v017_add_task_description",
    "v018_sync_support",
    "v019_add_performance_indexes",
    "v020_add_uuid_indexes",
    "v021_sync_conflict_convergence",
    "v022_sync_bootstrap_and_deferred",
    "v023_sync_legacy_metadata_repair",
]


# ---------------------------------------------------------------------------
# Discovery + validation
# ---------------------------------------------------------------------------


def _discover_migrations() -> list[ModuleType]:
    """Import and validate every registered migration module."""
    modules: list[ModuleType] = []
    for name in _REGISTRY:
        mod = importlib.import_module(f".{name}", package=__name__)
        # Validate required exports
        for attr in ("VERSION", "DESCRIPTION", "upgrade"):
            if not hasattr(mod, attr):
                raise ImportError(f"Migration {name} missing required attribute: {attr}")
        modules.append(mod)
    # Ensure sorted by VERSION with no duplicates
    modules.sort(key=lambda m: m.VERSION)
    versions = [m.VERSION for m in modules]
    if len(versions) != len(set(versions)):
        raise ValueError(f"Duplicate migration versions: {versions}")
    return modules


# ---------------------------------------------------------------------------
# Migrations table
# ---------------------------------------------------------------------------


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            version     INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.commit()


def _get_applied_versions(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute("SELECT version FROM _migrations").fetchall()
    return {row["version"] for row in rows}


def _bootstrap_migration_history(
    conn: sqlite3.Connection,
    migrations: list[ModuleType],
) -> None:
    """Populate ``_migrations`` for legacy databases that already have a
    ``schema_version`` but no migration history rows."""
    applied = _get_applied_versions(conn)
    if applied:
        return  # already bootstrapped

    current = _get_schema_version(conn)
    if current == 0:
        return  # brand-new database, nothing to backfill

    # Build a VERSION -> DESCRIPTION map from discovered modules
    desc_map = {m.VERSION: m.DESCRIPTION for m in migrations}
    now = datetime.now().isoformat()
    for v in range(1, current + 1):
        desc = desc_map.get(v, "legacy migration")
        conn.execute(
            "INSERT OR IGNORE INTO _migrations (version, description, applied_at) VALUES (?, ?, ?)",
            (v, desc, now),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Pending detection
# ---------------------------------------------------------------------------


def _get_pending(
    conn: sqlite3.Connection,
    migrations: list[ModuleType],
) -> list[ModuleType]:
    applied = _get_applied_versions(conn)
    return [m for m in migrations if m.VERSION not in applied]


# ---------------------------------------------------------------------------
# Pre-migration backup + retention
# ---------------------------------------------------------------------------


def _backup_before_migration(old_version: int, new_version: int) -> bool:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"grouper_pre_migration_v{old_version}_to_v{new_version}_{ts}.db"
    success = backup_database(filename=filename)
    if success:
        log.info("Pre-migration backup created: %s", filename)
        _cleanup_migration_backups(keep=3)
    else:
        log.warning("Pre-migration backup failed — proceeding anyway")
    return success


def _cleanup_migration_backups(keep: int = 3) -> None:
    backup_dir = get_data_directory() / "backups"
    if not backup_dir.exists():
        return
    backups = sorted(
        backup_dir.glob("grouper_pre_migration_v*"),
        key=lambda p: p.stat().st_mtime,
    )
    for old in backups[:-keep]:
        with contextlib.suppress(OSError):
            old.unlink()


# ---------------------------------------------------------------------------
# Runner — main entry point
# ---------------------------------------------------------------------------


def stamp_all_migrations(conn: sqlite3.Connection) -> None:
    """Mark every registered migration as applied without running it.

    Used on fresh installs where ``_INITIAL_SCHEMA`` already contains
    all the schema changes that migrations would otherwise apply.
    """
    _ensure_migrations_table(conn)
    all_migrations = _discover_migrations()
    now = datetime.now().isoformat()
    for m in all_migrations:
        conn.execute(
            "INSERT OR IGNORE INTO _migrations (version, description, applied_at) VALUES (?, ?, ?)",
            (m.VERSION, m.DESCRIPTION, now),
        )
    if all_migrations:
        _set_schema_version(conn, all_migrations[-1].VERSION)
    conn.commit()
    log.info("Fresh install — stamped %d migrations as applied", len(all_migrations))


def run_pending_migrations(conn: sqlite3.Connection) -> None:
    """Discover and apply any pending migrations.

    Called from ``init_database()`` in ``connection.py``.
    """
    _ensure_migrations_table(conn)
    all_migrations = _discover_migrations()
    _bootstrap_migration_history(conn, all_migrations)

    pending = _get_pending(conn, all_migrations)
    if not pending:
        return

    old_v = _get_schema_version(conn)
    new_v = pending[-1].VERSION
    _backup_before_migration(old_v, new_v)

    for migration in pending:
        log.info(
            "Applying migration v%03d: %s",
            migration.VERSION,
            migration.DESCRIPTION,
        )
        migration.upgrade(conn)
        conn.execute(
            "INSERT INTO _migrations (version, description) VALUES (?, ?)",
            (migration.VERSION, migration.DESCRIPTION),
        )
        _set_schema_version(conn, migration.VERSION)
        conn.commit()

    log.info("All migrations applied (v%d → v%d)", old_v, new_v)
