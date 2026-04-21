"""version_check.py — Background version checking against GitHub Releases API."""

from __future__ import annotations

import json
import logging
import re
import threading
from urllib.request import Request, urlopen

from PySide6.QtCore import QThread, Signal

from ._urls import GITHUB_RELEASES_API_URL, GITHUB_RELEASES_URL
from ._version import __version__

logger = logging.getLogger(__name__)

__all__ = [
    "VersionCheckWorker",
    "check_for_update",
]

# Module-level cache: (has_update, latest_version, release_url) | None
# Only set on a successful check — failures are never cached so they are retried.
_cache: tuple[bool, str, str] | None = None
_cache_lock = threading.Lock()


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a version string into a comparable tuple.

    Supports SemVer ('1.0.0-rc.1') and PEP 440 ('1.0.0rc1') pre-release formats,
    as well as plain release versions ('1.0.0', 'v2.1.3').

    Pre-release suffixes make the version sort *below* the corresponding release.
    A trailing sentinel distinguishes release (1) from pre-release (0):
      '1.0.0'       → (1, 0, 0, 1)
      '1.0.0rc1'    → (1, 0, 0, 0)
      '1.0.0-rc.1'  → (1, 0, 0, 0)

    Segments are zero-padded to length 3 so that '1.0' and '1.0.0' compare equal.
    """
    stripped = version_str.lstrip("v")
    # Match the leading numeric dotted part; anything after is a pre-release suffix.
    # Handles both "1.0.0rc1" (PEP 440) and "1.0.0-rc.1" (SemVer).
    m = re.match(r"^(\d+(?:\.\d+)*)(.*)", stripped)
    parts_str = m.group(1) if m else stripped
    _suffix = m.group(2) if m else ""
    parts = [int(x) for x in parts_str.split(".")]
    while len(parts) < 3:
        parts.append(0)
    # Append 0 for pre-release, 1 for release — so pre-release < release.
    parts.append(0 if _suffix else 1)
    return tuple(parts)


def check_for_update() -> tuple[bool, str, str]:
    """
    Check GitHub Releases API for a newer version.
    Returns (has_update, latest_version, release_url).
    Returns (False, "", "") on any network or parse failure (not cached).
    Successful results are cached for the lifetime of the process.
    """
    global _cache
    with _cache_lock:
        if _cache is not None:
            return _cache

        req = Request(GITHUB_RELEASES_API_URL)
        req.add_header("Accept", "application/vnd.github.v3+json")
        req.add_header("User-Agent", f"Grouper/{__version__}")

        try:
            with urlopen(req, timeout=10) as resp:
                release = json.loads(resp.read().decode())

            latest_tag: str = release.get("tag_name", "")

            if not latest_tag:
                return False, "", ""

            latest_ver = _parse_version(latest_tag)
            current_ver = _parse_version(__version__)

            has_update = latest_ver > current_ver
            _cache = (has_update, latest_tag.lstrip("v"), GITHUB_RELEASES_URL)
            return _cache
        except Exception as e:
            logger.debug("Version check failed: %s", e)
            return False, "", ""


class VersionCheckWorker(QThread):
    """Non-blocking version check. Emit a signal when done; never touch the GUI directly."""

    update_available = Signal(str, str)  # (latest_version, release_url)
    up_to_date = Signal()
    check_failed = Signal()

    def run(self) -> None:
        has_update, version, url = check_for_update()
        if has_update:
            self.update_available.emit(version, url)
        elif version:  # non-empty version = successful check, just up to date
            self.up_to_date.emit()
        else:
            self.check_failed.emit()
