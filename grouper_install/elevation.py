"""Elevation detection and UAC relaunch for Windows."""

from __future__ import annotations

import ctypes
import subprocess
import sys


def is_elevated() -> bool:
    """Return True if the current process has administrator privileges."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except AttributeError:
        return False


def relaunch_elevated(argv: list[str] | None = None) -> None:
    """Relaunch the current executable with UAC elevation and exit."""
    executable = sys.argv[0]
    args = (
        subprocess.list2cmdline(argv)
        if argv is not None
        else subprocess.list2cmdline(sys.argv[1:])
    )
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, args, None, 1)
    if result <= 32:
        raise OSError(f"Failed to relaunch elevated (ShellExecuteW returned {result})")
    sys.exit(0)
