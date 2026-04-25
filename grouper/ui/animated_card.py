"""animated_card.py — Animated session card wrapper + slide transition helper."""

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QTimer,
)
from PySide6.QtWidgets import QFrame, QSizePolicy, QVBoxLayout, QWidget

from ..config import get_config


class AnimatedCard(QFrame):
    """Wrapper that provides expand/collapse animations for session cards.

    Vertical axis (maximumHeight): used for start/stop transitions.
    Horizontal axis (maximumWidth): used for pause/resume transitions.
    """

    ANIMATION_DURATION = 250

    def __init__(self, card: QFrame, parent: QWidget | None = None, animate: bool = True):
        super().__init__(parent)
        self.card = card
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(card)

        # Vertical animation — start/stop axis
        self._on_finished_cb = None
        self._anim = QPropertyAnimation(self, b"maximumHeight")
        self._anim.setDuration(self.ANIMATION_DURATION)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_finished)

        if animate and get_config().animations_enabled:
            self.setMaximumHeight(0)
            QTimer.singleShot(50, self._animate_in)
        else:
            self.setMaximumHeight(16777215)

    def _on_finished(self):
        cb, self._on_finished_cb = self._on_finished_cb, None
        if cb:
            cb()

    def _animate_in(self):
        target = max(self.card.sizeHint().height(), 60)
        self._anim.stop()
        self._on_finished_cb = lambda: self.setMaximumHeight(16777215)
        self._anim.setStartValue(0)
        self._anim.setEndValue(target)
        self._anim.start()

    def slide_in(self):
        self._animate_in()

    def slide_out(self, on_finished=None):
        if not get_config().animations_enabled:
            self.setMaximumHeight(0)
            if on_finished:
                on_finished()
            return
        self._anim.stop()
        self._on_finished_cb = on_finished
        self._anim.setStartValue(self.height())
        self._anim.setEndValue(0)
        self._anim.start()

    def get_card(self) -> QFrame:
        return self.card


def animate_slide_transition(
    parent: QWidget,
    old_animated: QWidget,
    new_animated: AnimatedCard,
    card_w: int,
    card_h: int,
    duration: int = AnimatedCard.ANIMATION_DURATION,
) -> tuple[QWidget, QParallelAnimationGroup]:
    """Create a horizontal slide transition between two card widgets.

    Sets up a clip container with old_animated at (0,0) and new_animated at
    (card_w, 0). Returns (clip_widget, animation_group). The caller is
    responsible for inserting the clip into a layout, connecting the group's
    ``finished`` signal, and calling ``group.start()``.
    """
    if not get_config().animations_enabled:
        # Snap positions directly — no animation objects needed
        clip = QWidget(parent)
        clip.setFixedHeight(card_h)
        clip.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        old_animated.setParent(clip)
        old_animated.setGeometry(-card_w, 0, card_w, card_h)
        new_animated.setParent(clip)
        new_animated.setGeometry(0, 0, card_w, card_h)
        new_animated.show()
        group = QParallelAnimationGroup(parent)
        return clip, group

    clip = QWidget(parent)
    clip.setFixedHeight(card_h)
    clip.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    old_animated.setParent(clip)
    old_animated.setGeometry(0, 0, card_w, card_h)

    new_animated.setParent(clip)
    new_animated.setGeometry(card_w, 0, card_w, card_h)
    new_animated.show()

    old_anim = QPropertyAnimation(old_animated, b"pos")
    old_anim.setDuration(duration)
    old_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    old_anim.setStartValue(QPoint(0, 0))
    old_anim.setEndValue(QPoint(-card_w, 0))

    new_anim = QPropertyAnimation(new_animated, b"pos")
    new_anim.setDuration(duration)
    new_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    new_anim.setStartValue(QPoint(card_w, 0))
    new_anim.setEndValue(QPoint(0, 0))

    group = QParallelAnimationGroup(parent)
    group.addAnimation(old_anim)
    group.addAnimation(new_anim)

    return clip, group
