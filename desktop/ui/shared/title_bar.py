"""
title_bar.py — Custom window title bar for Grouper.

Replaces the default OS window chrome with a dark-themed title bar
that matches the application's design. Provides:
  - App title label
  - Minimize / maximize-restore / close buttons
  - Click-and-drag to move the window
  - Double-click to toggle maximise
"""

import sys

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
)


class TitleBarButton(QPushButton):
    """A small, icon-style button used in the custom title bar."""

    def __init__(self, text: str, object_name: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName(object_name)
        self.setFixedSize(55, 38)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)


class TitleBar(QFrame):
    """Custom window title bar with drag support and window controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(43)
        self._drag_pos: QPoint | None = None
        self._build()

    # -- construction --------------------------------------------------------

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(0)

        # App icon
        app = QApplication.instance()
        if app is not None:
            icon_lbl = QLabel()
            icon_lbl.setPixmap(app.windowIcon().pixmap(QSize(22, 22)))
            layout.addWidget(icon_lbl)
            layout.addSpacing(8)

        # App title
        self._title = QLabel("GROUPER")
        self._title.setObjectName("titleBarTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._title)

        layout.addStretch()

        # Window-control buttons
        self._btn_min = TitleBarButton("—", "titleBarBtnMin")
        self._btn_max = TitleBarButton("☐", "titleBarBtnMax")
        self._btn_close = TitleBarButton("✕", "titleBarBtnClose")

        self._btn_min.clicked.connect(self._on_minimize)
        self._btn_max.clicked.connect(self._on_maximize)
        self._btn_close.clicked.connect(self._on_close)

        layout.addWidget(self._btn_min)
        layout.addWidget(self._btn_max)
        layout.addWidget(self._btn_close)

    # -- window actions ------------------------------------------------------

    def _on_minimize(self):
        self.window().showMinimized()

    def _on_maximize(self):
        win = self.window()
        if win.isMaximized():
            win.showNormal()
        else:
            win.showMaximized()

    def _on_close(self):
        self.window().close()

    # -- public API ----------------------------------------------------------

    def update_maximize_icon(self, maximized: bool):
        """Swap the maximise button icon between ☐ and ❐."""
        self._btn_max.setText("❐" if maximized else "☐")

    # -- drag-to-move --------------------------------------------------------

    def mousePressEvent(self, event):
        if sys.platform == "win32":
            # Drag handled natively via WM_NCHITTEST -> HTCAPTION
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            )
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if sys.platform == "win32":
            return
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            win = self.window()
            if win.isMaximized():
                win.showNormal()
                title_center_x = self._title.x() + self._title.width() // 2
                anchor_y = self.height() // 2
                new_x = int(event.globalPosition().x()) - title_center_x
                new_y = int(event.globalPosition().y()) - anchor_y
                win.move(new_x, new_y)
                self._drag_pos = event.globalPosition().toPoint() - win.frameGeometry().topLeft()
            else:
                win.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if sys.platform == "win32":
            return
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if sys.platform == "win32":
            # Double-click-to-maximize handled natively via HTCAPTION
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_maximize()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


class DialogTitleBarButton(QPushButton):
    """A compact close button for dialog title bars."""

    def __init__(self, parent=None):
        super().__init__("✕", parent)
        self.setObjectName("dialogTitleBarBtnClose")
        self.setFixedSize(36, 28)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)


class DialogTitleBar(QFrame):
    """Compact title bar for frameless dialogs with drag-to-move and close button."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("dialogTitleBar")
        self.setFixedHeight(32)
        self._drag_pos: QPoint | None = None
        self._build(title)

    def _build(self, title: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(0)

        self._title = QLabel(title)
        self._title.setObjectName("dialogTitleBarTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._title)

        layout.addStretch()

        self._btn_close = DialogTitleBarButton()
        self._btn_close.clicked.connect(self._on_close)
        layout.addWidget(self._btn_close)

    def _on_close(self):
        self.window().reject()

    def set_title(self, title: str):
        self._title.setText(title)

    def mousePressEvent(self, event):
        if sys.platform == "win32":
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            )
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if sys.platform == "win32":
            return
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if sys.platform == "win32":
            return
        self._drag_pos = None
        super().mouseReleaseEvent(event)
