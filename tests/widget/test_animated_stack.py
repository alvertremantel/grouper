"""Unit tests for AnimatedViewStack — validates slide transitions,
direction logic, size policy, and the horizontal axis used by calendar sub-views.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QLabel, QSizePolicy, QVBoxLayout, QWidget

sys.path.insert(0, str(Path(__file__).parent.parent))

from grouper.ui.animated_stack import AnimatedViewStack, SlideAxis


@pytest.fixture
def stack_h(qapp: QApplication) -> AnimatedViewStack:
    """Horizontal AnimatedViewStack with 4 child widgets (like calendar views)."""
    s = AnimatedViewStack(axis=SlideAxis.HORIZONTAL)
    s.resize(800, 600)
    for label in ("Month", "Week", "Agenda", "Timeline"):
        w = QLabel(label)
        s.addWidget(w)
    return s


@pytest.fixture
def stack_v(qapp: QApplication) -> AnimatedViewStack:
    """Vertical AnimatedViewStack with 3 child widgets."""
    s = AnimatedViewStack(axis=SlideAxis.VERTICAL)
    s.resize(800, 600)
    for label in ("View A", "View B", "View C"):
        s.addWidget(QLabel(label))
    return s


# ── Construction & size policy ──────────────────────────────────────


class TestConstruction:
    def test_default_axis_is_vertical(self, qapp: QApplication) -> None:
        s = AnimatedViewStack()
        assert s.axis == SlideAxis.VERTICAL

    def test_horizontal_axis(self, stack_h: AnimatedViewStack) -> None:
        assert stack_h.axis == SlideAxis.HORIZONTAL

    def test_size_policy_is_expanding(self, stack_h: AnimatedViewStack) -> None:
        sp = stack_h.sizePolicy()
        assert sp.horizontalPolicy() == QSizePolicy.Policy.Expanding
        assert sp.verticalPolicy() == QSizePolicy.Policy.Expanding

    def test_size_hint_reflects_children(self, qapp: QApplication) -> None:
        s = AnimatedViewStack()
        w1 = QWidget()
        w1.setMinimumSize(100, 50)
        w2 = QWidget()
        w2.setMinimumSize(200, 150)
        s.addWidget(w1)
        s.addWidget(w2)
        hint = s.sizeHint()
        assert hint.width() >= 100
        assert hint.height() >= 50


# ── addWidget / basic state ─────────────────────────────────────────


class TestAddWidget:
    def test_first_widget_is_current(self, qapp: QApplication) -> None:
        s = AnimatedViewStack()
        s.addWidget(QLabel("only"))
        assert s.currentIndex() == 0
        assert s.count() == 1

    def test_subsequent_widgets_hidden(self, stack_h: AnimatedViewStack) -> None:
        # Only the first widget (index 0) should be visible
        assert not stack_h.widget(0).isHidden()
        for i in range(1, stack_h.count()):
            assert stack_h.widget(i).isHidden()

    def test_count(self, stack_h: AnimatedViewStack) -> None:
        assert stack_h.count() == 4

    def test_widget_returns_correct_child(self, stack_h: AnimatedViewStack) -> None:
        for i in range(4):
            assert stack_h.widget(i) is not None
        assert stack_h.widget(99) is None


# ── setCurrentIndex (no-animation path) ─────────────────────────────


class TestSwitchNoAnimation:
    """Test view switching with animations disabled (instant swap)."""

    @patch("grouper.ui.animated_stack.get_config")
    def test_switch_forward_hides_old_shows_new(self, mock_cfg, stack_h: AnimatedViewStack) -> None:
        mock_cfg.return_value.animations_enabled = False
        stack_h.setCurrentIndex(2)  # Month -> Agenda
        assert stack_h.currentIndex() == 2
        assert stack_h.widget(0).isHidden()
        assert not stack_h.widget(2).isHidden()

    @patch("grouper.ui.animated_stack.get_config")
    def test_switch_backward(self, mock_cfg, stack_h: AnimatedViewStack) -> None:
        mock_cfg.return_value.animations_enabled = False
        stack_h.setCurrentIndex(3)
        stack_h.setCurrentIndex(1)  # Timeline -> Week
        assert stack_h.currentIndex() == 1
        assert not stack_h.widget(1).isHidden()
        assert stack_h.widget(3).isHidden()

    @patch("grouper.ui.animated_stack.get_config")
    def test_switch_to_same_index_is_noop(self, mock_cfg, stack_h: AnimatedViewStack) -> None:
        mock_cfg.return_value.animations_enabled = False
        stack_h.setCurrentIndex(0)
        assert stack_h.currentIndex() == 0

    @patch("grouper.ui.animated_stack.get_config")
    def test_switch_out_of_range_is_noop(self, mock_cfg, stack_h: AnimatedViewStack) -> None:
        mock_cfg.return_value.animations_enabled = False
        stack_h.setCurrentIndex(99)
        assert stack_h.currentIndex() == 0
        stack_h.setCurrentIndex(-1)
        assert stack_h.currentIndex() == 0

    @patch("grouper.ui.animated_stack.get_config")
    def test_current_changed_signal(self, mock_cfg, stack_h: AnimatedViewStack) -> None:
        mock_cfg.return_value.animations_enabled = False
        received: list[int] = []
        stack_h.currentChanged.connect(received.append)
        stack_h.setCurrentIndex(2)
        assert received == [2]


# ── setCurrentIndex (animation path) ────────────────────────────────


class TestSwitchWithAnimation:
    """Test that animation starts with correct direction and offsets."""

    @patch("grouper.ui.animated_stack.get_config")
    def test_horizontal_forward_starts_animation(
        self, mock_cfg, stack_h: AnimatedViewStack
    ) -> None:
        mock_cfg.return_value.animations_enabled = True
        stack_h.setCurrentIndex(1)  # Month -> Week (forward)
        # Animation should be in flight
        assert stack_h._animation_group is not None
        assert stack_h._transitioning_from == 0
        assert stack_h._transitioning_to == 1

    @patch("grouper.ui.animated_stack.get_config")
    def test_horizontal_backward_starts_animation(
        self, mock_cfg, stack_h: AnimatedViewStack
    ) -> None:
        mock_cfg.return_value.animations_enabled = True
        # First jump to index 3 without animation
        mock_cfg.return_value.animations_enabled = False
        stack_h.setCurrentIndex(3)
        mock_cfg.return_value.animations_enabled = True
        stack_h.setCurrentIndex(1)  # Timeline -> Week (backward)
        assert stack_h._animation_group is not None
        assert stack_h._transitioning_from == 3
        assert stack_h._transitioning_to == 1

    @patch("grouper.ui.animated_stack.get_config")
    def test_vertical_forward_uses_vertical_offset(
        self, mock_cfg, stack_v: AnimatedViewStack
    ) -> None:
        mock_cfg.return_value.animations_enabled = True
        stack_v.setCurrentIndex(1)
        assert stack_v._animation_group is not None

    @patch("grouper.ui.animated_stack.get_config")
    def test_rapid_switch_finalizes_previous(self, mock_cfg, stack_h: AnimatedViewStack) -> None:
        """Rapid clicking should cancel in-flight animation cleanly."""
        mock_cfg.return_value.animations_enabled = True
        stack_h.setCurrentIndex(1)
        assert stack_h._animation_group is not None
        # Switch again before first animation finishes
        stack_h.setCurrentIndex(3)
        # Should now be transitioning 1->3, previous finalized
        assert stack_h.currentIndex() == 3
        assert stack_h._transitioning_from == 1
        assert stack_h._transitioning_to == 3


# ── finalize / resize ───────────────────────────────────────────────


class TestFinalizeAndResize:
    @patch("grouper.ui.animated_stack.get_config")
    def test_finalize_snaps_to_target(self, mock_cfg, stack_h: AnimatedViewStack) -> None:
        mock_cfg.return_value.animations_enabled = True
        stack_h.setCurrentIndex(2)
        stack_h._finalize_transition()
        assert stack_h._animation_group is None
        assert not stack_h.widget(2).isHidden()
        assert stack_h.widget(0).isHidden()
        assert stack_h.widget(2).pos() == QPoint(0, 0)

    @patch("grouper.ui.animated_stack.get_config")
    def test_resize_during_animation_finalizes(
        self, mock_cfg, stack_h: AnimatedViewStack, qapp: QApplication
    ) -> None:
        mock_cfg.return_value.animations_enabled = True
        stack_h.show()
        qapp.processEvents()
        stack_h.setCurrentIndex(1)
        assert stack_h._animation_group is not None
        stack_h.resize(900, 700)
        qapp.processEvents()
        # Resize should have finalized the transition
        assert stack_h._animation_group is None
        assert stack_h.currentIndex() == 1
        stack_h.close()


# ── Layout integration (the actual bug) ─────────────────────────────


class TestLayoutIntegration:
    """Verify AnimatedViewStack gets proper size when placed in a layout
    (the root cause of the calendar animation not being visible)."""

    @patch("grouper.ui.animated_stack.get_config")
    def test_stack_in_layout_gets_nonzero_size(self, mock_cfg, qapp: QApplication) -> None:
        mock_cfg.return_value.animations_enabled = True
        container = QWidget()
        container.resize(800, 600)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        stack = AnimatedViewStack(axis=SlideAxis.HORIZONTAL)
        for label in ("A", "B", "C"):
            stack.addWidget(QLabel(label))
        layout.addWidget(stack)

        container.show()
        qapp.processEvents()

        # The stack must have nonzero size for animation offsets to work
        assert stack.width() > 0, f"Stack width is {stack.width()}, expected > 0"
        assert stack.height() > 0, f"Stack height is {stack.height()}, expected > 0"

        container.close()


# ── Axis property ───────────────────────────────────────────────────


class TestAxisProperty:
    def test_axis_setter(self, stack_h: AnimatedViewStack) -> None:
        assert stack_h.axis == SlideAxis.HORIZONTAL
        stack_h.axis = SlideAxis.VERTICAL
        assert stack_h.axis == SlideAxis.VERTICAL
