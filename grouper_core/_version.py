"""Read version from pyproject.toml (dev / source tree) or package metadata (installed).

When compiled with Nuitka the source tree is gone and importlib.metadata may
hold stale data.  As a final fallback the version baked at import time via
``_FALLBACK_VERSION`` (kept in sync with pyproject.toml) is used.
"""

from __future__ import annotations

from pathlib import Path

_FALLBACK_VERSION = "1.1.0.5"

_pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"

if _pyproject.exists():
    import tomllib

    with open(_pyproject, "rb") as _f:
        __version__: str = tomllib.load(_f)["project"]["version"]
else:
    try:
        from importlib.metadata import version

        __version__ = version("grouper")
    except Exception:
        # Nuitka builds or missing metadata — use baked-in fallback
        __version__ = _FALLBACK_VERSION
