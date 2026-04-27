# Status

## Standardize Frameless Dialog Styling and Drag Behavior

**Date:** 2026-04-26
**Status:** completed

---

### Summary

Refactored shared dialog infrastructure so every frameless dialog uses the same chrome, surface colors, and drag behavior regardless of parent widget.

### Changes

1. **Shared dialog base classes**
   - `FramelessDialog` now sets `WA_TranslucentBackground` and `autoFillBackground(False)` with object name `framelessDialog`, making the 16 px shadow gutter transparent instead of painting it as a solid border.
   - Added `BaseButtonDialog` for dialogs that need stacked content plus a standard button box without `QFormLayout`.
   - `BaseFormDialog` now inherits from `BaseButtonDialog`; button ownership and `finalize_form()` behavior are preserved.

2. **Dialog subclass restructuring**
   - `AddGroupDialog` migrated from `BaseFormDialog` to `BaseButtonDialog`; removed the `removeItem(self._form)` anti-pattern. Added keyword-only params `title`, `item_label`, and `limit_hint` for tag reuse.
   - `StopSessionDialog` migrated from `BaseFormDialog` to `BaseButtonDialog`; same form-removal pattern eliminated.
   - `ConfirmDialog` migrated from `FramelessDialog` to `BaseButtonDialog` for consistency.
   - `_add_tag()` in `activity_config.py` now uses the new constructor keywords instead of `setWindowTitle("Add Tag")` post-hoc.

3. **QSS and theme color corrections**
   - Removed `#card QDialog { background-color: {{bg-secondary}}; }` from `_base.qss`.
   - Added `QDialog#framelessDialog { background: transparent; }` after the generic `QDialog` rule.
   - Updated `_DIALOG_SURFACE_TOKENS` in `grouper_core/colors.py` with toned-down values that keep dialogs elevated but less aggressively bright/desaturated.

4. **Restore dialog drag behavior**
   - Removed Windows-only early returns from `DialogTitleBar.mousePressEvent`, `mouseMoveEvent`, and `mouseReleaseEvent`. Frameless dialogs can now be click-dragged on Windows.

### Verification

- **Lint:** `python -m ruff check desktop/ui/shared/base_dialog.py desktop/ui/shared/title_bar.py desktop/ui/tasks/dialogs.py desktop/ui/time/activity_config.py grouper_core/colors.py tests/widget/test_dialogs.py tests/widget/test_transparency.py tests/widget/test_theme_validation.py` — passed.
- **Targeted widget tests:**
  - `python -m pytest tests/widget/test_dialogs.py -v` — 23 passed.
  - `python -m pytest tests/widget/test_transparency.py -v` — 34 passed.
  - `python -m pytest tests/widget/test_theme_validation.py -v` — 11 passed.
- **Manual UI verification:** performed on `dark`, `light`, `black`, and `oxygen` themes.
  - Task Board → Edit Board dialog renders correctly, no thick border, draggable.
  - Time Tracker → Edit Activities → Add Group renders correctly, no solid `bg-secondary` band, draggable.
  - Time Tracker → Edit Activities → Add Tag shows correct title and prompt, draggable.
