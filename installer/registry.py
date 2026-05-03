"""Windows uninstall registry registration for Grouper."""

from __future__ import annotations

import os
import winreg
from contextlib import suppress
from pathlib import Path

from .manifest import InstallManifest

UNINSTALL_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Grouper"


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = Path(dirpath) / f
                if fp.is_file():
                    total += fp.stat().st_size
    except OSError:
        pass
    return total


def register_uninstall(manifest: InstallManifest) -> None:
    """Register Grouper in Add/Remove Programs."""
    key = winreg.CreateKeyEx(
        winreg.HKEY_LOCAL_MACHINE,
        UNINSTALL_KEY,
        0,
        winreg.KEY_CREATE_SUB_KEY | winreg.KEY_SET_VALUE,
    )
    try:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "Grouper")
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, manifest.version)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Grouper")

        app_dest = manifest.destinations.get("app", "")
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, app_dest)

        if manifest.installer_path:
            uninstall_cmd = f'"{manifest.installer_path}" --uninstall'
        elif app_dest:
            uninstall_cmd = f'"{Path(app_dest) / "setup.exe"}" --uninstall'
        else:
            uninstall_cmd = ""
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, uninstall_cmd)

        total_bytes = 0
        for dest in manifest.destinations.values():
            p = Path(dest)
            if p.exists():
                total_bytes += _dir_size(p)
        estimated_kb = total_bytes // 1024
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, estimated_kb)

        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    finally:
        winreg.CloseKey(key)


def unregister_uninstall() -> None:
    """Remove the Grouper uninstall registry entry."""
    with suppress(FileNotFoundError):
        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY)
