"""connection.py — Re-exported from grouper_core with Qt notifier added."""

from __future__ import annotations

from typing import Any

import grouper_core.database.connection as _core_conn

# Re-export public API from grouper_core
from grouper_core.database.connection import (
    backup_database,
    bump_version,
    get_connection,
    get_data_directory,
    get_database_path,
    get_version,
    init_database,
    register_data_changed_callback,
    set_archived,
    set_data_directory,
    unregister_data_changed_callback,
)

# ---------------------------------------------------------------------------
# Qt notifier — desktop app only (PySide6 lazy import)
# ---------------------------------------------------------------------------

_notifier: Any | None = None


def get_notifier() -> Any:
    """Return the singleton _DataNotifier, creating it lazily on first call.

    PySide6 is imported here (not at module level) so that this module can be
    used without a Qt runtime.  The notifier's data_changed signal is
    registered as a callback with grouper_core's bump_version().
    """
    global _notifier
    if _notifier is None:
        from PySide6.QtCore import QObject, Signal

        class _DataNotifier(QObject):
            data_changed: Signal = Signal()

        _notifier = _DataNotifier()
        register_data_changed_callback(_notifier.data_changed.emit)
    return _notifier


# ---------------------------------------------------------------------------
# Proxy for private names and mutable module-level globals
# ---------------------------------------------------------------------------
# Tests and internal code access _init_paths, _INITIAL_SCHEMA,
# _set_schema_version, _get_schema_version, DATA_DIR, DATABASE_PATH, etc.
# __getattr__ delegates to the core module so live values are returned.


def __getattr__(name: str) -> Any:
    return getattr(_core_conn, name)
