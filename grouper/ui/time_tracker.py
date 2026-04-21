"""
time_tracker.py — Time tracking view.

Shows activities, active sessions, and start/stop/pause/resume controls.
Activities are distinct from projects (which hold tasks).

Layout:
  Left panel  — 4 quadrants for activity selection (each quadrant has a group selector)
  Right panel — two sections:
      • Active Sessions  — green (running) / amber (paused) cards
      • Background Activity — single purple-accent card or placeholder
"""

import time as _time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..database import (
    get_active_sessions,
    get_all_groups,
    get_setting,
    pause_session,
    resume_session,
    set_setting,
    start_session,
    stop_session,
)
from ..database.activities import get_activity
from ..database.connection import get_notifier
from .activity_card import ActivityQuadrant, GridMode
from .activity_config import ActivityConfigPanel
from .animated_card import AnimatedCard, animate_slide_transition
from .animated_stack import AnimatedViewStack, SlideAxis
from .dialogs import CreateActivityDialog, StopSessionDialog
from .session_card import SessionCard
from .widgets import clear_layout, reconnect


class TimeTrackerView(QWidget):
    """Main time tracking interface."""

    session_changed = Signal()  # emitted after start/stop/pause/resume

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("timeTrackerView")
        self._fg_session_cards: dict = {}  # session_id -> (AnimatedCard, timer_label)
        self._fg_session_state: dict = {}  # session_id -> is_paused
        self._bg_session_card = None  # (session_id, (AnimatedCard, timer_label))
        self._bg_pause_state: bool | None = None
        self._bg_pending_transition: bool = False
        self._pending_transitions: set = set()  # session_ids mid pause/resume slide
        self._slide_anims: list = []  # keep QPropertyAnimation refs alive
        self._build()
        self._show_bg_placeholder()
        self._dirty: bool = False
        self._last_refresh_ts: float = 0.0
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(50)
        self._refresh_timer.timeout.connect(self.refresh)
        get_notifier().data_changed.connect(
            self._on_data_changed, Qt.ConnectionType.QueuedConnection
        )
        self.refresh()

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._update_timers)
        self._tick.start(1000)

    def _on_data_changed(self) -> None:
        if self.isVisible():
            # Skip if refresh() was called very recently (e.g. from
            # _on_activity_click).  The queued data_changed signal from the DB
            # commit would trigger a redundant rebuild that disrupts
            # AnimatedCard slide-in animations.
            if _time.monotonic() - self._last_refresh_ts < 0.1:
                return
            if not self._refresh_timer.isActive():
                self._refresh_timer.start()
        else:
            self._dirty = True

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_quadrants()
        if self._dirty:
            self._dirty = False
            self.refresh()

    # -- build ---------------------------------------------------------------

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._inner_stack = AnimatedViewStack(axis=SlideAxis.HORIZONTAL)
        root.addWidget(self._inner_stack)

        # -- Page 0: time tracker content ------------------------------------
        tracker_page = QWidget()
        outer = QVBoxLayout(tracker_page)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(20)

        # Header row
        header = QHBoxLayout()
        title = QLabel("Time Tracker")
        title.setProperty("heading", True)
        header.addWidget(title)
        header.addStretch()

        edit_act_btn = QPushButton("Edit Activities")
        edit_act_btn.clicked.connect(self._edit_activities)
        header.addWidget(edit_act_btn)

        new_act_btn = QPushButton("+ New Activity")
        new_act_btn.setProperty("primary", True)
        new_act_btn.clicked.connect(self._create_activity)
        header.addWidget(new_act_btn)
        outer.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: activity grid ─────────────────────────────────────────────
        left = QFrame()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 8, 0)
        left_lay.setSpacing(10)

        act_header_row = QHBoxLayout()
        act_header_row.setContentsMargins(0, 0, 0, 0)
        act_header = QLabel("ACTIVITIES")
        act_header.setObjectName("sectionHeader")
        act_header_row.addWidget(act_header)
        act_header_row.addStretch()
        self._grid_toggle_btn = QPushButton()
        self._grid_toggle_btn.setObjectName("gridToggleBtn")
        self._grid_toggle_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._grid_toggle_btn.clicked.connect(self._toggle_grid_mode)
        act_header_row.addWidget(self._grid_toggle_btn)
        left_lay.addLayout(act_header_row)

        self._quadrant_grid = QGridLayout()
        self._quadrant_grid.setSpacing(12)

        self._quadrants = []
        for _ in range(4):
            q = ActivityQuadrant()
            q.activity_selected.connect(self._on_activity_click)
            self._quadrants.append(q)

        self._quadrant_grid.addWidget(self._quadrants[0], 0, 0)
        self._quadrant_grid.addWidget(self._quadrants[1], 0, 1)
        self._quadrant_grid.addWidget(self._quadrants[2], 1, 0)
        self._quadrant_grid.addWidget(self._quadrants[3], 1, 1)

        left_lay.addLayout(self._quadrant_grid)

        self._grid_mode: GridMode = get_setting("activity_grid_mode", "2x2")  # type: ignore[assignment]
        self._apply_grid_mode(self._grid_mode, save=False)
        splitter.addWidget(left)

        # ── Right: sessions panel ─────────────────────────────────────────
        right = QFrame()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(8, 0, 0, 0)
        right_lay.setSpacing(16)

        # ─ Active Sessions section ─
        active_header = QLabel("ACTIVE SESSIONS")
        active_header.setObjectName("sectionHeader")
        right_lay.addWidget(active_header)

        active_scroll = QScrollArea()
        active_scroll.setWidgetResizable(True)
        active_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        active_scroll.setFrameShape(QFrame.Shape.NoFrame)
        active_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._active_container = QWidget()
        self._active_layout = QVBoxLayout(self._active_container)
        self._active_layout.setContentsMargins(0, 0, 0, 0)
        self._active_layout.setSpacing(12)
        self._active_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        active_scroll.setWidget(self._active_container)
        right_lay.addWidget(active_scroll, stretch=1)

        # ─ Background Activity section ─
        bg_header = QLabel("BACKGROUND ACTIVITY")
        bg_header.setObjectName("sectionHeader")
        right_lay.addWidget(bg_header)

        self._bg_container = QWidget()
        self._bg_layout = QVBoxLayout(self._bg_container)
        self._bg_layout.setContentsMargins(0, 0, 0, 0)
        self._bg_layout.setSpacing(0)
        right_lay.addWidget(self._bg_container)

        splitter.addWidget(right)
        splitter.setSizes([500, 400])
        outer.addWidget(splitter)

        self._inner_stack.addWidget(tracker_page)  # index 0

        # -- Page 1: activity config panel -----------------------------------
        self._config_panel = ActivityConfigPanel()
        self._config_panel.closed.connect(self._close_config)
        self._config_panel.data_changed.connect(self._refresh_quadrants)
        self._inner_stack.addWidget(self._config_panel)  # index 1

    # -- grid mode -----------------------------------------------------------

    def _apply_grid_mode(self, mode: GridMode, *, save: bool = True) -> None:
        self._grid_mode = mode
        self._grid_toggle_btn.setText("2x2" if mode == "2x2" else "1x2")
        if mode == "2x2":
            self._quadrants[2].show()
            self._quadrants[3].show()
            self._quadrant_grid.addWidget(self._quadrants[0], 0, 0)
            self._quadrant_grid.addWidget(self._quadrants[1], 0, 1)
            self._quadrant_grid.addWidget(self._quadrants[2], 1, 0)
            self._quadrant_grid.addWidget(self._quadrants[3], 1, 1)
        else:
            self._quadrants[2].hide()
            self._quadrants[3].hide()
            self._quadrant_grid.addWidget(self._quadrants[0], 0, 0)
            self._quadrant_grid.addWidget(self._quadrants[1], 1, 0)
        if save:
            set_setting("activity_grid_mode", mode)

    def _toggle_grid_mode(self) -> None:
        self._apply_grid_mode("1x2" if self._grid_mode == "2x2" else "2x2")

    # -- actions -------------------------------------------------------------

    def _create_activity(self):
        from ..database import create_activity

        dlg = CreateActivityDialog(self)
        if dlg.exec():
            vals = dlg.get_values()
            if vals["name"]:
                create_activity(**vals)
                self.refresh()

    def _edit_activities(self) -> None:
        """Slide to the activity configuration panel."""
        self._config_panel.refresh()
        self._inner_stack.setCurrentIndex(1)

    def _close_config(self) -> None:
        """Slide back from config panel to the time tracker."""
        self._inner_stack.setCurrentIndex(0)
        self.refresh()
        self.session_changed.emit()

    def _on_activity_click(self, name: str):
        if name:
            act = get_activity(name)
            if act and act.is_background:
                # Enforce single background session — silently stop any existing one
                for s in get_active_sessions():
                    s_act = get_activity(s.activity_name)
                    if s_act and s_act.is_background:
                        stop_session(s.activity_name, "")
            start_session(name)
            self.refresh()
            self.session_changed.emit()

    def _pause(self, session_id: int):
        try:
            pause_session(session_id)
            self._rebuild_active_cards()
            self.session_changed.emit()
        except Exception:
            import traceback

            traceback.print_exc()

    def _resume(self, session_id: int):
        try:
            resume_session(session_id)
            self._rebuild_active_cards()
            self.session_changed.emit()
        except Exception:
            import traceback

            traceback.print_exc()

    # -- signal wiring -------------------------------------------------------

    def _connect_session_signals(self, card: SessionCard) -> None:
        """Connect a SessionCard's signals to view handler methods."""
        card.pause_requested.connect(self._pause)
        card.resume_requested.connect(self._resume)
        card.stop_requested.connect(self._show_stop_ui)

    # -- refresh -------------------------------------------------------------

    def refresh(self) -> None:
        self._last_refresh_ts = _time.monotonic()
        self._refresh_quadrants()
        self._rebuild_active_cards()

    def _refresh_quadrants(self):
        groups = get_all_groups()
        for q in self._quadrants:
            q.refresh_groups(groups)

    def _categorize_sessions(self, sessions):
        """Split sessions into (fg_list, bg_session_or_None)."""
        fg, bg = [], []
        for s in sessions:
            act = get_activity(s.activity_name)
            if act and act.is_background:
                bg.append(s)
            else:
                fg.append(s)
        return fg, (bg[0] if bg else None)

    def _update_timers(self):
        """Update timer labels; rebuild if any structural change (IDs or pause state)."""
        sessions = get_active_sessions()
        fg_sessions, bg_session = self._categorize_sessions(sessions)

        new_fg_state = {s.id: s.is_paused for s in fg_sessions}
        new_bg_id = bg_session.id if bg_session else None
        old_bg_id = self._bg_session_card[0] if self._bg_session_card else None
        new_bg_paused = bg_session.is_paused if bg_session else None

        if (
            new_fg_state != self._fg_session_state
            or new_bg_id != old_bg_id
            or new_bg_paused != self._bg_pause_state
        ):
            self._rebuild_active_cards()
            return

        # No structural change — update timer text in-place
        for s in fg_sessions:
            if s.id in self._fg_session_cards:
                _, timer_lbl = self._fg_session_cards[s.id]
                if timer_lbl is None and s.id not in self._pending_transitions:
                    self._rebuild_active_cards()
                    return
                if timer_lbl:
                    try:
                        timer_lbl.setText(s.format_duration())
                    except RuntimeError:
                        self._rebuild_active_cards()
                        return

        if bg_session and self._bg_session_card:
            _, (_, timer_lbl) = self._bg_session_card
            if timer_lbl:
                try:
                    timer_lbl.setText(bg_session.format_duration())
                except RuntimeError:
                    self._rebuild_active_cards()

    def _rebuild_active_cards(self):
        """Rebuild session cards. Evicts stale cards (gone or pause-state changed)."""
        sessions = get_active_sessions()
        fg_sessions, bg_session = self._categorize_sessions(sessions)

        new_fg_ids = {s.id for s in fg_sessions}
        new_fg_state = {s.id: s.is_paused for s in fg_sessions}

        # Evict foreground cards that are gone or whose pause state changed
        for sid in list(self._fg_session_cards.keys()):
            if sid in self._pending_transitions:
                if sid not in new_fg_ids:
                    # Session ended while animation was in-flight — clean up.
                    clip, _ = self._fg_session_cards.pop(sid)
                    self._pending_transitions.discard(sid)
                    clip.hide()
                    clip.deleteLater()
                continue  # mid-transition — leave it alone
            if sid not in new_fg_ids:
                animated, _ = self._fg_session_cards.pop(sid)
                animated.slide_out(lambda cw=animated: self._remove_card(cw))
            elif self._fg_session_state.get(sid) != new_fg_state.get(sid):
                animated, _ = self._fg_session_cards[sid]  # don't pop yet
                new_session = next((s for s in fg_sessions if s.id == sid), None)
                if new_session is None:
                    continue
                self._pending_transitions.add(sid)
                self._start_pause_transition(sid, animated, new_session)

        # Commit new state
        self._fg_session_state = new_fg_state

        # Rebuild foreground layout
        existing = {cw for cw, _ in self._fg_session_cards.values()}
        clear_layout(self._active_layout, keep=existing)

        if not fg_sessions:
            lbl = QLabel("No active sessions\nClick an activity to start tracking")
            lbl.setObjectName("placeholderText")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._active_layout.addWidget(lbl)
        else:
            for i, s in enumerate(fg_sessions):
                if s.id in self._pending_transitions:
                    # Re-insert transition widget (clear loop removed it from layout)
                    trans_widget, _ = self._fg_session_cards[s.id]
                    self._active_layout.insertWidget(i, trans_widget)
                    continue
                if s.id in self._fg_session_cards:
                    animated, _ = self._fg_session_cards[s.id]
                    if self._active_layout.indexOf(animated) != i:
                        self._active_layout.insertWidget(i, animated)
                else:
                    card = SessionCard(s, is_background=False)
                    self._connect_session_signals(card)
                    animated = AnimatedCard(card, parent=self._active_container)
                    self._active_layout.insertWidget(i, animated)
                    self._fg_session_cards[s.id] = (animated, card.timer_lbl)

        # Rebuild background section
        new_bg_id = bg_session.id if bg_session else None
        old_bg_id = self._bg_session_card[0] if self._bg_session_card else None
        new_bg_paused = bg_session.is_paused if bg_session else None

        if new_bg_id != old_bg_id:
            if self._bg_session_card:
                _, (old_wrapper, _) = self._bg_session_card
                old_wrapper.slide_out(lambda cw=old_wrapper: self._remove_card(cw))
                self._bg_session_card = None
                self._bg_pause_state = None

            clear_layout(self._bg_layout)

            if bg_session:
                card = SessionCard(bg_session, is_background=True)
                self._connect_session_signals(card)
                animated = AnimatedCard(card, parent=self._bg_container)
                self._bg_layout.addWidget(animated)
                timer_lbl = card.findChild(QLabel, "timerLabelBackground") or card.findChild(
                    QLabel, "timerLabelBackgroundPaused"
                )
                self._bg_session_card = (bg_session.id, (animated, timer_lbl))
            else:
                self._show_bg_placeholder()
            self._bg_pause_state = new_bg_paused
        elif (
            new_bg_paused != self._bg_pause_state
            and self._bg_session_card
            and not self._bg_pending_transition
        ):
            _, (old_animated, _) = self._bg_session_card
            self._start_bg_pause_transition(bg_session, old_animated)
            self._bg_pause_state = new_bg_paused

    def _start_pause_transition(self, sid: int, old_animated: AnimatedCard, new_session) -> None:
        """Slide from active->paused (or paused->active) card using horizontal animation."""
        new_card = SessionCard(new_session, is_background=False)
        self._connect_session_signals(new_card)

        # Capture size BEFORE reparenting (old_animated still has its layout geometry).
        card_w = old_animated.width()
        card_h = max(old_animated.height(), old_animated.sizeHint().height(), 60)
        if card_w <= 0:
            card_w = self._active_container.width()

        idx = self._active_layout.indexOf(old_animated)

        new_animated = AnimatedCard(new_card, animate=False)
        clip, group = animate_slide_transition(
            self._active_container,
            old_animated,
            new_animated,
            card_w,
            card_h,
        )

        # Register clip as layout placeholder; also keeps it alive through clear loop.
        self._active_layout.insertWidget(idx, clip)
        self._fg_session_cards[sid] = (clip, None)  # type: ignore[assignment]

        def _on_done():
            self._slide_anims = [g for g in self._slide_anims if g is not group]
            if sid not in self._pending_transitions:
                # Session was evicted mid-animation; widgets already cleaned up.
                return

            # Re-find clip's position — it may have shifted if layout changed mid-anim.
            current_idx = self._active_layout.indexOf(clip)
            insert_at = current_idx if current_idx >= 0 else idx

            new_animated.setParent(self._active_container)
            new_animated.setMinimumSize(0, 0)
            new_animated.setMaximumSize(16777215, 16777215)
            new_animated.show()
            self._active_layout.insertWidget(insert_at, new_animated)

            clip.hide()
            clip.deleteLater()
            old_animated.hide()
            old_animated.deleteLater()

            self._fg_session_cards[sid] = (new_animated, new_card.timer_lbl)
            self._pending_transitions.discard(sid)

        group.finished.connect(_on_done)
        group.start()
        self._slide_anims.append(group)

    def _start_bg_pause_transition(self, new_session, old_animated: AnimatedCard) -> None:
        """Horizontal slide transition for background card pause/resume."""
        self._bg_pending_transition = True

        new_card = SessionCard(new_session, is_background=True)
        self._connect_session_signals(new_card)

        card_w = old_animated.width()
        card_h = max(old_animated.height(), old_animated.sizeHint().height(), 60)
        if card_w <= 0:
            card_w = self._bg_container.width()

        new_animated = AnimatedCard(new_card, animate=False)
        clip, group = animate_slide_transition(
            self._bg_container,
            old_animated,
            new_animated,
            card_w,
            card_h,
        )

        # Clear bg layout and insert clip
        clear_layout(self._bg_layout, keep={clip, old_animated})
        self._bg_layout.addWidget(clip)

        def _on_done():
            self._slide_anims = [g for g in self._slide_anims if g is not group]
            if self._bg_session_card is None or self._bg_session_card[0] != new_session.id:
                # Session was stopped or changed mid-animation; clean up.
                self._bg_pending_transition = False
                clip.hide()
                clip.deleteLater()
                old_animated.hide()
                old_animated.deleteLater()
                new_animated.hide()
                new_animated.deleteLater()
                return

            new_animated.setParent(self._bg_container)
            new_animated.setMinimumSize(0, 0)
            new_animated.setMaximumSize(16777215, 16777215)
            new_animated.show()

            clip.hide()
            clip.deleteLater()
            old_animated.hide()
            old_animated.deleteLater()

            clear_layout(self._bg_layout, keep={new_animated})
            self._bg_layout.addWidget(new_animated)

            timer_lbl = new_card.findChild(QLabel, "timerLabelBackground") or new_card.findChild(
                QLabel, "timerLabelBackgroundPaused"
            )
            self._bg_session_card = (new_session.id, (new_animated, timer_lbl))
            self._bg_pending_transition = False

        group.finished.connect(_on_done)
        group.start()
        self._slide_anims.append(group)

    def _show_bg_placeholder(self):
        placeholder = QFrame()
        placeholder.setObjectName("backgroundPlaceholder")
        ph_lay = QHBoxLayout(placeholder)
        ph_lay.setContentsMargins(16, 12, 16, 12)
        dot = QLabel("○")
        dot.setObjectName("statusDotInactive")
        ph_lay.addWidget(dot)
        msg = QLabel("No background activity")
        msg.setObjectName("smallMuted")
        ph_lay.addWidget(msg)
        ph_lay.addStretch()
        self._bg_layout.addWidget(placeholder)

    def _remove_card(self, widget):
        widget.hide()
        widget.deleteLater()

    # -- stop logic ----------------------------------------------------------

    def _show_stop_ui(self, card: SessionCard, activity_name: str):
        """Show inline stop UI with note input, or dialog if card is too narrow."""
        if not card.use_inline_stop:
            self._confirm_stop(card, activity_name, notes="")
            return

        middle_box = card.middle_box
        note_input = card.note_input
        confirm_btn = card.confirm_stop_btn
        if middle_box is None or note_input is None or confirm_btn is None:
            self._stop_with_dialog(card, activity_name)
            return

        if middle_box.isVisible():
            self._confirm_stop(card, activity_name, notes="")
            return

        middle_box.setVisible(True)
        note_input.setFocus()

        reconnect(confirm_btn.clicked, lambda: self._confirm_stop(card, activity_name))

    def _stop_with_dialog(self, card: SessionCard, activity_name: str):
        """Show the StopSessionDialog for note entry."""
        dlg = StopSessionDialog(activity_name, parent=self)
        if dlg.exec():
            vals = dlg.get_values()
            session_id = card.session_id
            from ..database import stop_session

            stop_session(activity_name, vals["notes"], vals.get("task_id"))
            self.session_changed.emit()

            if session_id in self._fg_session_cards:
                del self._fg_session_cards[session_id]
            if self._bg_session_card and self._bg_session_card[0] == session_id:
                self._bg_session_card = None
                self._bg_pause_state = None
                self._bg_pending_transition = False

            # Suppress rebuilds during slide-out: prevent the queued DB
            # data_changed signal (50ms) and the 1s _update_timers tick
            # from calling _rebuild_active_cards before the animation ends.
            self._fg_session_state.pop(session_id, None)
            self._last_refresh_ts = _time.monotonic()

            animated = card.parent()
            if isinstance(animated, AnimatedCard):
                animated.slide_out(lambda: self._rebuild_active_cards())
            else:
                self._rebuild_active_cards()

    def _confirm_stop(
        self, card: SessionCard, activity_name: str, notes: str | None = None
    ) -> None:
        """Handle stop confirmation from inline UI."""
        if notes is None:
            notes = card.note_input.text().strip() if card.note_input else ""

        session_id = card.session_id

        from ..database import stop_session

        # Empty string is intentional — DB schema uses DEFAULT '' and
        # stop_session signature is notes: str = "".  NULL is not expected.
        stop_session(activity_name, notes if notes else "", None)
        self.session_changed.emit()

        if session_id in self._fg_session_cards:
            del self._fg_session_cards[session_id]
        if self._bg_session_card and self._bg_session_card[0] == session_id:
            self._bg_session_card = None
            self._bg_pause_state = None
            self._bg_pending_transition = False

        # Suppress rebuilds during slide-out: prevent the queued DB
        # data_changed signal (50ms) and the 1s _update_timers tick
        # from calling _rebuild_active_cards before the animation ends.
        self._fg_session_state.pop(session_id, None)
        self._last_refresh_ts = _time.monotonic()

        animated = card.parent()
        if isinstance(animated, AnimatedCard):
            animated.slide_out(lambda: self._rebuild_active_cards())
        else:
            self._rebuild_active_cards()
