"""
event_dialog.py — Modal dialog for creating and editing calendar events.
"""

from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTimeEdit,
    QWidget,
)

from ..database.activities import list_activities
from ..database.calendars import get_default_calendar_id, list_calendars
from ..models import Event
from .dialogs import FramelessDialog
from .widgets import _ChevronMixin

# ---------------------------------------------------------------------------
# Colour presets
# ---------------------------------------------------------------------------

_COLOUR_PRESETS: list[tuple[str, str]] = [
    ("Inherit from calendar", ""),
    ("Blue", "#7aa2f7"),
    ("Green", "#9ece6a"),
    ("Yellow", "#e0af68"),
    ("Red", "#f7768e"),
    ("Purple", "#bb9af7"),
    ("Cyan", "#7dcfff"),
    ("Orange", "#ff9e64"),
    ("Teal", "#1abc9c"),
]

# ---------------------------------------------------------------------------
# Themed time-edit with SVG chevron arrows
# ---------------------------------------------------------------------------


class ThemedTimeEdit(_ChevronMixin, QTimeEdit):
    """QTimeEdit with custom SVG chevron arrows that follow the theme."""


_RECURRENCE_OPTIONS: list[tuple[str, str]] = [
    ("Does not repeat", ""),
    ("Daily", "FREQ=DAILY"),
    ("Weekly", "FREQ=WEEKLY"),
    ("Monthly", "FREQ=MONTHLY"),
    ("Yearly", "FREQ=YEARLY"),
]


class EventDialog(FramelessDialog):
    """Create or edit a calendar event.

    Pass ``event=None`` (default) for create mode.
    Pass an existing ``Event`` for edit mode — all fields are pre-populated.
    Pass ``prefill_date`` to pre-fill the date when creating from a day-cell click.
    """

    def __init__(
        self,
        event: Event | None = None,
        prefill_date: date | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._event = event
        self._deleted = False
        self.setWindowTitle("Edit Event" if event else "New Event")
        self.setMinimumWidth(420)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)
        self.contentLayout().addLayout(form)

        # --- Title ---
        self._title = QLineEdit()
        self._title.setPlaceholderText("Event title")
        form.addRow("Title", self._title)

        # --- Calendar ---
        self._calendar_combo = QComboBox()
        self._cal_ids: list[int] = []
        self._populate_calendars()
        form.addRow("Calendar", self._calendar_combo)

        # --- All-day toggle ---
        self._all_day = QCheckBox("All-day event")
        form.addRow("", self._all_day)

        # --- Date ---
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow("Date", self._date_edit)

        # --- Time row ---
        time_row = QWidget()
        time_lay = QHBoxLayout(time_row)
        time_lay.setContentsMargins(0, 0, 0, 0)
        time_lay.setSpacing(8)
        self._start_time = ThemedTimeEdit()
        self._start_time.setDisplayFormat("hh:mm")
        self._end_time = ThemedTimeEdit()
        self._end_time.setDisplayFormat("hh:mm")
        time_lay.addWidget(self._start_time)
        time_lay.addWidget(QLabel("→"))
        time_lay.addWidget(self._end_time)
        time_lay.addStretch()
        form.addRow("Time", time_row)
        self._time_row_widget = time_row

        # --- Location ---
        self._location = QLineEdit()
        self._location.setPlaceholderText("Optional")
        form.addRow("Location", self._location)

        # --- Description ---
        self._description = QPlainTextEdit()
        self._description.setPlaceholderText("Optional notes")
        self._description.setMinimumHeight(60)
        self._description.setMaximumHeight(120)
        form.addRow("Description", self._description)

        # --- Colour override ---
        self._color_combo = QComboBox()
        for label, _ in _COLOUR_PRESETS:
            self._color_combo.addItem(label)
        form.addRow("Color", self._color_combo)

        # --- Recurrence ---
        self._recurrence_combo = QComboBox()
        for label, _ in _RECURRENCE_OPTIONS:
            self._recurrence_combo.addItem(label)
        form.addRow("Repeats", self._recurrence_combo)

        # --- Linked activity ---
        self._activity_combo = QComboBox()
        self._activity_ids: list[int | None] = []
        self._populate_activities()
        form.addRow("Activity", self._activity_combo)

        # --- Button row ---
        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("Save")
        self._save_btn.setObjectName("primaryButton")
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)

        if event:
            self._delete_btn = QPushButton("Delete")
            self._delete_btn.setObjectName("destructiveButton")
            self._delete_btn.clicked.connect(self._on_delete)
            btn_row.addWidget(self._delete_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)

        self.contentLayout().addLayout(btn_row)

        # --- Wire signals ---
        self._all_day.toggled.connect(self._on_all_day_toggled)

        # --- Populate initial values ---
        self._init_values(prefill_date)

        # Auto-focus title
        self._title.setFocus()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _populate_calendars(self) -> None:
        calendars = list_calendars(include_system=False)
        default_id = get_default_calendar_id()
        default_index = 0
        for i, cal in enumerate(calendars):
            self._calendar_combo.addItem(cal.name)
            self._cal_ids.append(cal.id)
            if cal.id == default_id:
                default_index = i
        self._calendar_combo.setCurrentIndex(default_index)

    def _populate_activities(self) -> None:
        self._activity_combo.addItem("None")
        self._activity_ids.append(None)
        for act in list_activities(include_archived=False):
            self._activity_combo.addItem(act.name)
            self._activity_ids.append(act.id)

    def _init_values(self, prefill_date: date | None) -> None:
        """Set default or pre-populated field values."""
        now = datetime.now()

        if self._event:
            e = self._event
            self._title.setText(e.title)

            # Calendar
            if e.calendar_id in self._cal_ids:
                self._calendar_combo.setCurrentIndex(self._cal_ids.index(e.calendar_id))

            # All-day
            self._all_day.setChecked(e.all_day)

            # Date / time
            if e.start_dt:
                self._date_edit.setDate(QDate(e.start_dt.year, e.start_dt.month, e.start_dt.day))
                self._start_time.setTime(QTime(e.start_dt.hour, e.start_dt.minute))
            if e.end_dt:
                self._end_time.setTime(QTime(e.end_dt.hour, e.end_dt.minute))

            self._location.setText(e.location)
            self._description.setPlainText(e.description)

            # Colour
            color_values = [v for _, v in _COLOUR_PRESETS]
            if e.color in color_values:
                self._color_combo.setCurrentIndex(color_values.index(e.color))

            # Recurrence
            rrule_values = [v for _, v in _RECURRENCE_OPTIONS]
            if e.recurrence_rule in rrule_values:
                self._recurrence_combo.setCurrentIndex(rrule_values.index(e.recurrence_rule))

            # Activity
            if e.linked_activity_id in self._activity_ids:
                self._activity_combo.setCurrentIndex(self._activity_ids.index(e.linked_activity_id))
        else:
            # Create mode defaults
            target = prefill_date or now.date()
            self._date_edit.setDate(QDate(target.year, target.month, target.day))
            start_hour = now.hour if not prefill_date else 9
            self._start_time.setTime(QTime(start_hour, 0))
            self._end_time.setTime(QTime(min(start_hour + 1, 23), 0))

        self._on_all_day_toggled(self._all_day.isChecked())

    def _on_all_day_toggled(self, checked: bool) -> None:
        self._time_row_widget.setVisible(not checked)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_values(self) -> dict:
        """Return a dict of field values ready to pass to create_event / update_event."""
        qdate = self._date_edit.date()
        start_date = date(qdate.year(), qdate.month(), qdate.day())
        all_day = self._all_day.isChecked()

        if all_day:
            start_dt = datetime(start_date.year, start_date.month, start_date.day, 0, 0)
            end_dt = start_dt + timedelta(days=1)
        else:
            st = self._start_time.time()
            et = self._end_time.time()
            start_dt = datetime(
                start_date.year, start_date.month, start_date.day, st.hour(), st.minute()
            )
            end_dt = datetime(
                start_date.year, start_date.month, start_date.day, et.hour(), et.minute()
            )
            if end_dt <= start_dt:
                end_dt = start_dt + timedelta(hours=1)

        cal_index = self._calendar_combo.currentIndex()
        calendar_id = self._cal_ids[cal_index] if self._cal_ids else get_default_calendar_id()

        color_value = _COLOUR_PRESETS[self._color_combo.currentIndex()][1] or None
        rrule_value = _RECURRENCE_OPTIONS[self._recurrence_combo.currentIndex()][1]

        act_index = self._activity_combo.currentIndex()
        linked_activity_id = self._activity_ids[act_index] if self._activity_ids else None

        return {
            "calendar_id": calendar_id,
            "title": self._title.text().strip(),
            "start_dt": start_dt,
            "end_dt": end_dt,
            "all_day": all_day,
            "location": self._location.text().strip(),
            "description": self._description.toPlainText().strip(),
            "color": color_value,
            "recurrence_rule": rrule_value,
            "linked_activity_id": linked_activity_id,
        }

    def was_deleted(self) -> bool:
        return self._deleted

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #

    def _on_save(self) -> None:
        if not self._title.text().strip():
            self._title.setProperty("error", True)
            self._title.style().unpolish(self._title)
            self._title.style().polish(self._title)
            return
        self._title.setProperty("error", False)
        self._title.style().unpolish(self._title)
        self._title.style().polish(self._title)
        self.accept()

    def _on_delete(self) -> None:
        self._deleted = True
        self.reject()
