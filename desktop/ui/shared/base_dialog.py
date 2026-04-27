"""
base_dialog.py — Shared dialog base classes for Grouper.

Centralizes FramelessDialog and BaseFormDialog to avoid circular imports
and provide consistent dialog behavior across the application.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QVBoxLayout,
    QWidget,
)

from .title_bar import DialogTitleBar


class FramelessDialog(QDialog):
    """Base class for frameless dialogs with custom title bar and shadow.

    Transparency contract:
        - dialogFrame and dialogContent have WA_StyledBackground=True
        - Dialog itself has autoFillBackground=True to prevent black margins
          when parented to another window.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)

        # Prevent black transparent margins when parented
        self.setAutoFillBackground(True)

        self._container = QFrame()
        self._container.setObjectName("dialogFrame")
        self._container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        self._container.setGraphicsEffect(shadow)

        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(16, 16, 16, 16)
        self._outer_layout.addWidget(self._container)

        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(0)

        self._title_bar = DialogTitleBar("", self._container)
        self._title_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._container_layout.addWidget(self._title_bar)

        self._content = QWidget()
        self._content.setObjectName("dialogContent")
        self._content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._container_layout.addWidget(self._content)

        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(16, 12, 16, 16)
        self._content_layout.setSpacing(10)

    def setWindowTitle(self, title: str):
        super().setWindowTitle(title)
        if hasattr(self, "_title_bar"):
            self._title_bar.set_title(title)

    def contentLayout(self) -> QVBoxLayout:
        return self._content_layout


class BaseFormDialog(FramelessDialog):
    """FramelessDialog with standard form layout + Ok/Cancel buttons.

    Provides:
    - QFormLayout with standard spacing (accessible as self._form)
    - Ok/Cancel button box (accessible as self._buttons)
    - add_row() helper for form fields
    - finalize_form() to add buttons to the form
    - set_field_error() static helper for field validation
    """

    def __init__(self, title: str, min_width: int = 380, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(min_width)
        self._form = QFormLayout()
        self._form.setSpacing(10)
        self.contentLayout().addLayout(self._form)
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

    def add_row(self, label, widget):
        """Add a row to the form layout."""
        self._form.addRow(label, widget)

    def add_form_row(self, label, widget):
        """Alias for add_row() for convenience."""
        self.add_row(label, widget)

    def finalize_form(self):
        """Add the button box to the form. Call after all rows are added."""
        self._form.addRow(self._buttons)

    @staticmethod
    def set_field_error(widget, has_error: bool = True):
        """Toggle the 'error' property on a widget and force QSS re-evaluation."""
        widget.setProperty("error", has_error)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
