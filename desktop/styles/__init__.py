"""Styles package — QSS theme loading via template + color palettes.

Each theme is defined as a dict of color tokens.  At load time, the single
``_base.qss`` template is rendered by substituting ``{{token}}`` placeholders
with the chosen palette's hex values.  This replaces the old scheme of 8
near-identical .qss files (~10 000 lines) with 1 template + compact palettes.
"""

from pathlib import Path

from PySide6.QtWidgets import QApplication

# Re-export everything from colors.py so existing imports keep working:
#   from desktop.styles import theme_colors, lerp_hex, ...
from .colors import (
    _THEME_PALETTE,
    TASK_COLOR,
    THEME_GROUPS,
    available_themes,
    lerp_hex,
    theme_colors,
)

_STYLES_DIR = Path(__file__).parent
_TEMPLATE_CACHE: str | None = None


# ---------------------------------------------------------------------------
#  QSS-specific helpers (require PySide6)
# ---------------------------------------------------------------------------


def _get_template() -> str:
    """Read and cache the QSS template file."""
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is None:
        _TEMPLATE_CACHE = (_STYLES_DIR / "_base.qss").read_text(encoding="utf-8")
    return _TEMPLATE_CACHE


def load_theme(app: QApplication, theme: str = "dark") -> None:
    """Render the QSS template with the chosen palette and apply it."""
    palette = _THEME_PALETTE.get(theme, _THEME_PALETTE["dark"])
    qss = _get_template()
    for token, value in palette.items():
        qss = qss.replace("{{" + token + "}}", value)
    app.setStyleSheet(qss)
