"""TUI sub-package -- Textual-based terminal dashboard."""

try:
    from textual.app import App as _App

    HAS_TEXTUAL = True
except ImportError:
    HAS_TEXTUAL = False
