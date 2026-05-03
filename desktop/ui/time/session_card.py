"""session_card.py — Typed session card widget with signals."""

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...config import get_config
from ...models import Session
from ...styles import theme_colors
from ..shared.base_card import BaseCard
from ..shared.icons import get_icon


class SessionCard(BaseCard):
    """A styled session card for an active or paused session.

    Emits signals for pause/resume/stop instead of calling methods directly,
    so the parent view can wire them up.
    """

    pause_requested = Signal(int)  # session_id
    resume_requested = Signal(int)  # session_id
    stop_requested = Signal(object, str)  # (self, activity_name)

    def __init__(self, session: Session, *, is_background: bool, parent: QWidget | None = None):
        # Default object name is "activeSessionCard"; _build() overrides it for
        # background/paused states. Passing it here as the initial value avoids
        # a flash of the wrong object name before _build() is called.
        super().__init__(parent, object_name="activeSessionCard")
        self.session_id: int = session.id  # type: ignore[assignment]
        self.timer_lbl: QLabel | None = None
        self.use_inline_stop: bool = True
        self.middle_box: QFrame | None = None
        self.note_input: QLineEdit | None = None
        self.confirm_stop_btn: QPushButton | None = None
        self.skip_label: QLabel | None = None
        self._build(session, is_background)

    def _build(self, s: Session, is_background: bool) -> None:
        chip_text = theme_colors(get_config().theme)["chip_text"]

        if is_background:
            self.setObjectName("backgroundCardPaused" if s.is_paused else "backgroundCard")
        elif s.is_paused:
            self.setObjectName("pausedSessionCard")
        else:
            self.setObjectName("activeSessionCard")

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)

        # === LEFT BOX ===
        left_box = QVBoxLayout()
        left_box.setSpacing(6)

        left_top = QHBoxLayout()
        left_top.setSpacing(8)

        if is_background:
            dot_char, dot_id = "●", ("statusDotPaused" if s.is_paused else "statusDotBackground")
        elif s.is_paused:
            dot_char, dot_id = "●", "statusDotPaused"
        else:
            dot_char, dot_id = "●", "statusDotActive"

        dot = QLabel(dot_char)
        dot.setObjectName(dot_id)
        dot.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        left_top.addWidget(dot)

        name_lbl = QLabel(s.activity_name)
        name_lbl.setObjectName("nameLabel")
        left_top.addWidget(name_lbl)
        left_box.addLayout(left_top)

        top_row.addLayout(left_box, 1)

        # === RIGHT BOX (timer only) ===
        right_box = QVBoxLayout()
        right_box.setSpacing(6)

        timer_lbl = QLabel(s.format_duration())
        if is_background:
            timer_lbl.setObjectName(
                "timerLabelBackgroundPaused" if s.is_paused else "timerLabelBackground"
            )
        elif s.is_paused:
            timer_lbl.setObjectName("timerLabelPaused")
        else:
            timer_lbl.setObjectName("timerLabelActive")
        right_box.addWidget(timer_lbl)

        top_row.addLayout(right_box)
        main_lay.addLayout(top_row)

        # === BUTTON ROW (equal-width pause/resume + stop) ===
        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        button_row.setContentsMargins(0, 6, 0, 0)

        if s.is_paused:
            resume_btn = QPushButton("Resume")
            resume_btn.setIcon(get_icon("play", chip_text, size=20))
            resume_btn.setIconSize(QSize(20, 20))
            resume_btn.setObjectName("resumeButton")
            resume_btn.setProperty("primary", True)
            resume_btn.clicked.connect(
                lambda checked=False, sid=s.id: self.resume_requested.emit(sid)
            )
            button_row.addWidget(resume_btn, 1)
        else:
            pause_btn = QPushButton("Pause")
            pause_btn.setIcon(get_icon("pause", chip_text, size=20))
            pause_btn.setIconSize(QSize(20, 20))
            pause_btn.setObjectName("pauseButton")
            pause_btn.setProperty("caution", True)
            pause_btn.clicked.connect(
                lambda checked=False, sid=s.id: self.pause_requested.emit(sid)
            )
            button_row.addWidget(pause_btn, 1)

        stop_btn = QPushButton("Stop")
        stop_btn.setIcon(get_icon("stop", chip_text, size=20))
        stop_btn.setIconSize(QSize(20, 20))
        stop_btn.setObjectName("stopButton")
        stop_btn.setProperty("danger", True)
        stop_btn.clicked.connect(lambda: self.stop_requested.emit(self, s.activity_name))
        button_row.addWidget(stop_btn, 1)

        main_lay.addLayout(button_row)

        # === NOTE ROW (shown on first Stop click) ===
        self.use_inline_stop = not is_background or get_config().bg_notes_enabled

        if self.use_inline_stop:
            note_row = QFrame()
            note_row.setObjectName("noteRow")
            note_row.setVisible(False)
            note_hbox = QHBoxLayout(note_row)
            note_hbox.setContentsMargins(0, 8, 0, 0)
            note_hbox.setSpacing(6)

            self.note_input = QLineEdit()
            self.note_input.setPlaceholderText("Notes...")
            self.note_input.setMinimumWidth(0)
            self.note_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            note_hbox.addWidget(self.note_input, 1)

            self.confirm_stop_btn = QPushButton("Confirm")
            self.confirm_stop_btn.setProperty("primary", True)
            note_hbox.addWidget(self.confirm_stop_btn)

            self.skip_label = QLabel("Skip ↑")
            self.skip_label.setObjectName("smallMuted")
            note_hbox.addWidget(self.skip_label)

            self.middle_box = note_row
            main_lay.addWidget(note_row)

        self.timer_lbl = timer_lbl
