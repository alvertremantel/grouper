"""Cached, theme-aware SVG icons.

Single source of truth for all SVG icon rendering.  Call ``get_icon(name, color)``
instead of building QIcon from raw SVG in each consumer module.  The cache avoids
re-parsing / re-rendering the same (name, color) pair and can be invalidated on
theme change via ``clear_cache()``.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_cache: dict[tuple[str, str, int], QIcon] = {}


def get_icon(name: str, color: str, size: int = 16) -> QIcon:
    """Return a cached QIcon for the given (*name*, *color*, *size*) triple."""
    key = (name, color, size)
    if key in _cache:
        return _cache[key]
    svg_fn = _SVG_TEMPLATES.get(name)
    if svg_fn is None:
        raise KeyError(f"Unknown icon name: {name!r}")
    svg = svg_fn(color)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    icon = QIcon(pixmap)
    _cache[key] = icon
    return icon


def clear_cache() -> None:
    """Invalidate all cached icons.  Call on theme change."""
    _cache.clear()


def get_themed_icon(name: str, size: int = 16) -> QIcon:
    """Return a QIcon using the current theme's ``icon_stroke`` color."""
    from ..config import get_config
    from ..styles import theme_colors

    color = theme_colors(get_config().theme)["icon_stroke"]
    return get_icon(name, color, size)


# ---------------------------------------------------------------------------
# SVG templates — consolidated from task_board, task_list, history,
#                 time_tracker, calendar_view
# ---------------------------------------------------------------------------


def _settings_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="3"></circle>
  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
</svg>
"""


def _edit_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 20h9"></path>
  <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
</svg>
"""


def _trash_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="3 6 5 6 21 6"></polyline>
  <path d="M19 6l-1 14H6L5 6"></path>
  <path d="M10 11v6"></path>
  <path d="M14 11v6"></path>
  <path d="M9 6V4h6v2"></path>
</svg>
"""


def _move_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M15 3h6v6"/>
  <path d="M10 14L21 3"/>
  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
</svg>
"""


def _copy_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
</svg>
"""


def _nav_svg(color: str, *, direction: str = "prev") -> str:
    """Navigation chevron arrow.  *direction* is ``"prev"`` or ``"next"``."""
    path_d = "M10 3L5 8l5 5" if direction == "prev" else "M6 3l5 5-5 5"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
        f'<path d="{path_d}" stroke="{color}" stroke-width="2.2" fill="none"'
        ' stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


def _home_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
  <polyline points="9 22 9 12 15 12 15 22"/>
</svg>
"""


def _clock_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="10"/>
  <polyline points="12 6 12 12 16 14"/>
</svg>
"""


def _grid_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="3" width="7" height="7"/>
  <rect x="14" y="3" width="7" height="7"/>
  <rect x="14" y="14" width="7" height="7"/>
  <rect x="3" y="14" width="7" height="7"/>
</svg>
"""


def _list_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <line x1="8" y1="6" x2="21" y2="6"/>
  <line x1="8" y1="12" x2="21" y2="12"/>
  <line x1="8" y1="18" x2="21" y2="18"/>
  <line x1="3" y1="6" x2="3.01" y2="6"/>
  <line x1="3" y1="12" x2="3.01" y2="12"/>
  <line x1="3" y1="18" x2="3.01" y2="18"/>
</svg>
"""


def _calendar_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
  <line x1="16" y1="2" x2="16" y2="6"/>
  <line x1="8" y1="2" x2="8" y2="6"/>
  <line x1="3" y1="10" x2="21" y2="10"/>
</svg>
"""


def _history_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="1 4 1 10 7 10"/>
  <path d="M3.51 15a9 9 0 1 0 .49-3.6"/>
  <polyline points="12 7 12 12 15 15"/>
</svg>
"""


def _chart_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <line x1="18" y1="20" x2="18" y2="10"/>
  <line x1="12" y1="20" x2="12" y2="4"/>
  <line x1="6" y1="20" x2="6" y2="14"/>
  <line x1="2" y1="20" x2="22" y2="20"/>
</svg>
"""


def _info_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="10"/>
  <line x1="12" y1="16" x2="12" y2="12"/>
  <line x1="12" y1="8" x2="12.01" y2="8"/>
</svg>
"""


def _cart_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="9" cy="21" r="1"/>
  <circle cx="20" cy="21" r="1"/>
  <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
</svg>
"""


def _plug_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 22v-5"/>
  <path d="M9 8V2"/>
  <path d="M15 8V2"/>
  <path d="M18 8v5a6 6 0 0 1-12 0V8z"/>
</svg>
"""


def _mail_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="2" y="4" width="20" height="16" rx="2"/>
  <path d="M22 7l-10 7L2 7"/>
</svg>
"""


def _github_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/>
  <path d="M9 18c-4.51 2-5-2-7-2"/>
</svg>
"""


def _download_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
  <polyline points="7 10 12 15 17 10"/>
  <line x1="12" y1="15" x2="12" y2="3"/>
</svg>
"""


def _play_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="5 3 19 12 5 21 5 3"/>
</svg>
"""


def _pause_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="6" y="4" width="4" height="16"/>
  <rect x="14" y="4" width="4" height="16"/>
</svg>
"""


def _star_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
</svg>
"""


def _star_filled_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{color}" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
</svg>
"""


def _stop_svg(color: str) -> str:
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="3" width="18" height="18" rx="2"/>
</svg>
"""


def _task_add_svg(color: str) -> str:
    """Check-square icon for adding a scheduled task."""
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="3" width="18" height="18" rx="2"/>
  <path d="M9 12l2 2 4-4"/>
</svg>
"""


def _event_add_svg(color: str) -> str:
    """Calendar-plus icon for adding a calendar event."""
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="4" width="18" height="18" rx="2"/>
  <line x1="16" y1="2" x2="16" y2="6"/>
  <line x1="8" y1="2" x2="8" y2="6"/>
  <line x1="3" y1="10" x2="21" y2="10"/>
  <line x1="12" y1="14" x2="12" y2="20"/>
  <line x1="9" y1="17" x2="15" y2="17"/>
</svg>
"""


def _sync_svg(color: str) -> str:
    """Two circular arrows (Feather refresh-cw) for sync."""
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="1 4 1 10 7 10"/>
  <polyline points="23 20 23 14 17 14"/>
  <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10"/>
  <path d="M3.51 15A9 9 0 0 0 18.36 18.36L23 14"/>
</svg>
"""


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

_SVG_TEMPLATES: dict[str, Callable[[str], str]] = {
    "settings": _settings_svg,
    "edit": _edit_svg,
    "trash": _trash_svg,
    "move": _move_svg,
    "copy": _copy_svg,
    # nav_prev / nav_next use direction kwarg via wrapper lambdas
    "nav_prev": lambda c: _nav_svg(c, direction="prev"),
    "nav_next": lambda c: _nav_svg(c, direction="next"),
    # sidebar nav icons
    "home": _home_svg,
    "clock": _clock_svg,
    "grid": _grid_svg,
    "list": _list_svg,
    "calendar": _calendar_svg,
    "history": _history_svg,
    "chart": _chart_svg,
    "info": _info_svg,
    # about page link icons
    "cart": _cart_svg,
    "plug": _plug_svg,
    "mail": _mail_svg,
    "github": _github_svg,
    "download": _download_svg,
    # session card control icons
    "play": _play_svg,
    "pause": _pause_svg,
    "stop": _stop_svg,
    "star": _star_svg,
    "star_filled": _star_filled_svg,
    # timeline action buttons
    "task_add": _task_add_svg,
    "event_add": _event_add_svg,
    # sync
    "sync": _sync_svg,
}
