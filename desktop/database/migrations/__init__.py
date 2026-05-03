"""migrations — Re-exported from grouper_core."""

from __future__ import annotations

from typing import Any

import grouper_core.database.migrations as _core_mig
from grouper_core.database.migrations import (
    run_pending_migrations,
    stamp_all_migrations,
)


def __getattr__(name: str) -> Any:
    return getattr(_core_mig, name)
