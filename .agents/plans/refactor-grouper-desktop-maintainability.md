# refactor grouper desktop maintainability

## Goal

Refactor the `grouper/` desktop package for maintainability by (1) renaming `grouper/` → `desktop/`, (2) introducing a deeply nested directory structure under `desktop/ui/` organized by feature domain, (3) eliminating duplicated card and dialog implementations via shared base classes and a single card factory, and (4) centralizing transparency/background handling to prevent the recurring opacity bugs that the test suite (`test_transparency.py`) currently guards against.

This is a pure structural refactoring — no behavior changes, no new features. Every existing test must continue to pass with updated import paths only.

## Understanding

## Repository layout (current)

```
grouper/                          # project root
├── grouper/                      # ← DESKTOP APP (PySide6 GUI) — TO BE RENAMED
│   ├── __init__.py               # re-exports __version__ from grouper_core
│   ├── __main__.py               # delegates to main.py
│   ├── _urls.py, _version.py, _win_startup.py
│   ├── app.py                    # MainWindow (530 LOC)
│   ├── config.py                 # shim → grouper_core.config
│   ├── formatting.py             # shim → grouper_core.formatting
│   ├── main.py                   # entry point (splash, theme, app loop)
│   ├── models.py                 # shim → grouper_core.models
│   ├── operations.py             # shim → grouper_core.operations
│   ├── version_check.py, web_server.py
│   ├── assets/icon.ico
│   ├── database/                 # thin shims re-exporting from grouper_core.database.*
│   │   ├── __init__.py           # massive re-export list (~200 names)
│   │   ├── connection.py         # adds Qt _DataNotifier on top of core
│   │   ├── activities.py, boards.py, calendars.py, events.py, ...
│   ├── styles/
│   │   ├── __init__.py           # load_theme() — QSS template renderer
│   │   ├── _base.qss            # single QSS template with {{token}} placeholders
│   │   └── colors.py             # shim → grouper_core.colors
│   └── ui/                       # 33 files, all flat — THIS IS THE MESS
│       ├── about.py, activity_card.py, activity_config.py, activity_week.py
│       ├── agenda_view.py, animated_card.py, animated_stack.py
│       ├── calendar_view.py, dashboard.py, dialogs.py, event_dialog.py
│       ├── history.py, icons.py, link_chips.py, mime_types.py
│       ├── session_card.py, settings.py, sidebar.py, splash.py
│       ├── summary.py, sync_view.py, task_board.py, task_list.py
│       ├── task_panel.py, time_grid.py, time_tracker.py
│       ├── timeline_view.py, title_bar.py, view_models.py
│       ├── widget_pool.py, widgets.py
├── grouper_core/                 # shared business logic (no Qt dependency)
├── grouper_cli/                  # TUI interface
├── grouper_server/               # Flask sync server
├── grouper_install/              # Windows installer
├── tests/
│   ├── widget/                   # widget tests (need QApplication)
│   │   └── test_transparency.py  # 300 LOC of pixel-level opacity/contrast tests
│   ├── unit/                     # unit tests
│   └── integration/              # integration tests
└── pyproject.toml                # [tool.setuptools.packages.find] include = ["grouper*", ...]
```

## Duplication inventory

### 1. Card classes (the worst offender)

There are **11 separate QFrame subclasses** called `*Card`, most setting `self.setObjectName("card")` with nearly identical layouts:

| File | Class | Role | LOC |
|------|-------|------|-----|
| `dashboard.py` | `_SessionCard` | active session row | ~30 |
| `dashboard.py` | `_TaskCard` | upcoming task row | ~30 |
| `dashboard.py` | `_TaskboxCard` | starred projects/tasks | ~120 |
| `history.py` | `_TaskHistoryCard` | completed task row | ~25 |
| `history.py` | `_SessionHistoryCard` | past session row | ~35 |
| `task_board.py` | `TaskCard` | kanban task card | ~400 |
| `session_card.py` | `SessionCard` | active session card (complex) | ~130 |
| `activity_card.py` | `ActivityCard` | activity drag card | ~60 |
| `animated_card.py` | `AnimatedCard` | animation wrapper | ~60 |
| `timeline_view.py` | `_TimelineCard` | event/task in timeline | ~100 |

**Common pattern** (repeated 9+ times):
```python
class _XxxCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)
        # ... label + stretch + label ...
```

### 2. Dialog classes — FramelessDialog boilerplate

`dialogs.py` (830 LOC) has **11 Dialog subclasses** all inheriting `FramelessDialog`. Each repeats:
- `QFormLayout()` + `QLineEdit()` + `QDialogButtonBox(Ok|Cancel)` pattern
- Manual error state management (`setProperty("error")` + `unpolish`/`polish`)
- `_build_due_date_row` helper extracted but tags/prereqs/link sections are duplicated between `CreateTaskDialog` and `EditTaskDialog`

### 3. Package-level shim duplication

`grouper/config.py`, `grouper/models.py`, `grouper/formatting.py`, `grouper/operations.py`, `grouper/styles/colors.py`, and all `grouper/database/*.py` files are pure re-export shims from `grouper_core`. This is intentional (decouples core from Qt) but means 14 files exist solely to forward imports.

### 4. Transparency / opacity issues

The `test_transparency.py` file (300 LOC) pixel-tests that:
- `FramelessDialog` chrome is opaque (alpha == 255) in all themes
- Dialog border differs visually from page background
- Parented dialogs don't get pure-black transparent margins
- `#card QWidget { background-color: transparent; }` descendant selectors work correctly

These bugs recur because transparency is set ad-hoc in individual card/dialog constructors rather than being centralized.

## Constraints

- **No behavior changes**: this is purely structural. All tests must pass after refactoring.
- **`grouper_core` is untouched**: it has no Qt dependency and serves CLI/server too.
- **Entry point**: `pyproject.toml` has `[project.gui-scripts] grouper = "grouper.main:main"`. After rename this becomes `"desktop.main:main"`.
- **Database shim layer stays**: the `database/` re-exports from `grouper_core` must remain because `connection.py` adds the Qt `DataNotifier`.
- **35 files import from `grouper.*`**: all test files, the server, CLI, and installer import from the `grouper` package namespace.

## Approach

## High-level strategy

Three independent tracks that can execute in sequence (each track is independently verifiable):

### Track A — Rename `grouper/` → `desktop/`
Rename the top-level package directory and update all references. This is a mechanical find-replace across `pyproject.toml`, test imports, and any cross-package imports.

### Track B — Restructure `desktop/ui/` into nested feature domains
Split the 33-file flat directory into domain-oriented sub-packages. Files move; their public APIs stay identical. Internal imports within `desktop/ui/` update to use relative paths.

### Track C — Consolidate card & dialog implementations
Extract a shared `BaseCard(QFrame)` class that centralizes the `setObjectName("card")` + standard margins + transparency pattern. Extract a shared `BaseFormDialog(FramelessDialog)` that provides the standard form layout + button box + error-state management. Rewrite the 11 card subclasses and 11 dialog subclasses to use these bases, eliminating ~400 LOC of duplication.

### Why this order
- Track A is mechanical and gives us the final package name.
- Track B is also mechanical (file moves + import updates) and gives us the directory structure.
- Track C is the substantive change (shared bases, transparency centralization) and benefits from both the final name and structure being stable.

## Steps

## Phase 1: Rename `grouper/` → `desktop/`

### 1.1 Rename the package directory
- **Location:** `grouper/grouper/` → `grouper/desktop/`
- **Action:** `git mv grouper desktop`
- **Verification:** `ls desktop/` shows `__init__.py`, `app.py`, `ui/`, etc.

### 1.2 Update `pyproject.toml`
- **Location:** `pyproject.toml`
- **Action:**
  - Change `[tool.setuptools.packages.find] include` from `["grouper*", "grouper_core*", ...]` to `["desktop*", "grouper_core*", "grouper_cli*", "grouper_server*"]`
  - Change `[project.gui-scripts]` from `grouper = "grouper.main:main"` to `grouper = "desktop.main:main"`
  - Change `[tool.ruff] src` from `["grouper", ...]` to `["desktop", ...]`
  - Change all `[tool.ruff.lint.per-file-ignores]` keys starting with `"grouper/` to `"desktop/`
- **Verification:** `python -c "import desktop; print(desktop.__version__)"` works.

### 1.3 Update all internal imports within `desktop/`
- **Location:** Every file inside `desktop/`
- **Action:** Replace `from grouper.` → `from desktop.` and `import grouper.` → `import desktop.` in:
  - `desktop/__init__.py` (imports `from grouper_core`)
  - `desktop/__main__.py` (imports `from .main`)
  - `desktop/main.py` (7 import lines: `from grouper._win_startup`, `from grouper.app`, `from grouper.config`, `from grouper.database.connection`, `from grouper.styles`, `from grouper.ui.splash`, `from grouper.version_check`)
  - All `desktop/ui/*.py` — verified: ALL 33 UI files use relative imports only (`from ..config`, `from ..database`, etc.). No changes needed.
  - `desktop/database/connection.py` (imports `grouper_core.*` — no change needed)
  - `desktop/styles/colors.py` (imports `grouper_core.*` — no change needed)
- **Only files needing explicit changes:** `desktop/__init__.py`, `desktop/main.py`.
- **Verification:** `python -c "from desktop.app import MainWindow"` succeeds.

### 1.4 Update test imports
- **Location:** `tests/**/*.py`
- **Action:** Replace all `from grouper.` → `from desktop.` and `import grouper.` → `import desktop.` in every test file:
  - `tests/widget/*.py` (imports like `from grouper.styles import ...`, `from grouper.ui.dialogs import ...`)
  - `tests/unit/*.py`
  - `tests/conftest.py`
- **Verification:** `pytest tests/ --co -q` collects all tests without import errors.

### 1.5 Update other packages that reference `grouper`
- **Location:** `grouper_server/`, `grouper_cli/`, `grouper_install/`, `scripts/`
- **Action:** Search for `from grouper.` or `import grouper` in these packages. Most reference `grouper_core` (not `grouper`) so likely need no changes. Verify:
  - `grouper_server/__main__.py`
  - `grouper_cli/main.py`
  - `grouper_install/` files
  - `scripts/` files
- **Verification:** `pytest tests/` passes.

### 1.6 Clean up stale artifacts
- **Location:** project root
- **Action:**
  - Delete `grouper.egg-info/` if it exists (will be regenerated)
  - Delete `desktop/__pycache__/`, `desktop/ui/__pycache__/`, etc.
  - Run `pip install -e .` to regenerate egg-info
- **Verification:** `pip install -e . && pytest tests/` passes.

---

## Phase 2: Restructure `desktop/ui/` into nested feature domains

### Target directory structure

```
desktop/ui/
├── __init__.py               # (unchanged — empty)
├── shared/                   # shared infrastructure
│   ├── __init__.py
│   ├── base_card.py          # NEW — BaseCard (from Phase 3)
│   ├── base_dialog.py        # NEW — BaseFormDialog (from Phase 3)
│   ├── animated_card.py      # MOVED from ui/animated_card.py
│   ├── animated_stack.py     # MOVED from ui/animated_stack.py
│   ├── widget_pool.py        # MOVED from ui/widget_pool.py
│   ├── widgets.py            # MOVED from ui/widgets.py
│   ├── icons.py              # MOVED from ui/icons.py
│   ├── link_chips.py         # MOVED from ui/link_chips.py
│   ├── mime_types.py         # MOVED from ui/mime_types.py
│   ├── view_models.py        # MOVED from ui/view_models.py
│   ├── title_bar.py          # MOVED from ui/title_bar.py (includes DialogTitleBar)
│   └── splash.py             # MOVED from ui/splash.py (startup concern, not time-tracking)
├── time/                     # time tracking domain
│   ├── __init__.py
│   ├── time_tracker.py       # MOVED from ui/time_tracker.py
│   ├── time_grid.py          # MOVED from ui/time_grid.py
│   ├── session_card.py       # MOVED from ui/session_card.py
│   ├── activity_card.py      # MOVED from ui/activity_card.py
│   ├── activity_config.py    # MOVED from ui/activity_config.py
│   └── activity_week.py      # MOVED from ui/activity_week.py
├── tasks/                    # task management domain
│   ├── __init__.py
│   ├── task_board.py         # MOVED from ui/task_board.py
│   ├── task_list.py          # MOVED from ui/task_list.py
│   ├── task_panel.py         # MOVED from ui/task_panel.py
│   └── dialogs.py            # MOVED from ui/dialogs.py (FramelessDialog + all task/project dialogs)
├── calendar/                 # calendar/events domain
│   ├── __init__.py
│   ├── calendar_view.py      # MOVED from ui/calendar_view.py
│   ├── agenda_view.py        # MOVED from ui/agenda_view.py
│   ├── event_dialog.py       # MOVED from ui/event_dialog.py
│   └── timeline_view.py      # MOVED from ui/timeline_view.py
├── views/                    # top-level views / pages
│   ├── __init__.py
│   ├── dashboard.py          # MOVED from ui/dashboard.py
│   ├── history.py            # MOVED from ui/history.py
│   ├── summary.py            # MOVED from ui/summary.py
│   ├── settings.py           # MOVED from ui/settings.py
│   ├── about.py              # MOVED from ui/about.py
│   ├── sync_view.py          # MOVED from ui/sync_view.py
│   └── sidebar.py            # MOVED from ui/sidebar.py
```

### 2.1 Create sub-package directories
- **Action:** Create `desktop/ui/shared/`, `desktop/ui/time/`, `desktop/ui/tasks/`, `desktop/ui/calendar/`, `desktop/ui/views/` — each with an empty `__init__.py`.
- **Verification:** All 5 directories exist with `__init__.py`.

### 2.2 Move shared infrastructure files → `desktop/ui/shared/`
- **Files to move (10 files):**
  - `animated_card.py` → `shared/animated_card.py`
  - `animated_stack.py` → `shared/animated_stack.py`
  - `widget_pool.py` → `shared/widget_pool.py`
  - `widgets.py` → `shared/widgets.py`
  - `icons.py` → `shared/icons.py`
  - `link_chips.py` → `shared/link_chips.py`
  - `mime_types.py` → `shared/mime_types.py`
  - `view_models.py` → `shared/view_models.py`
  - `title_bar.py` → `shared/title_bar.py`
  - `splash.py` → `shared/splash.py`
- **Action:** `git mv` each file. Update internal relative imports in moved files:
  - `from ..config` → `from ...config` (one more level of nesting)
  - `from ..database` → `from ...database`
  - `from ..styles` → `from ...styles`
  - `from ..models` → `from ...models`
  - Cross-references between shared files (e.g., `from .widgets import ...`) remain unchanged (same directory).
  - `splash.py` also imports `from .._version` → `from ..._version`, `from ..styles` → `from ...styles`.
- **Also update:** `desktop/main.py` import: `from desktop.ui.splash import SplashScreen` → `from desktop.ui.shared.splash import SplashScreen`
- **Verification:** `python -c "from desktop.ui.shared.widgets import ElidedLabel"` succeeds.

### 2.3 Move time-tracking files → `desktop/ui/time/`
- **Files to move (6 files):**
  - `time_tracker.py` → `time/time_tracker.py`
  - `time_grid.py` → `time/time_grid.py`
  - `session_card.py` → `time/session_card.py`
  - `activity_card.py` → `time/activity_card.py`
  - `activity_config.py` → `time/activity_config.py`
  - `activity_week.py` → `time/activity_week.py`
- **Action:** `git mv` each file. Update imports in each:
  - `from ..config` → `from ...config`
  - `from ..database` → `from ...database`
  - `from ..styles` → `from ...styles`
  - `from ..models` → `from ...models`
  - `from .animated_card` → `from ..shared.animated_card`
  - `from .animated_stack` → `from ..shared.animated_stack`
  - `from .widget_pool` → `from ..shared.widget_pool`
  - `from .widgets` → `from ..shared.widgets`
  - `from .icons` → `from ..shared.icons`
  - `from .dialogs` → `from ..tasks.dialogs` (CreateActivityDialog, StopSessionDialog)
  - Same-directory references (`from .activity_card`, `from .session_card`) remain unchanged.
- **Verification:** `python -c "from desktop.ui.time.time_tracker import TimeTrackerView"` succeeds.

### 2.4 Move task files → `desktop/ui/tasks/`
- **Files to move (4 files):**
  - `task_board.py` → `tasks/task_board.py`
  - `task_list.py` → `tasks/task_list.py`
  - `task_panel.py` → `tasks/task_panel.py`
  - `dialogs.py` → `tasks/dialogs.py` (FramelessDialog + all task/project/board dialogs)
- **Action:** `git mv` each file. Update imports in each:
  - `from ..config` → `from ...config`
  - `from ..database` → `from ...database`
  - `from ..models` → `from ...models`
  - `from .title_bar` → `from ..shared.title_bar`
  - `from .widgets` → `from ..shared.widgets`
  - `from .icons` → `from ..shared.icons`
  - `from .link_chips` → `from ..shared.link_chips`
  - `from .animated_stack` → `from ..shared.animated_stack`
  - `from .widget_pool` → `from ..shared.widget_pool`
- **Verification:** `python -c "from desktop.ui.tasks.task_board import TaskBoardView"` succeeds.

### 2.5 Move calendar files → `desktop/ui/calendar/`
- **Files to move (4 files):**
  - `calendar_view.py` → `calendar/calendar_view.py`
  - `agenda_view.py` → `calendar/agenda_view.py`
  - `event_dialog.py` → `calendar/event_dialog.py`
  - `timeline_view.py` → `calendar/timeline_view.py`
- **Action:** `git mv` each file. Update imports in each:
  - `from ..config` → `from ...config`
  - `from ..database` → `from ...database`
  - `from ..styles` → `from ...styles`
  - `from ..models` → `from ...models`
  - `from .dialogs` → `from ..tasks.dialogs` (FramelessDialog used by EventDialog)
  - `from .widgets` → `from ..shared.widgets`
  - `from .icons` → `from ..shared.icons`
  - `from .mime_types` → `from ..shared.mime_types`
  - Same-directory references (`from .event_dialog`) remain unchanged.
- **Verification:** `python -c "from desktop.ui.calendar.calendar_view import CalendarView"` succeeds.

### 2.6 Move view files → `desktop/ui/views/`
- **Files to move (7 files):**
  - `dashboard.py` → `views/dashboard.py`
  - `history.py` → `views/history.py`
  - `summary.py` → `views/summary.py`
  - `settings.py` → `views/settings.py`
  - `about.py` → `views/about.py`
  - `sync_view.py` → `views/sync_view.py`
  - `sidebar.py` → `views/sidebar.py`
- **Action:** `git mv` each file. Update imports in each:
  - `from ..config` → `from ...config`
  - `from ..database` → `from ...database`
  - `from ..styles` → `from ...styles`
  - `from ..models` → `from ...models`
  - Cross-domain imports now need `..` prefix:
    - `from .time_grid` → `from ..time.time_grid` (dashboard)
    - `from .activity_week` → `from ..time.activity_week` (dashboard)
    - `from .widget_pool` → `from ..shared.widget_pool`
    - `from .widgets` → `from ..shared.widgets`
    - `from .icons` → `from ..shared.icons`
    - `from .animated_stack` → `from ..shared.animated_stack`
- **Verification:** `python -c "from desktop.ui.views.dashboard import DashboardView"` succeeds.

### 2.7 Update `desktop/app.py` imports
- **Location:** `desktop/app.py`
- **Action:** Update all view imports from flat `from .ui.X` to nested paths:
  - `from .ui.about import AboutView` → `from .ui.views.about import AboutView`
  - `from .ui.calendar_view import CalendarView` → `from .ui.calendar.calendar_view import CalendarView`
  - `from .ui.dashboard import DashboardView` → `from .ui.views.dashboard import DashboardView`
  - `from .ui.history import HistoryView` → `from .ui.views.history import HistoryView`
  - `from .ui.settings import SettingsView` → `from .ui.views.settings import SettingsView`
  - `from .ui.sidebar import Sidebar` → `from .ui.views.sidebar import Sidebar`
  - `from .ui.summary import SummaryView` → `from .ui.views.summary import SummaryView`
  - `from .ui.sync_view import SyncView` → `from .ui.views.sync_view import SyncView`
  - `from .ui.task_board import TaskBoardView` → `from .ui.tasks.task_board import TaskBoardView`
  - `from .ui.task_list import TaskListView` → `from .ui.tasks.task_list import TaskListView`
  - `from .ui.time_tracker import TimeTrackerView` → `from .ui.time.time_tracker import TimeTrackerView`
  - `from .ui.title_bar import TitleBar` → `from .ui.shared.title_bar import TitleBar`
  - `from .ui.icons import clear_cache` → `from .ui.shared.icons import clear_cache`
  - `from .ui.animated_stack import ...` → `from .ui.shared.animated_stack import ...`
- **Verification:** `python -c "from desktop.app import MainWindow"` succeeds.

### 2.8 Update all test imports
- **Location:** `tests/widget/*.py`, `tests/unit/*.py`, `tests/conftest.py`
- **Action:** Update imports to match new paths:
  - `from desktop.ui.dialogs import ...` → `from desktop.ui.tasks.dialogs import ...`
  - `from desktop.ui.activity_config import ...` → `from desktop.ui.time.activity_config import ...`
  - `from desktop.styles import ...` → stays `from desktop.styles import ...` (no change)
  - `from desktop.models import ...` → stays `from desktop.models import ...` (no change)
  - `from desktop.ui.sidebar import ...` → `from desktop.ui.views.sidebar import ...`
  - `from desktop.ui.dashboard import ...` → `from desktop.ui.views.dashboard import ...`
  - `from desktop.ui.summary import ...` → `from desktop.ui.views.summary import ...`
  - `from desktop.ui.task_board import ...` → `from desktop.ui.tasks.task_board import ...`
  - `from desktop.ui.icons import ...` → `from desktop.ui.shared.icons import ...`
- **Verification:** `pytest tests/ --co -q` collects all tests.

### 2.9 Full test run after restructure
- **Action:** `pytest tests/ -v`
- **Verification:** All tests pass. Fix any remaining import issues.

---

## Phase 3: Consolidate card & dialog implementations

### 3.1 Create `BaseCard` in `desktop/ui/shared/base_card.py`
- **Location:** NEW file `desktop/ui/shared/base_card.py`
- **Action:** Extract a shared base class:
  ```python
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
  ```
- **Verification:** `python -c "from desktop.ui.shared.base_card import BaseCard"` succeeds.

### 3.2 Refactor simple card subclasses to use `BaseCard`
- **Files to modify:**
  - `desktop/ui/views/dashboard.py` — `_SessionCard`, `_TaskCard` (currently ~30 LOC each)
  - `desktop/ui/views/history.py` — `_TaskHistoryCard`, `_SessionHistoryCard`
- **Action:** Change `class _XxxCard(QFrame)` → `class _XxxCard(BaseCard)`, add `from ..shared.base_card import BaseCard`, and remove duplicated `__init__` boilerplate (setObjectName, layout setup). Keep view-specific fields.
- **Verification:** `pytest tests/widget/test_dashboard_layout.py tests/widget/test_taskbox_elide.py -v` passes.

### 3.3 Refactor complex card subclasses
- **Files to modify:**
  - `desktop/ui/time/session_card.py` — `SessionCard` (130 LOC)
  - `desktop/ui/time/activity_card.py` — `ActivityCard` (60 LOC)
  - `desktop/ui/tasks/task_board.py` — `TaskCard` (400 LOC)
  - `desktop/ui/calendar/timeline_view.py` — `_TimelineCard` (100 LOC)
- **Action:** Change base class to `BaseCard`. Remove duplicated init boilerplate. Keep all domain-specific logic (signals, drag-and-drop, action rows). The `_set_drag_passthrough` pattern in `TaskCard` becomes a call to `BaseCard._make_child_transparent`.
- **Verification:** `pytest tests/widget/test_task_board_drag.py tests/widget/test_transparency.py -v` passes.

### 3.4 Create `BaseFormDialog` in `desktop/ui/shared/base_dialog.py`
- **Location:** NEW file `desktop/ui/shared/base_dialog.py`
- **Action:** Extract shared dialog patterns:
  ```python
  from PySide6.QtWidgets import QDialogButtonBox, QFormLayout

  from ..tasks.dialogs import FramelessDialog  # noqa: F401 (re-exported for convenience)


  class BaseFormDialog(FramelessDialog):
      """FramelessDialog with standard form layout + Ok/Cancel buttons.

      Provides:
      - QFormLayout with standard spacing
      - Ok/Cancel button box (accessible as self._buttons)
      - set_field_error() helper for field validation
      """

      def __init__(self, title: str, min_width: int = 380, parent=None):
          super().__init__(parent)
          self.setWindowTitle(title)
          self.setMinimumWidth(min_width)
          self._form = QFormLayout()
          self._form.setSpacing(10)
          self.contentLayout().addLayout(self._form)
          self._buttons = QDialogButtonBox(
              QDialogButtonBox.StandardButton.Ok
              | QDialogButtonBox.StandardButton.Cancel
          )
          self._buttons.accepted.connect(self.accept)
          self._buttons.rejected.connect(self.reject)

      def add_row(self, label, widget):
          self._form.addRow(label, widget)

      def finalize_form(self):
          """Add the button box to the form. Call after all rows are added."""
          self._form.addRow(self._buttons)

      @staticmethod
      def set_field_error(widget, has_error: bool = True):
          """Toggle the 'error' property on a widget and force QSS re-evaluation."""
          widget.setProperty("error", has_error)
          widget.style().unpolish(widget)
          widget.style().polish(widget)
  ```
- **IMPORTANT:** This file imports from `..tasks.dialogs` which means `tasks/dialogs.py` must be importable without pulling in `base_dialog.py`. Since `FramelessDialog` is defined in `tasks/dialogs.py` and `base_dialog.py` only imports it, there is no circular dependency.
- **Verification:** `python -c "from desktop.ui.shared.base_dialog import BaseFormDialog"` succeeds.

### 3.5 Refactor dialog subclasses to use `BaseFormDialog`
- **Files to modify:**
  - `desktop/ui/tasks/dialogs.py` — Refactor these to use `BaseFormDialog`:
    - `CreateActivityDialog` (~40 LOC → ~15 LOC)
    - `CreateProjectDialog` (~40 LOC → ~15 LOC)
    - `EditProjectDialog` (~60 LOC → ~30 LOC)
    - `EditBoardDialog` (~50 LOC → ~25 LOC)
    - `AddBoardDialog` (~30 LOC → ~12 LOC)
    - `AddGroupDialog` (~50 LOC → ~25 LOC)
    - `StopSessionDialog` (~40 LOC → ~20 LOC)
    - `ConfirmDialog` — leave as-is (too simple, different Yes/No button pattern)
    - `CreateTaskDialog` and `EditTaskDialog` — these are more complex (tags, prereqs, links). Use `BaseFormDialog` for the form + button boilerplate but keep all domain-specific sections.
  - `desktop/ui/calendar/event_dialog.py` — `EventDialog` uses custom Save/Delete/Cancel button layout; use `BaseFormDialog` for form boilerplate but override button setup.
- **Action:** Add `from ..shared.base_dialog import BaseFormDialog` to each file. Replace `class XxxDialog(FramelessDialog)` → `class XxxDialog(BaseFormDialog)`. Remove manual form layout + button box setup. Replace `self.contentLayout().addLayout(...)` with `self.add_row(...)`. Replace manual error property toggling with `self.set_field_error(widget)`.
- **Verification:** `pytest tests/widget/test_dialogs.py tests/widget/test_setup_dialog.py -v` passes.

### 3.6 Centralize transparency handling in `FramelessDialog`
- **Location:** `desktop/ui/tasks/dialogs.py` — `FramelessDialog.__init__()`
- **Action:**
  1. Ensure both `dialogFrame` and `dialogContent` have `WA_StyledBackground = True` (already set — verify).
  2. Add `self.setAutoFillBackground(True)` on the dialog itself, with the palette color set to the theme's `bg-primary`. This prevents the pure-black margin bleed-through that `test_transparency.py` guards against when a dialog is parented.
  3. Verify this doesn't break the existing shadow effect (the `_container` uses `QGraphicsDropShadowEffect` which should still work since the shadow is on the container, not the dialog).
- **Verification:** `pytest tests/widget/test_transparency.py -v` passes. This 300-LOC pixel-level test suite is the authoritative guard against opacity regressions.

### 3.7 Update `about.py` card usage
- **Location:** `desktop/ui/views/about.py`
- **Action:** The about page creates a `QFrame` with `setObjectName("card")`. Replace with `BaseCard` for consistency. Add `from ..shared.base_card import BaseCard`.
- **Verification:** `pytest tests/widget/test_theme_load.py -v` passes.

---

## Phase 4: Final verification & cleanup

### 4.1 Run full test suite
- **Action:** `pytest tests/ -v --tb=short`
- **Verification:** All tests pass.

### 4.2 Run ruff linting
- **Action:** `ruff check desktop/ tests/`
- **Verification:** No errors. Fix any F401 (unused imports from moves) or F403 issues.

### 4.3 Verify entry point
- **Action:** `python -m desktop` or `grouper` (if installed) launches the app without error.
- **Verification:** App window appears.

### 4.4 Update pyproject.toml per-file-ignores
- **Location:** `pyproject.toml`
- **Action:** Ensure all `[tool.ruff.lint.per-file-ignores]` entries use `desktop/` paths:
  ```
  "desktop/config.py" = ["F401", "F403"]
  "desktop/formatting.py" = ["F401", "F403"]
  "desktop/models.py" = ["F401", "F403"]
  "desktop/operations.py" = ["F401", "F403"]
  "desktop/styles/colors.py" = ["F401", "F403"]
  "desktop/database/*.py" = ["F403"]
  "desktop/database/connection.py" = ["F401"]
  ```
- **Verification:** `ruff check desktop/` passes.

### 4.5 Delete stale `__pycache__` directories
- **Action:** `Get-ChildItem -Path . -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force`
- **Verification:** No `__pycache__` directories remain.
## Phase 1: Rename `grouper/` → `desktop/`

### 1.1 Rename the package directory
- **Location:** `grouper/grouper/` → `grouper/desktop/`
- **Action:** `git mv grouper desktop`
- **Verification:** `ls desktop/` shows `__init__.py`, `app.py`, `ui/`, etc.

### 1.2 Update `pyproject.toml`
- **Location:** `pyproject.toml`
- **Action:**
  - Change `[tool.setuptools.packages.find] include` from `["grouper*", "grouper_core*", ...]` to `["desktop*", "grouper_core*", "grouper_cli*", "grouper_server*"]`
  - Change `[project.gui-scripts]` from `grouper = "grouper.main:main"` to `grouper = "desktop.main:main"`
  - Change `[tool.ruff] src` from `["grouper", ...]` to `["desktop", ...]`
  - Change all `[tool.ruff.lint.per-file-ignores]` keys starting with `"grouper/` to `"desktop/`
- **Verification:** `python -c "import desktop; print(desktop.__version__)"` works.

### 1.3 Update all internal imports within `desktop/`
- **Location:** Every file inside `desktop/`
- **Action:** Replace `from grouper.` → `from desktop.` and `import grouper.` → `import desktop.` in:
  - `desktop/__init__.py`
  - `desktop/__main__.py`
  - `desktop/main.py` (imports `from grouper._win_startup`, `from grouper.app`, etc.)
  - `desktop/app.py` (imports `from .ui.*`, `from .styles.*`, `from .config` — these are relative so mostly fine)
  - `desktop/ui/*.py` (any absolute `from grouper.` imports — most use `..` relative imports, but check)
  - `desktop/database/connection.py` (imports `grouper_core.*` — no change needed)
  - `desktop/styles/colors.py` (imports `grouper_core.*` — no change needed)
- **Note:** Most UI files use relative imports (`from ..config import get_config`) which will work unchanged. The main files that need updating are `__init__.py`, `__main__.py`, `main.py`.
- **Verification:** `python -c "from desktop.app import MainWindow"` succeeds.

### 1.4 Update test imports
- **Location:** `tests/**/*.py`
- **Action:** Replace all `from grouper.` → `from desktop.` and `import grouper.` → `import desktop.` in every test file.
  - `tests/widget/*.py` (imports like `from grouper.styles import ...`, `from grouper.ui.dialogs import ...`)
  - `tests/unit/*.py`
  - `tests/conftest.py`
- **Verification:** `pytest tests/ --co -q` collects all tests without import errors.

### 1.5 Update other packages that reference `grouper`
- **Location:** `grouper_server/`, `grouper_cli/`, `grouper_install/`, `scripts/`
- **Action:** Search for `from grouper.` or `import grouper` in these packages. Most reference `grouper_core` (not `grouper`) so may need no changes. Check:
  - `grouper_server/__main__.py`
  - `grouper_cli/main.py`
  - `grouper_install/` files
  - `scripts/` files
- **Verification:** `pytest tests/` passes.

### 1.6 Clean up stale artifacts
- **Location:** project root
- **Action:**
  - Delete `grouper.egg-info/` if it exists (will be regenerated)
  - Delete `desktop/__pycache__/`, `desktop/ui/__pycache__/`, etc.
  - Run `pip install -e .` to regenerate egg-info
- **Verification:** `pip install -e . && pytest tests/` passes.

---

## Phase 2: Restructure `desktop/ui/` into nested feature domains

### Target directory structure

```
desktop/ui/
├── __init__.py               # (unchanged — empty)
├── shared/                   # shared infrastructure
│   ├── __init__.py
│   ├── base_card.py          # NEW — BaseCard, BaseListCard (from Phase 3)
│   ├── base_dialog.py        # NEW — BaseFormDialog, BaseConfirmDialog (from Phase 3)
│   ├── animated_card.py      # MOVED from ui/animated_card.py
│   ├── animated_stack.py     # MOVED from ui/animated_stack.py
│   ├── widget_pool.py        # MOVED from ui/widget_pool.py
│   ├── widgets.py            # MOVED from ui/widgets.py
│   ├── icons.py              # MOVED from ui/icons.py
│   ├── link_chips.py         # MOVED from ui/link_chips.py
│   ├── mime_types.py         # MOVED from ui/mime_types.py
│   ├── view_models.py        # MOVED from ui/view_models.py
│   └── title_bar.py          # MOVED from ui/title_bar.py (includes DialogTitleBar)
├── time/                     # time tracking domain
│   ├── __init__.py
│   ├── time_tracker.py       # MOVED from ui/time_tracker.py
│   ├── time_grid.py          # MOVED from ui/time_grid.py
│   ├── session_card.py       # MOVED from ui/session_card.py
│   ├── activity_card.py      # MOVED from ui/activity_card.py
│   ├── activity_config.py    # MOVED from ui/activity_config.py
│   ├── activity_week.py      # MOVED from ui/activity_week.py
│   └── splash.py             # MOVED from ui/splash.py
├── tasks/                    # task management domain
│   ├── __init__.py
│   ├── task_board.py         # MOVED from ui/task_board.py
│   ├── task_list.py          # MOVED from ui/task_list.py
│   ├── task_panel.py         # MOVED from ui/task_panel.py
│   └── dialogs.py            # MOVED from ui/dialogs.py (CreateTaskDialog, EditTaskDialog, etc.)
├── calendar/                 # calendar/events domain
│   ├── __init__.py
│   ├── calendar_view.py      # MOVED from ui/calendar_view.py
│   ├── agenda_view.py        # MOVED from ui/agenda_view.py
│   ├── event_dialog.py       # MOVED from ui/event_dialog.py
│   └── timeline_view.py      # MOVED from ui/timeline_view.py
├── views/                    # top-level views / pages
│   ├── __init__.py
│   ├── dashboard.py          # MOVED from ui/dashboard.py
│   ├── history.py            # MOVED from ui/history.py
│   ├── summary.py            # MOVED from ui/summary.py
│   ├── settings.py           # MOVED from ui/settings.py
│   ├── about.py              # MOVED from ui/about.py
│   ├── sync_view.py          # MOVED from ui/sync_view.py
│   └── sidebar.py            # MOVED from ui/sidebar.py
```

### 2.1 Create sub-package directories
- **Action:** Create `desktop/ui/shared/`, `desktop/ui/time/`, `desktop/ui/tasks/`, `desktop/ui/calendar/`, `desktop/ui/views/` with empty `__init__.py` files.
- **Verification:** All directories exist with `__init__.py`.

### 2.2 Move shared infrastructure files → `desktop/ui/shared/`
- **Files to move:**
  - `animated_card.py` → `shared/animated_card.py`
  - `animated_stack.py` → `shared/animated_stack.py`
  - `widget_pool.py` → `shared/widget_pool.py`
  - `widgets.py` → `shared/widgets.py`
  - `icons.py` → `shared/icons.py`
  - `link_chips.py` → `shared/link_chips.py`
  - `mime_types.py` → `shared/mime_types.py`
  - `view_models.py` → `shared/view_models.py`
  - `title_bar.py` → `shared/title_bar.py`
- **Action:** `git mv` each file. Update internal relative imports in moved files:
  - `from ..config` → `from ...config` (one more level of nesting)
  - `from ..database` → `from ...database`
  - `from ..styles` → `from ...styles`
  - `from ..models` → `from ...models`
  - Cross-references between shared files change from `from .widgets import ...` (same dir) to `from .widgets import ...` (still same dir, no change).
- **Verification:** `python -c "from desktop.ui.shared.widgets import ElidedLabel"` succeeds.

### 2.3 Move time-tracking files → `desktop/ui/time/`
- **Files to move:**
  - `time_tracker.py` → `time/time_tracker.py`
  - `time_grid.py` → `time/time_grid.py`
  - `session_card.py` → `time/session_card.py`
  - `activity_card.py` → `time/activity_card.py`
  - `activity_config.py` → `time/activity_config.py`
  - `activity_week.py` → `time/activity_week.py`
  - `splash.py` → `time/splash.py`
- **Action:** `git mv` each file. Update internal imports:
  - `from ..config` → `from ...config`
  - `from ..database` → `from ...database`
  - `from .activity_card` → `from .activity_card` (same dir, no change)
  - `from .session_card` → `from .session_card` (same dir, no change)
  - `from .animated_card` → `from ..shared.animated_card`
  - `from .animated_stack` → `from ..shared.animated_stack`
  - `from .widget_pool` → `from ..shared.widget_pool`
  - `from .widgets` → `from ..shared.widgets`
  - `from .icons` → `from ..shared.icons`
  - `from .dialogs` → `from ..tasks.dialogs` (CreateActivityDialog, StopSessionDialog)
- **Verification:** `python -c "from desktop.ui.time.time_tracker import TimeTrackerView"` succeeds.

### 2.4 Move task files → `desktop/ui/tasks/`
- **Files to move:**
  - `task_board.py` → `tasks/task_board.py`
  - `task_list.py` → `tasks/task_list.py`
  - `task_panel.py` → `tasks/task_panel.py`
  - `dialogs.py` → `tasks/dialogs.py` (FramelessDialog + all task/project dialogs)
- **Action:** `git mv` each file. Update imports:
  - `from ..config` → `from ...config`
  - `from ..database` → `from ...database`
  - `from .title_bar` → `from ..shared.title_bar`
  - `from .widgets` → `from ..shared.widgets`
  - `from .icons` → `from ..shared.icons`
  - `from .link_chips` → `from ..shared.link_chips`
  - `from .animated_stack` → `from ..shared.animated_stack`
  - `from .widget_pool` → `from ..shared.widget_pool`
- **Verification:** `python -c "from desktop.ui.tasks.task_board import TaskBoardView"` succeeds.

### 2.5 Move calendar files → `desktop/ui/calendar/`
- **Files to move:**
  - `calendar_view.py` → `calendar/calendar_view.py`
  - `agenda_view.py` → `calendar/agenda_view.py`
  - `event_dialog.py` → `calendar/event_dialog.py`
  - `timeline_view.py` → `calendar/timeline_view.py`
- **Action:** `git mv` each file. Update imports:
  - `from ..config` → `from ...config`
  - `from ..database` → `from ...database`
  - `from .dialogs` → `from ..tasks.dialogs` (FramelessDialog used by EventDialog)
  - `from .widgets` → `from ..shared.widgets`
  - `from .icons` → `from ..shared.icons`
  - `from .mime_types` → `from ..shared.mime_types`
  - `from .event_dialog` → `from .event_dialog` (same dir, no change)
- **Verification:** `python -c "from desktop.ui.calendar.calendar_view import CalendarView"` succeeds.

### 2.6 Move view files → `desktop/ui/views/`
- **Files to move:**
  - `dashboard.py` → `views/dashboard.py`
  - `history.py` → `views/history.py`
  - `summary.py` → `views/summary.py`
  - `settings.py` → `views/settings.py`
  - `about.py` → `views/about.py`
  - `sync_view.py` → `views/sync_view.py`
  - `sidebar.py` → `views/sidebar.py`
- **Action:** `git mv` each file. Update imports:
  - `from ..config` → `from ...config`
  - `from ..database` → `from ...database`
  - `from ..styles` → `from ...styles`
  - `from .time_grid` → `from ..time.time_grid`
  - `from .activity_week` → `from ..time.activity_week`
  - `from .widget_pool` → `from ..shared.widget_pool`
  - `from .widgets` → `from ..shared.widgets`
  - `from .icons` → `from ..shared.icons`
  - `from .animated_stack` → `from ..shared.animated_stack`
- **Verification:** `python -c "from desktop.ui.views.dashboard import DashboardView"` succeeds.

### 2.7 Update `desktop/app.py` imports
- **Location:** `desktop/app.py`
- **Action:** Update all view imports from flat `from .ui.X` to nested paths:
  - `from .ui.about import AboutView` → `from .ui.views.about import AboutView`
  - `from .ui.animated_stack import ...` → `from .ui.shared.animated_stack import ...`
  - `from .ui.calendar_view import CalendarView` → `from .ui.calendar.calendar_view import CalendarView`
  - `from .ui.dashboard import DashboardView` → `from .ui.views.dashboard import DashboardView`
  - `from .ui.history import HistoryView` → `from .ui.views.history import HistoryView`
  - `from .ui.settings import SettingsView` → `from .ui.views.settings import SettingsView`
  - `from .ui.sidebar import Sidebar` → `from .ui.views.sidebar import Sidebar`
  - `from .ui.summary import SummaryView` → `from .ui.views.summary import SummaryView`
  - `from .ui.sync_view import SyncView` → `from .ui.views.sync_view import SyncView`
  - `from .ui.task_board import TaskBoardView` → `from .ui.tasks.task_board import TaskBoardView`
  - `from .ui.task_list import TaskListView` → `from .ui.tasks.task_list import TaskListView`
  - `from .ui.time_tracker import TimeTrackerView` → `from .ui.time.time_tracker import TimeTrackerView`
  - `from .ui.title_bar import TitleBar` → `from .ui.shared.title_bar import TitleBar`
  - `from .ui.icons import clear_cache` → `from .ui.shared.icons import clear_cache`
- **Verification:** `python -c "from desktop.app import MainWindow"` succeeds.

### 2.8 Update all test imports
- **Location:** `tests/widget/*.py`
- **Action:** Update imports to match new paths, e.g.:
  - `from grouper.ui.dialogs import ...` → `from desktop.ui.tasks.dialogs import ...`
  - `from grouper.ui.activity_config import ...` → `from desktop.ui.time.activity_config import ...`
  - `from grouper.styles import ...` → `from desktop.styles import ...`
  - `from grouper.models import ...` → `from desktop.models import ...`
- **Verification:** `pytest tests/ --co -q` collects all tests.

### 2.9 Full test run after restructure
- **Action:** `pytest tests/ -v`
- **Verification:** All tests pass. Fix any remaining import issues.

---

## Phase 3: Consolidate card & dialog implementations

### 3.1 Create `BaseCard` in `desktop/ui/shared/base_card.py`
- **Location:** NEW file `desktop/ui/shared/base_card.py`
- **Action:** Extract a shared base class:
  ```python
  class BaseCard(QFrame):
      """Base class for all card-style widgets.
      
      Centralizes:
      - setObjectName("card")
      - Standard content margins (12, 8, 12, 8)
      - Standard spacing (8)
      - WA_StyledBackground attribute
      - Child transparency propagation
      """
      CONTENT_MARGINS = (12, 8, 12, 8)
      CONTENT_SPACING = 8
      
      def __init__(self, parent=None, *, object_name="card"):
          super().__init__(parent)
          self.setObjectName(object_name)
          self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
      
      def _make_row(self) -> QHBoxLayout:
          """Create a standard horizontal card row."""
          row = QHBoxLayout(self)
          row.setContentsMargins(*self.CONTENT_MARGINS)
          row.setSpacing(self.CONTENT_SPACING)
          return row
      
      def _make_child_transparent(self, widget: QWidget) -> None:
          """Set a widget and its children transparent for mouse events (drag passthrough)."""
          widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
          for child in widget.findChildren(QWidget):
              child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
  ```
- **Verification:** `python -c "from desktop.ui.shared.base_card import BaseCard"` succeeds.

### 3.2 Refactor simple card subclasses to use `BaseCard`
- **Files to modify:**
  - `desktop/ui/views/dashboard.py` — `_SessionCard`, `_TaskCard` (currently ~30 LOC each)
  - `desktop/ui/views/history.py` — `_TaskHistoryCard`, `_SessionHistoryCard`
- **Action:** Change `class _XxxCard(QFrame)` → `class _XxxCard(BaseCard)` and remove duplicated `__init__` boilerplate (setObjectName, layout setup). Keep view-specific fields.
- **Verification:** `pytest tests/widget/test_dashboard_layout.py tests/widget/test_taskbox_elide.py -v` passes.

### 3.3 Refactor complex card subclasses
- **Files to modify:**
  - `desktop/ui/time/session_card.py` — `SessionCard` (130 LOC)
  - `desktop/ui/time/activity_card.py` — `ActivityCard` (60 LOC)
  - `desktop/ui/tasks/task_board.py` — `TaskCard` (400 LOC)
  - `desktop/ui/calendar/timeline_view.py` — `_TimelineCard` (100 LOC)
- **Action:** Change base class to `BaseCard`. Remove duplicated init boilerplate. Keep all domain-specific logic (signals, drag-and-drop, action rows).
- **Verification:** `pytest tests/ -v` passes.

### 3.4 Create `BaseFormDialog` in `desktop/ui/shared/base_dialog.py`
- **Location:** NEW file `desktop/ui/shared/base_dialog.py`
- **Action:** Extract shared dialog patterns from `FramelessDialog` and its subclasses:
  ```python
  class BaseFormDialog(FramelessDialog):
      """FramelessDialog with standard form layout + Ok/Cancel buttons.
      
      Provides:
      - QFormLayout with standard spacing
      - Ok/Cancel button box (accessible as self._buttons)
      - set_error(widget) helper for field validation
      """
      def __init__(self, title: str, min_width=380, parent=None):
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
      
      def add_form_row(self, label, widget):
          self._form.addRow(label, widget)
      
      def finalize_form(self):
          """Add the button box to the form. Call after all rows are added."""
          self._form.addRow(self._buttons)
      
      def set_field_error(self, widget, has_error=True):
          widget.setProperty("error", has_error)
          widget.style().unpolish(widget)
          widget.style().polish(widget)
  ```
- **Verification:** `python -c "from desktop.ui.shared.base_dialog import BaseFormDialog"` succeeds.

### 3.5 Refactor dialog subclasses to use `BaseFormDialog`
- **Files to modify:**
  - `desktop/ui/tasks/dialogs.py` — Refactor these to use `BaseFormDialog`:
    - `CreateActivityDialog` (~40 LOC → ~15 LOC)
    - `CreateProjectDialog` (~40 LOC → ~15 LOC)
    - `EditProjectDialog` (~60 LOC → ~30 LOC)
    - `EditBoardDialog` (~50 LOC → ~25 LOC)
    - `AddBoardDialog` (~30 LOC → ~12 LOC)
    - `AddGroupDialog` (~50 LOC → ~25 LOC)
    - `StopSessionDialog` (~40 LOC → ~20 LOC)
    - `ConfirmDialog` — leave as-is (too simple, different button pattern)
  - `desktop/ui/calendar/event_dialog.py` — `EventDialog` uses custom button layout; adapt carefully.
- **Action:** Replace duplicated form boilerplate with `BaseFormDialog` methods. Keep all domain-specific fields and logic.
- **Verification:** `pytest tests/widget/test_dialogs.py -v` passes.

### 3.6 Centralize transparency handling
- **Location:** `desktop/ui/shared/base_card.py` and `desktop/ui/shared/base_dialog.py`
- **Action:**
  1. In `BaseCard.__init__()`, ensure `WA_StyledBackground` is always set (prevents the transparency bleed-through bug where parent widget background shows through card).
  2. In `FramelessDialog.__init__()` (in `desktop/ui/tasks/dialogs.py`), ensure both `dialogFrame` and `dialogContent` have `WA_StyledBackground = True` and that the outer margin container sets `autoFillBackground = True` with the correct palette color (not relying on transparent defaults).
  3. Add a comment block in `base_card.py` documenting the transparency contract: "All card widgets MUST use WA_StyledBackground. The QSS rule `#card QWidget { background-color: transparent; }` relies on the card itself having an opaque styled background."
- **Verification:** `pytest tests/widget/test_transparency.py -v` passes (these tests are the authoritative guard).

### 3.7 Update `about.py` card usage
- **Location:** `desktop/ui/views/about.py`
- **Action:** The about page creates a `QFrame` with `setObjectName("card")`. Replace with `BaseCard` for consistency.
- **Verification:** `pytest tests/widget/test_theme_load.py -v` passes.

---

## Phase 4: Final verification & cleanup

### 4.1 Run full test suite
- **Action:** `pytest tests/ -v --tb=short`
- **Verification:** All tests pass.

### 4.2 Run ruff linting
- **Action:** `ruff check desktop/ tests/`
- **Verification:** No errors. Fix any F401 (unused imports from moves) or F403 issues.

### 4.3 Verify entry point
- **Action:** `python -m desktop` or `grouper` (if installed) launches the app without error.
- **Verification:** App window appears.

### 4.4 Update pyproject.toml per-file-ignores
- **Location:** `pyproject.toml`
- **Action:** Ensure all `[tool.ruff.lint.per-file-ignores]` entries use `desktop/` paths:
  ```
  "desktop/config.py" = ["F401", "F403"]
  "desktop/formatting.py" = ["F401", "F403"]
  "desktop/models.py" = ["F401", "F403"]
  "desktop/operations.py" = ["F401", "F403"]
  "desktop/styles/colors.py" = ["F401", "F403"]
  "desktop/database/*.py" = ["F403"]
  "desktop/database/connection.py" = ["F401"]
  ```
- **Verification:** `ruff check desktop/` passes.

### 4.5 Delete stale `__pycache__` directories
- **Action:** `Get-ChildItem -Path . -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force`
- **Verification:** No `__pycache__` directories remain.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Circular imports from deeper nesting | Medium | High — app won't start | The shared/ sub-package has no imports from sibling sub-packages (time/, tasks/, calendar/, views/). Verify with `ruff` and by running the app after Phase 2. |
| Test breakage from import path changes | High | Medium — CI red | Phase 2.8 explicitly updates all test imports. Run `pytest --co -q` after every sub-step. |
| Transparency regression from BaseCard refactor | Low | High — visual glitch | Phase 3.6 centralizes transparency handling. `test_transparency.py` (300 LOC of pixel-level tests) is the guard. Run it after every card refactor. |
| Drag-and-drop breakage in TaskCard/ActivityCard refactor | Low | Medium — feature broken | The `_set_drag_passthrough` calls in TaskCard and the DragHandleButton in ActivityCard are specific to those classes. BaseCard only provides a helper, doesn't change behavior. Run `test_task_board_drag.py` after refactoring. |
| `grouper.egg-info` stale metadata | High | Low — wrong package found | Phase 1.6 explicitly deletes egg-info and re-installs. |
| External tools/scripts reference `grouper.` package | Low | Low | The `[project.gui-scripts]` entry point `grouper` command name is unchanged. Only internal imports change. Other packages (CLI, server) use `grouper_core`, not `grouper`. |
| Moving `dialogs.py` splits `FramelessDialog` from its subclasses | Medium | Low | `FramelessDialog` stays in `tasks/dialogs.py`. All dialog subclasses are already in that file. `EventDialog` in `calendar/event_dialog.py` imports from `..tasks.dialogs`. No circular dependency. |

## Verification

## Verification strategy

### After Phase 1 (rename)
```bash
python -c "import desktop; print(desktop.__version__)"
python -c "from desktop.app import MainWindow"
pytest tests/ --co -q
pytest tests/ -v
```

### After Phase 2 (restructure)
```bash
# Verify every module is importable at its new path
python -c "from desktop.ui.shared.widgets import ElidedLabel, BaseCard"
python -c "from desktop.ui.shared.animated_stack import AnimatedViewStack"
python -c "from desktop.ui.time.time_tracker import TimeTrackerView"
python -c "from desktop.ui.tasks.task_board import TaskBoardView"
python -c "from desktop.ui.tasks.dialogs import FramelessDialog"
python -c "from desktop.ui.calendar.calendar_view import CalendarView"
python -c "from desktop.ui.views.dashboard import DashboardView"
python -c "from desktop.ui.views.summary import SummaryView"
python -c "from desktop.ui.views.sync_view import SyncView"
python -c "from desktop.app import MainWindow"
pytest tests/ -v
```

### After Phase 3 (card/dialog consolidation)
```bash
# Transparency is the most fragile area
pytest tests/widget/test_transparency.py -v
# Dialog API must be preserved
pytest tests/widget/test_dialogs.py -v
# Drag-and-drop in cards
pytest tests/widget/test_task_board_drag.py -v
# Dashboard cards
pytest tests/widget/test_dashboard_layout.py tests/widget/test_taskbox_elide.py -v
# Full suite
pytest tests/ -v
ruff check desktop/ tests/
```

### Final sign-off
```bash
pytest tests/ -v
ruff check desktop/ tests/
pip install -e . && grouper  # launches app visually
```
