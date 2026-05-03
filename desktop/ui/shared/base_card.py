"""base_card.py — Shared base class for card-style widgets."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QWidget


class BaseCard(QFrame):
    """Base class for all card-style widgets.

    Centralizes:
    - setObjectName("card")
    - Standard content margins (12, 8, 12, 8)
    - Standard spacing (8)
    - WA_StyledBackground attribute (prevents transparency bleed-through)
    - Child transparency propagation helper

    Transparency contract:
        All card widgets MUST use WA_StyledBackground. The QSS rule
        ``#card QWidget { background-color: transparent; }`` relies on the
        card itself having an opaque styled background. Without this,
        parent widget transparency bleeds through and cards appear as
        black rectangles on certain themes.
    """

    CONTENT_MARGINS: tuple[int, int, int, int] = (12, 8, 12, 8)
    CONTENT_SPACING: int = 8

    def __init__(self, parent: QWidget | None = None, *, object_name: str = "card"):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def _make_row(self) -> QHBoxLayout:
        """Create and return a standard horizontal card layout."""
        row = QHBoxLayout(self)
        row.setContentsMargins(*self.CONTENT_MARGINS)
        row.setSpacing(self.CONTENT_SPACING)
        return row

    @staticmethod
    def _make_child_transparent(widget: QWidget) -> None:
        """Set a widget and its children transparent for mouse events (drag passthrough)."""
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        for child in widget.findChildren(QWidget):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
