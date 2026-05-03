"""output.py — Shared output formatting for the Grouper CLI.

Supports two modes:
  - JSON (--json flag): machine-readable, one JSON blob to stdout
  - Human (default): aligned columns / readable text
"""

from __future__ import annotations

import json
import sys
from typing import Any

from grouper_core.formatting import (
    default_json_serializer as _default,
)
from grouper_core.formatting import (
    format_duration,
)

# Re-export for existing call sites that import from here.
__all__ = ["format_duration", "print_error", "print_json", "print_kv", "print_table"]


def print_json(data: Any) -> None:
    """Dump *data* as indented JSON to stdout."""
    json.dump(data, sys.stdout, indent=2, default=_default)
    sys.stdout.write("\n")


def print_table(
    rows: list[dict[str, Any]], columns: list[str], headers: list[str] | None = None
) -> None:
    """Print *rows* as an aligned text table.

    *columns* are the dict keys to display.
    *headers* are the display names (defaults to column keys uppercased).
    """
    if not rows:
        print("(no results)")
        return

    hdrs = headers or [c.upper().replace("_", " ") for c in columns]
    col_widths = [len(h) for h in hdrs]

    stringified: list[list[str]] = []
    for row in rows:
        cells = [str(row.get(c, "")) for c in columns]
        stringified.append(cells)
        for i, cell in enumerate(cells):
            col_widths[i] = max(col_widths[i], len(cell))

    # Header
    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(hdrs))
    print(header_line)
    print("  ".join("-" * w for w in col_widths))

    # Rows
    for cells in stringified:
        print("  ".join(cells[i].ljust(col_widths[i]) for i in range(len(columns))))


def print_kv(pairs: list[tuple[str, Any]]) -> None:
    """Print key-value pairs aligned on the colon."""
    if not pairs:
        return
    max_key = max(len(k) for k, _ in pairs)
    for key, val in pairs:
        print(f"  {key.rjust(max_key)}: {val}")


def print_error(msg: str) -> None:
    """Print an error message to stderr."""
    print(f"error: {msg}", file=sys.stderr)
