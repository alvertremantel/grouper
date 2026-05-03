# Standardize Frameless Dialog Styling and Drag Behavior

**Date:** 2026-04-26
**Status:** draft

---

## Goal

Implement a shared, parent-proof dialog framework so every frameless dialog uses the same chrome, surface colors, and drag behavior regardless of where it is opened. Specifically, make `EditBoardDialog` (Task Board → Edit Board) and `AddGroupDialog` (Time Tracker → Edit Activities → selected activity → Add Group/Add Tag) render through the same dialog styling path, remove the visible 16px parent-color band around `AddGroupDialog`, slightly reduce the brightness of the intended elevated dialog colors, and restore click-drag movement on dialog title bars.

The outcome should preserve the design intent that dialogs are slightly elevated/desaturated relative to the page, but make that elevation less aggressive and consistent across themes and parent widgets.
## Understanding

Relevant current state:

- `desktop/ui/shared/base_dialog.py:23-76` defines `FramelessDialog`. It creates a `QDialog` with `FramelessWindowHint | Dialog`, calls `self.setAutoFillBackground(True)` at line 37, creates a styled `QFrame` named `dialogFrame` at lines 39-47 with a drop shadow, and wraps that frame in `self._outer_layout` with `16px` margins at lines 49-51. Those margins are the shadow gutter; when the top-level `QDialog` paints opaquely, the gutter appears as a thick border.
- `desktop/ui/shared/base_dialog.py:79-120` defines `BaseFormDialog`. It always creates `self._form` (`QFormLayout`) at lines 94-96 and `self._buttons` (`QDialogButtonBox`) at lines 97-101. It only supports the form-layout pattern directly.
- `desktop/ui/tasks/dialogs.py:173-214` defines `EditBoardDialog`. It follows `BaseFormDialog` normally: `super().__init__("Edit Board", 380, parent)` at line 177, adds a `QLineEdit` via `add_row()` at lines 181-183, calls `finalize_form()` at line 186, then appends a `dangerButton` delete action at lines 189-194.
- `desktop/ui/tasks/dialogs.py:663-710` defines `AddGroupDialog`. It also inherits `BaseFormDialog`, but immediately removes the form layout via `self.contentLayout().removeItem(self._form)` at lines 670-671, then manually stacks labels, `QLineEdit`, optional `QListWidget`, and `self._buttons` directly into `contentLayout()` at lines 673-699. This is the exact structural pattern that should be eliminated and regression-tested against.
- `desktop/ui/tasks/dialogs.py:603-645` defines `StopSessionDialog`, which uses the same `BaseFormDialog`-then-`removeItem(self._form)` escape hatch at lines 609-612. It is not one of the two user-facing dialogs in scope, but it should migrate to the new custom-content base class so the bad pattern is removed from the codebase rather than left as a template for future dialogs.
- `desktop/ui/tasks/dialogs.py:647-660` defines `ConfirmDialog` directly on `FramelessDialog`, with its own `QDialogButtonBox`. It is structurally fine but can remain as-is unless the implementer chooses to migrate it to the new button-dialog base for consistency.
- `desktop/ui/time/activity_config.py:557-575` opens `AddGroupDialog` from `_ActivityDetailEditor._add_group()` with `_ActivityDetailEditor` as parent. `_ActivityDetailEditor` sets `self.setObjectName("card")` at `desktop/ui/time/activity_config.py:425`, so this dialog is parented beneath `#card`.
- `desktop/ui/time/activity_config.py:596-611` reuses `AddGroupDialog` for tags and then calls `dlg.setWindowTitle("Add Tag")` at line 603. The current class still exposes the result as `selected_group`; preserve this public attribute for compatibility with existing callers.
- `desktop/styles/_base.qss:85-127` styles `#dialogTitleBar`, `#dialogFrame`, and `#dialogContent` using `{{dialog-title-bg}}`, `{{dialog-bg}}`, `{{dialog-border}}`, and `{{dialog-content-bg}}`. The duplicated `#card #dialogFrame` / `#card #dialogContent` selectors exist to outrank `#card QWidget { background-color: transparent; }` at lines 193-195 and should remain unless replaced with selectors of equal or higher specificity.
- `desktop/styles/_base.qss:201-204` contains the problematic parent override: `#card QDialog { background-color: {{bg-secondary}}; }`. This causes `AddGroupDialog`'s top-level `QDialog` shadow gutter to paint as a solid `bg-secondary` band whenever opened under `_ActivityDetailEditor`.
- `desktop/styles/_base.qss:556-560` contains the global fallback `QDialog { background-color: {{bg-primary}}; }` used by non-specialized dialogs.
- `grouper_core/colors.py:652-700` defines the intended dialog-specific palette. Current dark theme dialog values are notably brighter/desaturated than standard panels: `dialog-bg=#2f3146`, `dialog-title-bg=#3b3d57`, `dialog-border=#565f89` versus `bg-secondary=#24263a` and `border=#3b3d57`.
- `desktop/ui/shared/title_bar.py:163-219` defines `DialogTitleBar`. Its drag handlers return immediately on Windows at lines 195-197, 206-208, and 215-217. The main-window `TitleBar` has a separate Windows native-event implementation in `desktop/app.py`, but dialogs do not, so frameless dialogs cannot be dragged on Windows.
- Existing tests:
  - `tests/widget/test_dialogs.py:32-72` verifies the base dialog structure and currently asserts no `WA_TranslucentBackground` at lines 35-40.
  - `tests/widget/test_dialogs.py:75-98` constructs all task dialogs, including `EditBoardDialog` and `AddGroupDialog`.
  - `tests/widget/test_transparency.py:140-176` validates dialog palette token presence/contrast.
  - `tests/widget/test_transparency.py:177-256` performs screen-pixel checks for opaque dialog frame/content and chrome separation.
  - `tests/widget/test_transparency.py:258-360` specifically tests `AddGroupDialog` when parented to `_ActivityDetailEditor`.
  - `tests/widget/test_theme_validation.py:39-90` validates required theme/QSS tokens.
- `STATUS.md` and `NOTES.md` do not currently exist at repository root. The implementing agent must create them, or update them if they appear before implementation completes.
## Approach

Make the fix at the shared dialog layer rather than patching `AddGroupDialog` in isolation.

1. **Separate dialog chrome from dialog content patterns.** Keep `FramelessDialog` as the common chrome. Add a new shared base class for non-form dialogs with standard Ok/Cancel (or configurable) buttons so custom-content dialogs never need to inherit `BaseFormDialog` and remove `self._form`. Refactor `BaseFormDialog` to build on that base. Migrate `AddGroupDialog` and `StopSessionDialog` off the form-removal pattern. Add tests that fail if `removeItem(self._form)` is reintroduced in dialog definitions.
2. **Make frameless dialog outer gutters transparent and parent-proof.** The 16px margin in `FramelessDialog` is for the drop shadow, not a visible border. Set the frameless dialog object name and transparency behavior explicitly, target it with a dedicated QSS selector, and remove the `#card QDialog` override. Keep `dialogFrame`/`dialogContent` styled and opaque so the old black-margin bug does not return.
3. **Tone down, not remove, the intended dialog elevation.** Update `grouper_core/colors.py` dialog tokens to values closer to each theme's standard panel colors while preserving a visible title-bar/border/content distinction. Use the exact replacement values listed in the steps below so the visual change is deterministic and testable.
4. **Restore dialog dragging in `DialogTitleBar`.** The Windows early returns are correct for the main app `TitleBar`, which has native hit testing, but wrong for `DialogTitleBar`. Remove the Windows guards from `DialogTitleBar` drag methods only, leaving the main `TitleBar` Windows behavior unchanged.
5. **Codify behavior in tests.** Update existing widget tests for the new transparency contract, add drag tests, add parented-`AddGroupDialog` styling tests, and add static QSS/source regression tests that protect against the two root causes: `#card QDialog` and `removeItem(self._form)`.

Cost/benefit: this touches shared dialog infrastructure and several tests, so the change is broader than a one-line style patch. The benefit is that future dialogs will be routed through explicit base classes (`BaseFormDialog` for form rows, new custom-content base for stacked content) and cannot accidentally recreate the AddGroupDialog parent-cascade bug without failing tests.

## Steps

### Phase 1: Shared dialog base classes

1. **Update `FramelessDialog` transparency and identity.**
   - **Location:** `desktop/ui/shared/base_dialog.py:23-76`
   - **Action:** In `FramelessDialog.__init__`, immediately after `super().__init__(parent)`, set a stable object name: `self.setObjectName("framelessDialog")`. Replace the current opaque-gutter behavior at lines 36-37 with the explicit transparent-shadow-gutter contract:
     - `self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)`
     - `self.setAutoFillBackground(False)`
     - Update the class docstring at lines 24-30 to state that only `dialogFrame` and `dialogContent` are opaque/styled; the outer `QDialog#framelessDialog` is transparent so the 16px shadow gutter is not painted as a border.
   - **Verification:** Update/run the base dialog tests in Phase 5 so they assert the new transparency contract. Manually confirm `dialog.findChild(QFrame, "dialogFrame")` and `dialog.findChild(QWidget, "dialogContent")` still exist and are styled backgrounds.

2. **Introduce a custom-content button dialog base.**
   - **Location:** `desktop/ui/shared/base_dialog.py`, between `FramelessDialog` and `BaseFormDialog` (currently around line 79)
   - **Action:** Add a new class, `BaseButtonDialog(FramelessDialog)`, for dialogs that need a vertical content layout plus a standard button box but do not need `QFormLayout`. Required API:
     - `__init__(self, title: str, min_width: int = 380, parent=None, buttons: QDialogButtonBox.StandardButton = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)`
     - Calls `super().__init__(parent)`, `self.setWindowTitle(title)`, `self.setMinimumWidth(min_width)`.
     - Creates `self._buttons = QDialogButtonBox(buttons)` and connects `accepted` to `self.accept` and `rejected` to `self.reject` by default.
     - Initializes `self._buttons_finalized = False`.
     - Provides `finalize_content(self) -> None`: if `_buttons_finalized` is already true, raise `RuntimeError("Dialog buttons already finalized")`; otherwise append `self._buttons` to `self.contentLayout()` and set `_buttons_finalized = True`.
     - Provides `set_accept_handler(self, handler) -> None`: disconnect the default `accepted -> self.accept` connection if present, then connect `accepted` to `handler`. Use `try: self._buttons.accepted.disconnect(self.accept) except (TypeError, RuntimeError): pass` to tolerate PySide's behavior when no matching connection exists; do not call bare `disconnect()` because that can remove unrelated connections added by subclasses.
   - **Verification:** Add tests in `tests/widget/test_dialogs.py` that instantiate a tiny test subclass of `BaseButtonDialog`, call `finalize_content()`, and assert exactly one `QDialogButtonBox` exists under `dialogContent`. Add a second test that calling `finalize_content()` twice raises `RuntimeError`.

3. **Refactor `BaseFormDialog` to inherit from the new base.**
   - **Location:** `desktop/ui/shared/base_dialog.py:79-120`
   - **Action:** Change `class BaseFormDialog(FramelessDialog)` to `class BaseFormDialog(BaseButtonDialog)`. In its `__init__`, call `super().__init__(title, min_width, parent)` before creating `self._form`. Keep `self._form = QFormLayout()`, `self._form.setSpacing(10)`, and `self.contentLayout().addLayout(self._form)`. Remove the duplicate `self._buttons = QDialogButtonBox(...)` creation and signal connections from `BaseFormDialog`, because `BaseButtonDialog` now owns them. Keep `add_row()`, `add_form_row()`, `finalize_form()`, and `set_field_error()` behavior unchanged.
   - **Verification:** Existing construction tests for all `BaseFormDialog` subclasses in `tests/widget/test_dialogs.py:75-98` must still pass without dialog-specific code changes.

### Phase 2: Dialog subclass restructuring

4. **Migrate `AddGroupDialog` to the custom-content base.**
   - **Location:** `desktop/ui/tasks/dialogs.py:35` and `desktop/ui/tasks/dialogs.py:663-710`
   - **Action:** Import the new `BaseButtonDialog` from `desktop.ui.shared.base_dialog`. Change `class AddGroupDialog(BaseFormDialog)` to `class AddGroupDialog(BaseButtonDialog)`. Remove lines 670-671 (`self.contentLayout().removeItem(self._form)`) entirely. Keep the public constructor signature compatible, but extend it with keyword-only optional parameters for tag reuse:
     - `title: str = "Add Group"`
     - `item_label: str = "group"`
     - `limit_hint: str | None = "max 3 groups per activity"`
     The default group UI text should remain equivalent: `Enter or select a group name (max 3 groups per activity):`.
   - Use `super().__init__(title, 300, parent)` instead of the hardcoded `"Add Group"`. Build the stacked labels/input/list directly into `self.contentLayout()` as it already does. Replace the manual accepted disconnect/reconnect at lines 696-698 with `self.set_accept_handler(self._on_accept)`. Replace `layout.addWidget(self._buttons)` at line 699 with `self.finalize_content()`.
   - Preserve `self.selected_group` and `_select_existing()` / `_on_accept()` semantics so callers at `desktop/ui/time/activity_config.py:568-571` and `603-607` continue working.
   - **Verification:** `tests/widget/test_dialogs.py` construction test for `AddGroupDialog` passes. Add a test that `AddGroupDialog` is an instance of `BaseButtonDialog` but not `BaseFormDialog`, and a test that no `_form` attribute is required to construct it.

5. **Use the new tag-specific constructor path.**
   - **Location:** `desktop/ui/time/activity_config.py:596-604`
   - **Action:** Replace the current pattern:
     - `dlg = AddGroupDialog(all_tags, self._activity.tags, self)`
     - `dlg.setWindowTitle("Add Tag")`
     with a single constructor call using the new keyword arguments, for example:
     - `dlg = AddGroupDialog(all_tags, self._activity.tags, self, title="Add Tag", item_label="tag", limit_hint=None)`
   - The tag dialog text should say `Enter or select a tag name:` and should not mention the three-group limit.
   - **Verification:** Add/adjust a widget test that constructs the tag variant and asserts `dialog.windowTitle() == "Add Tag"`, the info label contains `tag name`, and the info label does not contain `max 3 groups`.

6. **Migrate `StopSessionDialog` off the form-removal pattern.**
   - **Location:** `desktop/ui/tasks/dialogs.py:603-645`
   - **Action:** Change `class StopSessionDialog(BaseFormDialog)` to `class StopSessionDialog(BaseButtonDialog)`. Remove comments and code at lines 609-612 that remove `self._form`. Keep the custom stacked layout logic at lines 614-634. Replace `layout.addWidget(self._buttons)` at line 635 with `self.finalize_content()`.
   - **Verification:** Existing `StopSessionDialog` construction test passes. Add a regression test that scans `desktop/ui/tasks/dialogs.py` and asserts the string `removeItem(self._form)` is absent.

7. **Optionally migrate `ConfirmDialog` to the new base if low-risk.**
   - **Location:** `desktop/ui/tasks/dialogs.py:647-660`
   - **Action:** This is optional because `ConfirmDialog` does not misuse `BaseFormDialog`. If touched, make it inherit `BaseButtonDialog` with `buttons=QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No`, add the message label to `contentLayout()`, and call `finalize_content()`. Preserve `accept`/`reject` behavior.
   - **Verification:** Existing `ConfirmDialog` construction tests pass. If not migrated, no action is required.

### Phase 3: QSS and theme color corrections

8. **Remove the parent-card QDialog override and add frameless-specific transparent styling.**
   - **Location:** `desktop/styles/_base.qss:201-204` and `desktop/styles/_base.qss:556-560`
   - **Action:** Delete the `#card QDialog { background-color: {{bg-secondary}}; }` rule at lines 201-204. Keep the `#dialogTitleBar`, `#dialogFrame`, and `#dialogContent` rules at lines 85-127. Add `QDialog#framelessDialog { background: transparent; }` after the generic `QDialog { background-color: {{bg-primary}}; }` rule at lines 556-560 so it wins for frameless dialogs while leaving non-frameless Qt dialogs unchanged.
   - **Verification:** Add a QSS regression test that `_get_template()` does not contain `#card QDialog` and does contain `QDialog#framelessDialog`. Run `tests/widget/test_theme_validation.py`.

9. **Tone down dialog surface tokens with exact replacement values.**
   - **Location:** `grouper_core/colors.py:652-700`
   - **Action:** Replace `_DIALOG_SURFACE_TOKENS` values exactly as follows:

     ```python
     _DIALOG_SURFACE_TOKENS: dict[str, dict[str, str]] = {
         "dark": {
             "dialog-bg": "#2b2d41",
             "dialog-content-bg": "#2b2d41",
             "dialog-title-bg": "#32344c",
             "dialog-border": "#4c5377",
         },
         "light": {
             "dialog-bg": "#fbfbfc",
             "dialog-content-bg": "#efeff2",
             "dialog-title-bg": "#e8e8ed",
             "dialog-border": "#cacacf",
         },
         "black": {
             "dialog-bg": "#0a0a0a",
             "dialog-content-bg": "#0a0a0a",
             "dialog-title-bg": "#1e1e1e",
             "dialog-border": "#2a2a2a",
         },
         "sage": {
             "dialog-bg": "#445646",
             "dialog-content-bg": "#445646",
             "dialog-title-bg": "#4e6050",
             "dialog-border": "#5e7160",
         },
         "cathode": {
             "dialog-bg": "#142114",
             "dialog-content-bg": "#162616",
             "dialog-title-bg": "#1a2e1a",
             "dialog-border": "#295d31",
         },
         "argon": {
             "dialog-bg": "#221838",
             "dialog-content-bg": "#271c3f",
             "dialog-title-bg": "#2c2048",
             "dialog-border": "#4e376d",
         },
         "sodium": {
             "dialog-bg": "#2e2c1f",
             "dialog-content-bg": "#323022",
             "dialog-title-bg": "#363424",
             "dialog-border": "#645846",
         },
         "oxygen": {
             "dialog-bg": "#381a1a",
             "dialog-content-bg": "#401e1e",
             "dialog-title-bg": "#482222",
             "dialog-border": "#713737",
         },
     }
     ```

     These values preserve the elevated dialog palette while moving non-black themes closer to `bg-secondary`/`border` than the current values.
   - **Verification:** Run `tests/widget/test_theme_validation.py` and `tests/widget/test_transparency.py`. Add/adjust tests so every theme still has valid hex dialog tokens and `dialog-title-bg` / `dialog-border` remain distinguishable from `bg-primary`.

### Phase 4: Restore dialog drag behavior

10. **Remove Windows early returns from `DialogTitleBar` drag handlers only.**
    - **Location:** `desktop/ui/shared/title_bar.py:195-219`
    - **Action:** In `DialogTitleBar.mousePressEvent`, `mouseMoveEvent`, and `mouseReleaseEvent`, remove the `if sys.platform == "win32": return` blocks. Keep the existing cross-platform movement logic:
      - Store `_drag_pos` on left-button press using `event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()`.
      - Move `self.window()` during left-button drag.
      - Clear `_drag_pos` on release.
    - Do **not** change the main `TitleBar` class at `desktop/ui/shared/title_bar.py:104-149`; it intentionally delegates Windows dragging/maximize behavior to `desktop/app.py` native events.
    - **Verification:** Add a widget test that shows a `_TestDialog`, finds `dialogTitleBar`, simulates a left-button drag with `QTest`, and asserts the dialog position changes. Run it on the current Windows environment.

### Phase 5: Tests, docs, and completion records

11. **Update base dialog tests for the new transparency contract.**
    - **Location:** `tests/widget/test_dialogs.py:32-72`
    - **Action:** Replace `test_does_not_use_translucent_background_attribute` with a test asserting `dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)` is true and `dialog.autoFillBackground()` is false. Keep the frameless flag, object-name, and drop-shadow tests.
    - **Verification:** `python -m pytest tests/widget/test_dialogs.py -v` passes.

12. **Add structural regression tests for dialog construction.**
    - **Location:** `tests/widget/test_dialogs.py`
    - **Action:** Add tests that:
      - `AddGroupDialog(["Focus"], [])` is a `BaseButtonDialog` and not a `BaseFormDialog`.
      - `StopSessionDialog("Activity")` is a `BaseButtonDialog` and not a `BaseFormDialog`.
      - The source text of `desktop/ui/tasks/dialogs.py` does not contain `removeItem(self._form)`.
      - The tag variant of `AddGroupDialog` created with `title="Add Tag", item_label="tag", limit_hint=None` has the correct title/info text.
    - **Verification:** `python -m pytest tests/widget/test_dialogs.py -v` passes.

13. **Update transparency/parented-dialog tests.**
    - **Location:** `tests/widget/test_transparency.py:177-360`
    - **Action:** Adjust tests to reflect a transparent outer frameless dialog gutter and opaque inner frame/content. Keep `test_dialog_content_is_opaque_on_screen` and `test_dialog_frame_is_opaque_on_screen`. Update parented `AddGroupDialog` tests so they assert:
      - The `dialogFrame` screen pixel matches or closely approximates `_THEME_PALETTE[theme]["dialog-bg"]`.
      - The `dialogTitleBar` screen pixel matches or closely approximates `_THEME_PALETTE[theme]["dialog-title-bg"]`.
      - The outer 16px gutter is not a solid `bg-secondary` band caused by `#card QDialog`; use either a pixel comparison against `bg-secondary` with shadow tolerance or rely on the QSS static test in Step 14 if pixel compositing is unstable.
    - **Verification:** `python -m pytest tests/widget/test_transparency.py -v` passes.

14. **Add QSS regression tests.**
    - **Location:** `tests/widget/test_theme_validation.py:78-90` or a new test class in the same file
    - **Action:** Add a test that reads `_get_template()` and asserts:
      - `"#card QDialog" not in template`
      - `"QDialog#framelessDialog" in template`
      - The template still contains `#dialogFrame` and `#dialogContent` rules.
    - **Verification:** `python -m pytest tests/widget/test_theme_validation.py -v` passes.

15. **Run full quality checks and update status files.**
    - **Location:** repository root
    - **Action:** Run the verification commands listed in the Verification section. After all pass, create or update `STATUS.md` with a short summary of completed dialog changes and test results. Create or update `NOTES.md` with implementation notes including: the reason `#card QDialog` was removed, the new dialog base-class rule (`BaseFormDialog` only for form layouts; `BaseButtonDialog` for stacked/custom content), the exact two user-facing dialogs verified (`EditBoardDialog` and `AddGroupDialog` in group/tag mode), and any manual UI observations.
    - **Verification:** `STATUS.md` and `NOTES.md` exist and mention the completed verification commands and outcomes.
## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Re-enabling `WA_TranslucentBackground` reintroduces black margins on some Windows/GPU/theme combinations. | Medium | High | Keep `dialogFrame`, `dialogTitleBar`, and `dialogContent` opaque/styled; add screen-pixel tests for parented and unparented dialogs; manually verify all target themes. If black margins appear, keep the top-level dialog transparent and fix the compositor/inner-surface styling rather than restoring opaque `#card QDialog`. |
| Qt QSS specificity differs from web CSS expectations and `QDialog#framelessDialog` does not override a generic rule. | Medium | Medium | Place `QDialog#framelessDialog` after the generic `QDialog` block as specified, add a static template test, and verify with widget pixel tests. Do not reintroduce any `#card QDialog` selector. |
| Drag simulation tests are flaky because of platform window-manager behavior. | Medium | Medium | Test movement through `DialogTitleBar` using a shown dialog and generous movement deltas; if screen/window movement is unreliable in CI, add a focused unit-style event test for `_drag_pos` plus keep manual verification documented in `NOTES.md`. |
| Refactoring `BaseFormDialog` to inherit `BaseButtonDialog` changes button ownership/order. | Low | Medium | Preserve `self._buttons` name and `finalize_form()` behavior exactly. Run construction tests for every dialog subclass and manual smoke-test Edit Board and Add Group/Add Tag. |
| Toned-down color tokens are still perceived as too bright or too close to panels. | Medium | Low | Use exact proposed values for deterministic implementation, then rely on manual theme review. Because colors remain centralized in `_DIALOG_SURFACE_TOKENS`, subsequent tuning is a small palette-only change. |
| `AddGroupDialog` tag-mode text/API changes break callers that expect `selected_group`. | Low | Medium | Preserve `selected_group` exactly. Only add optional keyword parameters; do not remove positional arguments. Update `_add_tag()` to use the new keywords and add a dedicated tag-variant test. |
## Verification

Run these checks after implementation, in order:

1. **Targeted lint:**
   - `python -m ruff check desktop/ui/shared/base_dialog.py desktop/ui/shared/title_bar.py desktop/ui/tasks/dialogs.py desktop/ui/time/activity_config.py grouper_core/colors.py tests/widget/test_dialogs.py tests/widget/test_transparency.py tests/widget/test_theme_validation.py`
2. **Targeted widget/theme tests:**
   - `python -m pytest tests/widget/test_dialogs.py -v`
   - `python -m pytest tests/widget/test_transparency.py -v`
   - `python -m pytest tests/widget/test_theme_validation.py -v`
3. **Full test suite:**
   - `python -m pytest`
4. **Manual UI verification across at least `dark`, `light`, `black`, and one colored theme (`argon` or `oxygen`):**
   - Open Task Board → click **Edit Board**. Confirm the dialog uses the toned-down elevated dialog surface, does not show a thick 16px border, and can be click-dragged by its title bar.
   - Open Time Tracker → **Edit Activities** → select an activity → click **+ Add Group**. Confirm it now uses the same dialog chrome/surface treatment as Edit Board, does not show a solid wide `bg-secondary` border, retains its list/input behavior, and can be click-dragged.
   - In the same activity detail editor, click **+ Add Tag**. Confirm the title is `Add Tag`, the prompt says `tag name`, it does not mention the max-three-groups rule, styling matches the group dialog, and it can be click-dragged.
5. **Completion records:**
   - Create or update `STATUS.md` with what changed and which commands/manual checks passed.
   - Create or update `NOTES.md` with the architectural rule for future dialogs, the removed `#card QDialog` cause, any platform-specific drag observations, and any unresolved visual caveats.

Acceptance criteria:

- `EditBoardDialog` and `AddGroupDialog` share the same frameless dialog chrome path and use `dialog-bg`, `dialog-content-bg`, `dialog-title-bg`, and `dialog-border` tokens, independent of parent widget object names.
- `AddGroupDialog` no longer paints the 16px shadow gutter as a solid parent-card-colored band.
- The dialog elevation remains intentional but less bright/desaturated using the exact token values in this plan.
- `DialogTitleBar` supports click-and-drag movement on Windows and non-Windows platforms.
- No dialog in `desktop/ui/tasks/dialogs.py` uses `self.contentLayout().removeItem(self._form)`.
- Tests protect against reintroducing the parent-cascade bug and the form-removal construction pattern.
