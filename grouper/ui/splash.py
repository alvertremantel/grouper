"""splash.py — Startup splash screen with branding and loading indicator."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .._version import __version__
from ..styles import theme_colors


class SpinnerWidget(QWidget):
    """Animated spinning arc indicator."""

    def __init__(self, color: str, size: int = 32, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._color = QColor(color)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30fps is smoother under startup load
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(self._color, 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        margin = 4
        rect = self.rect().adjusted(margin, margin, -margin, -margin)

        # Qt angles are in 1/16th of a degree; 270-degree arc leaves a 90-degree gap
        start_angle = int(self._angle * 16)
        span_angle = 270 * 16
        painter.drawArc(rect, start_angle, span_angle)

        painter.end()


class SplashScreen(QWidget):
    """Startup splash screen with GROUPER branding and a spinning indicator."""

    def __init__(self, theme: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(280, 200)

        colors = theme_colors(theme)
        self._bg_color = QColor(colors["bg-primary"])
        self._border_color = QColor(colors["accent"])

        self._build(colors)
        self._center_on_screen()

    def _build(self, colors: dict[str, str]) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 32, 24, 24)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # "GROUPER" title (Cascadia Mono preferred but not required — CSS fallback chain)
        title = QLabel("GROUPER")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"font-family: 'Cascadia Mono', 'DejaVu Sans Mono', monospace;"
            f"font-size: 26px; font-weight: 700; letter-spacing: 2px;"
            f"color: {colors['accent']}; background: transparent;"
        )
        layout.addWidget(title)

        # Version
        version = QLabel(f"v{__version__}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet(
            f"font-family: 'Cascadia Mono', 'DejaVu Sans Mono', monospace;"
            f"font-size: 11px; color: {colors['text-muted']}; background: transparent;"
        )
        layout.addWidget(version)

        layout.addSpacing(20)

        # Spinner
        self._spinner = SpinnerWidget(colors["accent"])
        spinner_row = QHBoxLayout()
        spinner_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spinner_row.addWidget(self._spinner)
        layout.addLayout(spinner_row)

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)

    def start_spinner(self) -> None:
        self._spinner.start()

    def stop_spinner(self) -> None:
        self._spinner.stop()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(self._bg_color)
        painter.setPen(QPen(self._border_color, 1))
        painter.drawRoundedRect(rect, 12, 12)

        painter.end()
