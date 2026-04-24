# Plan: Unit Test Revamp — Replace E2E Suite + Add Visual Regression Coverage

**Branch:** `feat/test-revamp`
**Date:** 2026-04-21

## Goal

1. Remove the broken pywinauto-based e2e test suite (`tests/e2e/`).
2. Replace its coverage with solid widget-level and unit tests that don't require subprocess launching, UI automation, or external dependencies (pywinauto, mss, psutil).
3. Add a transparent-background detection framework — systematic widget-level tests that catch unintended transparency / invisible-surface regressions across all themes.
4. Address broader deficiencies in the existing unit/widget test suites where they impact coverage gaps left by removing e2e tests.

---

## Current State

### E2E test suite (to be removed)

`tests/e2e/` contains 4 files:
- `__init__.py` (empty)
- `conftest.py` — launches app subprocess, connects pywinauto, screenshot capture
- `helpers.py` — pywinauto navigation/finder/database-seeding utilities
- `test_app.py` — 5 tests: `test_app_launches_and_renders`, `test_sidebar_navigation_all_views`, `test_title_bar_controls`, `test_theme_switch_survives`, `test_session_lifecycle`

Dependencies: `pywinauto`, `mss`, `psutil` — heavyweight, Windows-only, timing-sensitive, brittle.

### What the e2e tests cover and where replacement tests must go

| E2E Test | Coverage | Replacement Location |
|---|---|---|
| `test_app_launches_and_renders` | MainWindow construction, title, visibility, dashboard heading | New `tests/widget/test_main_window.py` |
| `test_sidebar_navigation_all_views` | Sidebar button → view mapping | New `tests/widget/test_sidebar.py` |
| `test_title_bar_controls` | Min/max/close buttons, maximize toggle | Already extensively covered in `tests/widget/test_title_bar_unit.py` (22+ tests) |
| `test_theme_switch_survives` | Theme loading, navigation after theme switch | New `tests/widget/test_theme_load.py` |
| `test_session_lifecycle` | Start/pause/resume/stop session flow | Already extensively covered in `tests/unit/db/test_integration.py` (13 tests) and `tests/cli/test_e2e.py` (46 tests) |

### Key source files for transparent-background testing

- `grouper/ui/dialogs.py` — `FramelessDialog` base class:
  - Sets `WA_TranslucentBackground` on the QDialog (line 75)
  - Inner `QFrame` with `objectName("dialogFrame")`, `setAutoFillBackground(True)`
  - Inner content `QWidget` with `objectName("dialogContent")`
  - `QGraphicsDropShadowEffect` for shadow
  - 10 dialog subclasses inherit from it

- `grouper/styles/_base.qss`:
  - `#dialogFrame`: `background-color: {{bg-primary}}`, `border: 1px solid {{border}}`
  - `#dialogContent`: `background-color: {{bg-primary}}`
  - `#dialogTitleBar`: `background-color: {{bg-secondary}}`
  - `QDialog`: `background-color: {{bg-primary}}`

- `grouper_core/colors.py` — 8 themes in `_THEME_PALETTE`, each with ~100 tokens

- `grouper/styles/__init__.py` — `load_theme(app, theme)` renders QSS template and applies stylesheet

### Existing test coverage gaps

1. **Theme validation** (`tests/widget/test_theme_validation.py`): Only checks `danger`/`success` hex validity and that they differ. Does NOT check:
   - All required tokens exist in every theme
   - Critical background tokens (`bg-primary`, `bg-secondary`, `border`) are present and valid
   - QSS template references match available palette tokens
   - Dialog surface tokens if/when they are added per the contrast-fix plan

2. **Theme loading** (`load_theme`): No tests for the template rendering pipeline.

3. **Dialog construction**: No widget tests for `FramelessDialog` or any of its 10 subclasses.

4. **Transparent-background detection**: Zero coverage. No mechanism to detect when widgets render as invisible or when surfaces blend into the background.

5. **MainWindow construction**: Only tested indirectly via title-bar tests. No direct construction/view-mapping tests.

6. **Sidebar**: No widget tests for navigation button → view index mapping.

---

## Implementation Steps

### Phase 1: Remove e2e test suite

**Step 1.1** — Delete the e2e test directory

- Delete: `tests/e2e/__init__.py`
- Delete: `tests/e2e/conftest.py`
- Delete: `tests/e2e/helpers.py`
- Delete: `tests/e2e/test_app.py`
- Delete: `tests/e2e/` directory

**Step 1.2** — Clean up pytest configuration

- In `pyproject.toml` `[tool.pytest.ini_options]`:
  - Remove `"e2e: end-to-end tests launching the full app subprocess"` from `markers` (the `e2e` marker is no longer used)
  - Keep `widget` and `slow` markers

**Verification:**
- `uv run pytest tests/ --co -q` lists no e2e tests
- `uv run pytest tests/ -v --ignore=tests/e2e` passes (same as before minus e2e)

---

### Phase 2: Add transparent-background detection framework

This is the core new testing infrastructure. It provides reusable helpers that any widget test can use to verify opacity and visual distinction.

**Step 2.1** — Create `tests/widget/test_transparency.py`

This file provides the core transparency-detection test infrastructure.

**Test approach — two-tier detection:**

**Tier 1: Palette-level contrast checks (pure Python, no Qt rendering required)**
For each theme, verify that dialog-critical color tokens produce sufficient visual separation from the page background. This catches the root cause (same color used for page and dialog) before any rendering happens.

```python
class TestPaletteContrastForDialogs:
    """Verify dialog surfaces are visually distinct from page background in every theme."""

    def test_dialog_frame_differs_from_page_bg(self):
        """#dialogFrame uses bg-primary but must be distinguishable from the page
        behind it. The dialog's actual visual distinction comes from the combination
        of bg-primary on dialogFrame + bg-secondary on titleBar + border.
        Verify that at least one of these differs from bg-primary by a meaningful amount."""
        # For each theme, compute perceptual contrast between bg-primary and:
        #   (a) bg-secondary (title bar)
        #   (b) border
        # Assert at least one exceeds a minimum luminance delta.

    def test_all_themes_have_dialog_critical_tokens(self):
        """Every theme must define bg-primary, bg-secondary, border, text, text-muted."""

    def test_no_theme_has_identical_bg_primary_and_bg_secondary(self):
        """bg-primary and bg-secondary must differ — they define surface separation."""

    def test_border_differs_from_bg_primary(self):
        """border must be distinguishable from bg-primary."""
```

Helper function to add (module-level or in conftest):
```python
def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert '#rrggbb' to (r, g, b)."""

def _relative_luminance(hex_str: str) -> float:
    """Compute relative luminance per WCAG 2.0."""

def _contrast_ratio(c1: str, c2: str) -> float:
    """WCAG 2.0 contrast ratio between two hex colors."""

def _perceptual_delta(c1: str, c2: str) -> float:
    """Simple Euclidean RGB distance, normalized to 0-1 range."""
```

**Tier 2: Pixel-level opacity checks (Qt rendering, requires QApplication)**
Render widgets offscreen and verify that their rendered surfaces are fully opaque where expected.

```python
class TestFramelessDialogOpacity:
    """Verify FramelessDialog renders opaque pixels in its content area."""

    @pytest.mark.parametrize("theme", available_themes())
    def test_dialog_content_is_opaque(self, qapp, theme):
        """Grab a pixel from the dialog content area and verify alpha == 255."""
        # 1. load_theme(qapp, theme)
        # 2. Create a FramelessDialog subclass (e.g. ConfirmDialog or a minimal test dialog)
        # 3. Show it (required for grab() to work)
        # 4. dlg.grab().toImage()
        # 5. Sample a pixel from the center of dialogContent
        # 6. Assert pixel.alpha() == 255

    @pytest.mark.parametrize("theme", available_themes())
    def test_dialog_frame_is_opaque(self, qapp, theme):
        """Grab a pixel from the dialog frame area and verify alpha == 255."""
        # Similar approach, sampling from dialogFrame region

    @pytest.mark.parametrize("theme", ["black", "dark", "light", "oxygen"])
    def test_dialog_body_differs_from_plain_page(self, qapp, theme):
        """The dialog body color must be perceptually distinguishable from
        a plain QWidget rendered with the same theme.
        This catches the 'transparent-looking dialog' bug where dialog and page
        share the same bg-primary."""
        # 1. load_theme(qapp, theme)
        # 2. Create a plain QWidget, show it, grab pixel from center
        # 3. Create a FramelessDialog, show it, grab pixel from dialogContent center
        # 4. Assert the colors are NOT identical, OR assert that the combined
        #    dialog chrome (title bar + border + frame) provides sufficient visual contrast
```

**Helper for dialog testing:**
```python
@pytest.fixture
def themed_dialog(qapp):
    """Create a minimal FramelessDialog with the given theme applied."""
    def _make(theme: str = "dark"):
        from grouper.styles import load_theme
        from grouper.ui.dialogs import ConfirmDialog
        load_theme(qapp, theme)
        dlg = ConfirmDialog("Test", "Body text", None)
        dlg.move(100, 100)
        dlg.resize(400, 300)
        dlg.show()
        qapp.processEvents()
        return dlg
    return _make
```

**Pixel sampling approach:**
```python
def _sample_pixel(image, x: int, y: int) -> QColor:
    """Sample a pixel from a QImage at the given coordinates."""
    from PySide6.QtGui import QColor
    return QColor(image.pixel(x, y))

def _find_dialog_content_center(dialog) -> tuple[int, int]:
    """Find the center of the dialogContent widget in dialog coordinates."""
    content = dialog.findChild(QWidget, "dialogContent")
    if content is None:
        pytest.skip("dialogContent not found")
    geo = content.geometry()
    return (geo.x() + geo.width() // 2, geo.y() + geo.height() // 2)
```

**Verification:**
- `uv run pytest tests/widget/test_transparency.py -v` — all tests pass
- Manually verify: change `bg-primary` and `bg-secondary` to the same value in the `black` theme in `grouper_core/colors.py`, re-run, see `test_dialog_body_differs_from_plain_page` fail for `black`

---

### Phase 3: Add missing widget/unit tests for e2e coverage gaps

**Step 3.1** — Create `tests/widget/test_main_window.py`

Covers: MainWindow construction, title, central widget layout, view stack existence.

```python
class TestMainWindowConstruction:
    """Replace e2e test_app_launches_and_renders with widget-level tests."""

    def test_window_title_contains_grouper(self, main_window):
        """Window title includes 'Grouper'."""
        # Use the existing main_window fixture pattern from test_title_bar_unit.py

    def test_central_widget_exists(self, main_window):
        """MainWindow has a central widget (_BorderedCentral)."""

    def test_stack_widget_exists(self, main_window):
        """MainWindow contains the animated stack for views."""

    def test_sidebar_exists(self, main_window):
        """MainWindow contains the sidebar navigation."""

    def test_title_bar_exists(self, main_window):
        """MainWindow contains the custom title bar."""

    def test_stack_has_expected_view_count(self, main_window):
        """The view stack should contain one widget per registered view."""
```

Reuse the `main_window` fixture pattern from `tests/widget/test_title_bar_unit.py` (mock config/theme, construct MainWindow).

**Step 3.2** — Create `tests/widget/test_sidebar.py`

Covers: Sidebar button → view index mapping.

```python
class TestSidebarNavigation:
    """Replace e2e test_sidebar_navigation_all_views."""

    def test_sidebar_has_all_view_buttons(self, main_window):
        """Sidebar has a button for every registered view."""

    def test_view_names_match_stack_indices(self, main_window):
        """Each sidebar button maps to the correct stack index."""

    def test_clicking_sidebar_button_switches_stack(self, main_window, qapp):
        """Clicking a sidebar button changes the current stack index."""
```

**Step 3.3** — Create `tests/widget/test_theme_load.py`

Covers: load_theme pipeline, theme switching, stylesheet application.

```python
class TestLoadTheme:
    """Replace e2e test_theme_switch_survives with unit-level tests."""

    def test_load_theme_produces_nonempty_stylesheet(self, qapp):
        """load_theme returns a non-empty stylesheet string."""
        # Actually call load_theme and verify qapp.setStyleSheet was called with non-empty string

    def test_load_theme_replaces_all_tokens(self, qapp):
        """No unresolved {{token}} placeholders remain in the rendered QSS."""
        # Load theme, get stylesheet, assert no '{{' remaining

    @pytest.mark.parametrize("theme", available_themes())
    def test_every_theme_loads_without_error(self, qapp, theme):
        """load_theme does not raise for any registered theme."""

    def test_theme_switch_changes_stylesheet(self, qapp):
        """Switching from dark to light produces a different stylesheet."""

    def test_theme_switch_preserves_window_visibility(self, main_window, qapp):
        """After switching themes, the main window remains visible and functional."""
```

**Step 3.4** — Create `tests/widget/test_dialogs.py`

Covers: FramelessDialog and subclass construction, layout, styling attributes.

```python
class TestFramelessDialog:
    """Test FramelessDialog base class construction and attributes."""

    def test_has_translucent_background_attribute(self, qapp):
        """FramelessDialog sets WA_TranslucentBackground."""
        # Create a FramelessDialog, check testAttribute(WA_TranslucentBackground)

    def test_has_frameless_window_hint(self, qapp):
        """FramelessDialog uses FramelessWindowHint."""

    def test_dialog_frame_has_auto_fill_background(self, qapp):
        """The inner dialogFrame sets autoFillBackground=True."""

    def test_dialog_frame_object_name(self, qapp):
        """Inner QFrame has objectName 'dialogFrame'."""

    def test_dialog_content_object_name(self, qapp):
        """Inner content widget has objectName 'dialogContent'."""

    def test_dialog_has_drop_shadow(self, qapp):
        """Dialog container has a QGraphicsDropShadowEffect."""

class TestDialogSubclasses:
    """Verify all FramelessDialog subclasses construct without error."""

    @pytest.mark.parametrize("dialog_class", [
        "CreateActivityDialog",
        "CreateProjectDialog",
        "EditProjectDialog",
        "EditBoardDialog",
        "AddBoardDialog",
        "CreateTaskDialog",
        "StopSessionDialog",
        "ConfirmDialog",
        "AddGroupDialog",
    ])
    def test_dialog_constructs(self, qapp, dialog_class):
        """Each dialog subclass can be constructed without errors."""
        # For dialogs that require arguments, provide minimal mocks
```

**Verification:**
- `uv run pytest tests/widget/test_main_window.py tests/widget/test_sidebar.py tests/widget/test_theme_load.py tests/widget/test_dialogs.py -v` — all pass

---

### Phase 4: Strengthen existing theme validation

**Step 4.1** — Extend `tests/widget/test_theme_validation.py`

Add these tests to the existing file:

```python
class TestThemeTokenCompleteness:
    """Verify every theme has all required color tokens."""

    REQUIRED_TOKENS = [
        "bg-primary", "bg-secondary", "bg-tertiary", "bg-sidebar",
        "border", "text", "text-muted",
        "accent", "accent-hover", "accent-active",
        "danger", "success", "warning",
        # Dialog-critical tokens (when added, extend this list)
        # "dialog-bg", "dialog-content-bg", "dialog-title-bg", "dialog-border",
    ]

    def test_all_themes_have_required_tokens(self):
        """Every theme in _THEME_PALETTE defines all REQUIRED_TOKENS."""

    def test_all_token_values_are_valid_hex(self):
        """Every token value in every theme matches #[0-9a-fA-F]{6}."""

    def test_no_duplicate_tokens_within_theme(self):
        """Token keys are unique within each theme (sanity check)."""

class TestQssTemplateTokenCoverage:
    """Verify QSS template tokens match available palette tokens."""

    def test_all_qss_tokens_have_palette_values(self):
        """Every {{token}} in _base.qss has a corresponding entry in every theme palette."""

    def test_no_unresolved_tokens_after_render(self):
        """Rendering the QSS with any theme leaves no {{token}} placeholders."""
```

**Verification:**
- `uv run pytest tests/widget/test_theme_validation.py -v` — all pass

---

### Phase 5: Final quality checks

**Step 5.1** — Run full test suite
```bash
uv run pytest tests/ -v --ignore=tests/e2e
```

**Step 5.2** — Run linting and type checking
```bash
uv run ruff check .
uv run ty check
```

**Step 5.3** — Update project context
- Update `.agents/context/STATUS.md` — note e2e removal and new test coverage
- Update `.agents/context/NOTES.md` — update quick commands if needed

---

## File Change Summary

### Delete
- `tests/e2e/__init__.py`
- `tests/e2e/conftest.py`
- `tests/e2e/helpers.py`
- `tests/e2e/test_app.py`

### Create
- `tests/widget/test_transparency.py` — transparent-background detection framework
- `tests/widget/test_main_window.py` — MainWindow construction tests
- `tests/widget/test_sidebar.py` — sidebar navigation tests
- `tests/widget/test_theme_load.py` — theme loading pipeline tests
- `tests/widget/test_dialogs.py` — FramelessDialog construction and subclass tests

### Modify
- `pyproject.toml` — remove `e2e` marker from pytest config
- `tests/widget/test_theme_validation.py` — add token completeness and QSS coverage tests

---

## Risks and Decisions

### Risk: Offscreen rendering may behave differently across platforms
- **Mitigation:** Pixel-level tests sample relative positions (centers, not absolute coords). Use `qapp.processEvents()` and `show()` to ensure layout is computed. If CI runs headless, use `QT_QPA_PLATFORM=offscreen`.

### Risk: `grab()` may produce all-transparent on some backends
- **Mitigation:** The palette-level contrast checks (Tier 1) don't depend on rendering at all. If pixel tests are flaky, the palette tests still catch the root cause. Mark pixel tests with `@pytest.mark.widget` so they can be filtered.

### Risk: Some dialog subclasses require complex argument setup
- **Mitigation:** Use minimal mocks for required arguments (activity lists, task objects, etc.). Test construction only, not full interaction flow.

### Decision: Two-tier transparency detection
- **Tier 1 (palette-level):** Fast, deterministic, no Qt rendering. Catches the root cause (color collision).
- **Tier 2 (pixel-level):** Slower, requires QApplication, but catches rendering-specific issues. Only parametrized over key themes for speed.
- **Why both:** Tier 1 catches the class of bugs seen so far (same color → invisible). Tier 2 catches future rendering regressions.

### Decision: Keep the fixture pattern from test_title_bar_unit.py
- The `main_window` fixture with mocked config/theme is proven and avoids importing the full app. Reuse it in new test files.

### Decision: EditTaskDialog excluded from simple construction tests
- `EditTaskDialog` requires a full task object and many UI elements. Skip it in the simple construction sweep or mock aggressively. Other 9 subclasses are straightforward to construct.

---

## Expected End State

- No `tests/e2e/` directory. No pywinauto, mss, or psutil test dependencies.
- ~30-40 new widget tests covering MainWindow, sidebar, theme loading, dialog construction, and transparency detection.
- Transparent-background regressions caught at two levels: palette contrast checks (fast) and pixel opacity checks (rendering-verified).
- Theme validation extended to verify token completeness and QSS template coverage.
- All existing tests unaffected and passing.
- Full test suite runs in seconds, not minutes (no subprocess launching).
