"""animated_stack.py — Animated view container with directional slide transitions.

Replaces QStackedWidget for top-level navigation.  Both vertical (up/down)
and horizontal (left/right) axes are supported via the ``SlideAxis`` enum.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QScrollArea, QSizePolicy, QWidget

from ..config import get_config


class SlideAxis(Enum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


class AnimatedViewStack(QWidget):
    """Container that holds multiple view widgets and animates slide
    transitions between them.

    At rest only the *current* widget is visible; during a transition both
    the outgoing and incoming widgets are visible and sliding.

    Direction is determined by comparing indices:
    - Higher target index  -> forward  (up / left)
    - Lower  target index  -> backward (down / right)
    """

    currentChanged = Signal(int)
    DURATION = 200  # ms

    def __init__(
        self,
        parent: QWidget | None = None,
        axis: SlideAxis = SlideAxis.VERTICAL,
    ) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._widgets: list[QWidget] = []
        self._current_index: int = -1
        self._axis = axis

        # In-flight transition state
        self._animation_group: QParallelAnimationGroup | None = None
        self._transitioning_from: int = -1
        self._transitioning_to: int = -1
        self._saved_hscroll_policies: list[tuple[QScrollArea, Qt.ScrollBarPolicy]] = []

    # -- public API (QStackedWidget-compatible) ------------------------------

    def addWidget(self, widget: QWidget) -> int:
        """Add a view widget.  Returns its index."""
        widget.setParent(self)
        idx = len(self._widgets)
        self._widgets.append(widget)

        if idx == 0:
            # First widget — show immediately, fill container
            widget.setGeometry(0, 0, self.width(), self.height())
            widget.show()
            self._current_index = 0
        else:
            widget.hide()

        return idx

    def setCurrentIndex(self, index: int) -> None:
        """Switch to the view at *index* with a slide animation.

        ``currentIndex()`` returns the new value immediately (before the
        animation completes) so that callers like the sidebar can highlight
        the destination tab without waiting.
        """
        if index == self._current_index:
            return
        if index < 0 or index >= len(self._widgets):
            return

        old_index = self._current_index

        # Cancel any in-flight transition first
        if self._animation_group is not None:
            self._finalize_transition()

        self._current_index = index
        self.currentChanged.emit(index)

        if not get_config().animations_enabled:
            self._widgets[old_index].hide()
            new_widget = self._widgets[index]
            new_widget.setGeometry(0, 0, self.width(), self.height())
            new_widget.show()
            return

        self._start_transition(old_index, index)

    def currentIndex(self) -> int:
        return self._current_index

    def widget(self, index: int) -> QWidget | None:
        if 0 <= index < len(self._widgets):
            return self._widgets[index]
        return None

    def count(self) -> int:
        return len(self._widgets)

    @property
    def axis(self) -> SlideAxis:
        return self._axis

    @axis.setter
    def axis(self, value: SlideAxis) -> None:
        self._axis = value

    # -- transition mechanics ------------------------------------------------

    def _start_transition(self, old_idx: int, new_idx: int) -> None:
        old_widget = self._widgets[old_idx]
        new_widget = self._widgets[new_idx]
        w, h = self.width(), self.height()

        forward = new_idx > old_idx

        if self._axis == SlideAxis.VERTICAL:
            offset = QPoint(0, h if forward else -h)
        else:
            offset = QPoint(w if forward else -w, 0)

        # Size both to fill container
        old_widget.setGeometry(0, 0, w, h)
        # Position new widget off-screen, then show (triggers showEvent)
        new_widget.setGeometry(offset.x(), offset.y(), w, h)
        new_widget.show()

        # Suppress horizontal scrollbars on the incoming view during the slide
        self._saved_hscroll_policies = []
        for sa in new_widget.findChildren(QScrollArea):
            policy = sa.horizontalScrollBarPolicy()
            if policy != Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
                self._saved_hscroll_policies.append((sa, policy))
                sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Animate old widget from (0,0) to the opposite offset
        old_anim = QPropertyAnimation(old_widget, b"pos")
        old_anim.setDuration(self.DURATION)
        old_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        old_anim.setStartValue(QPoint(0, 0))
        old_anim.setEndValue(QPoint(-offset.x(), -offset.y()))

        # Animate new widget from offset to (0,0)
        new_anim = QPropertyAnimation(new_widget, b"pos")
        new_anim.setDuration(self.DURATION)
        new_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        new_anim.setStartValue(offset)
        new_anim.setEndValue(QPoint(0, 0))

        group = QParallelAnimationGroup(self)
        group.addAnimation(old_anim)
        group.addAnimation(new_anim)

        self._transitioning_from = old_idx
        self._transitioning_to = new_idx
        self._animation_group = group

        group.finished.connect(self._on_transition_finished)
        group.start()

    def _finalize_transition(self) -> None:
        """Immediately complete the in-flight transition."""
        if self._animation_group is None:
            return

        group = self._animation_group
        self._animation_group = None
        group.finished.disconnect(self._on_transition_finished)
        group.stop()
        group.deleteLater()

        # Hide the outgoing widget and reset its position
        old_widget = self._widgets[self._transitioning_from]
        old_widget.hide()
        old_widget.move(0, 0)

        # Snap the incoming widget into place
        new_widget = self._widgets[self._transitioning_to]
        new_widget.setGeometry(0, 0, self.width(), self.height())

        self._restore_hscroll_policies()
        self._transitioning_from = -1
        self._transitioning_to = -1

    def _on_transition_finished(self) -> None:
        if self._animation_group is None:
            return

        old_widget = self._widgets[self._transitioning_from]
        old_widget.hide()
        old_widget.move(0, 0)

        new_widget = self._widgets[self._transitioning_to]
        new_widget.setGeometry(0, 0, self.width(), self.height())

        self._restore_hscroll_policies()
        self._animation_group.deleteLater()
        self._animation_group = None
        self._transitioning_from = -1
        self._transitioning_to = -1

    def _restore_hscroll_policies(self) -> None:
        for sa, policy in self._saved_hscroll_policies:
            sa.setHorizontalScrollBarPolicy(policy)
        self._saved_hscroll_policies.clear()

    # -- geometry management -------------------------------------------------

    def sizeHint(self) -> QSize:
        """Return the max size hint across all children (matches QStackedWidget)."""
        w, h = 0, 0
        for widget in self._widgets:
            hint = widget.sizeHint()
            if hint.isValid():
                w = max(w, hint.width())
                h = max(h, hint.height())
        return QSize(w, h) if w > 0 and h > 0 else QSize(200, 200)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._animation_group is not None:
            self._finalize_transition()
        if 0 <= self._current_index < len(self._widgets):
            self._widgets[self._current_index].setGeometry(
                0,
                0,
                self.width(),
                self.height(),
            )
