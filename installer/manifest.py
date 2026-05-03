"""Install manifest persistence for Grouper upgrades and uninstall."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

MANIFEST_DIR = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Grouper"
MANIFEST_FILE = MANIFEST_DIR / "install-manifest.json"


_MANIFEST_VERSION = "1"


@dataclass
class InstallManifest:
    version: str
    variant: str
    install_time: str
    destinations: dict[str, str]
    path_entries: list[str]
    shortcuts: list[str]
    installer_path: str = ""
    manifest_version: str = _MANIFEST_VERSION


def write_manifest(manifest: InstallManifest) -> None:
    """Write an install manifest to MANIFEST_FILE."""
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    try:
        data = {
            "manifest_version": manifest.manifest_version,
            "version": manifest.version,
            "variant": manifest.variant,
            "install_time": manifest.install_time,
            "destinations": manifest.destinations,
            "path_entries": manifest.path_entries,
            "shortcuts": manifest.shortcuts,
            "installer_path": manifest.installer_path,
        }
        MANIFEST_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except PermissionError as exc:
        raise PermissionError(f"Cannot write install manifest: {exc}") from exc


def read_manifest() -> InstallManifest | None:
    """Read the install manifest, or return None if missing/corrupt."""
    if not MANIFEST_FILE.exists():
        return None
    try:
        data = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        return InstallManifest(
            version=data["version"],
            variant=data["variant"],
            install_time=data["install_time"],
            destinations=data["destinations"],
            path_entries=data.get("path_entries", []),
            shortcuts=data.get("shortcuts", []),
            installer_path=data.get("installer_path", ""),
            manifest_version=data.get("manifest_version", _MANIFEST_VERSION),
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def remove_manifest() -> None:
    """Delete the install manifest and clean up the directory if empty."""
    if MANIFEST_FILE.exists():
        MANIFEST_FILE.unlink()
    if MANIFEST_DIR.exists() and not any(MANIFEST_DIR.iterdir()):
        MANIFEST_DIR.rmdir()
