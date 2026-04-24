# GROUPER STATUS

## Current State

- Core desktop app, CLI, server, and Windows installer are implemented and working.
- Four release variants exist: `core`, `core_cli`, `core_server`, `core_cli_server`.
- Installer supports machine-wide install, elevation, PATH updates, manifest persistence, ARP registration, upgrade detection, and uninstall.
- About page uses GitHub links and GitHub Releases for version checks.
- DRM / activation code has been removed.
- Shared frameless dialogs no longer rely on top-level translucency.
- Dialog surface tokens exist for all themes; `#card`-scoped QSS selectors prevent parent-card transparency bleed-through.
- E2E pywinauto tests have been removed and replaced with fast widget tests.

## Recent High-Value Changes

- Fixed Nuitka entry-point import issues by using absolute imports in app entry points.
- Added robust installer support modules: `dist_meta`, `path_env`, `elevation`, `manifest`, and `registry`.
- Completed uninstall flow including installer self-cleanup handling.
- Improved task-board dragging behavior and covered it with widget tests.
- Reworked dialog contrast coverage to test the real parented dialog context.
- Added dialog surface tokens and dialog-scoped list styling for low-contrast themes.
- Documented the dialog investigation in `.agents/context/qt-pitfalls.md`.
- Removed `WA_TranslucentBackground` from `FramelessDialog`; replaced with `WA_StyledBackground` on container, title bar, and content.
- Consolidated `#card` dialog QSS selectors into base rules to reduce duplication.
- Added warning log when `EditTaskDialog` encounters a prerequisite task with a missing `id`.
- Fixed activity rename not persisting: changed `_ActivityDetailEditor` name input signal from `returnPressed` to `editingFinished` so renames save on focus loss, not just Enter.

## Active Work

- Known remaining visual issue: the black-theme dialog title bar is perceptually too close to the plain page background in the free-floating (non-parented) dialog case. The `test_dialog_chrome_differs_from_plain_page[black]` test currently fails with a delta of ~0.008 vs. the required 0.015. A follow-up session should either lighten the black dialog title bar or darken the black page background to restore perceptual separation.
- Dialog translucency and blocky list-item styling should remain disabled.
- Follow-up: the group rename in `_GroupSection` (line ~281) also uses `returnPressed` and has the same focus-loss persistence bug.

## Verification Snapshot

- Full `uv run pytest` passes (528/529; 1 pre-existing failure from missing `win32com` module in test environment).
- `uv run ruff check .` clean.
- New `tests/widget/test_activity_config.py` covers editingFinished rename persistence with 4 tests.
