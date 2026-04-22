# GROUPER STATUS

## Current State

- Core desktop app, CLI, server, and Windows installer are implemented and working.
- Four release variants exist: `core`, `core_cli`, `core_server`, `core_cli_server`.
- Installer supports machine-wide install, elevation, PATH updates, manifest persistence, ARP registration, upgrade detection, and uninstall.
- About page uses GitHub links and GitHub Releases for version checks.
- DRM / activation code has been removed.
- Shared frameless dialogs no longer rely on top-level translucency.

## Recent High-Value Changes

- Fixed Nuitka entry-point import issues by using absolute imports in app entry points.
- Added robust installer support modules: `dist_meta`, `path_env`, `elevation`, `manifest`, and `registry`.
- Completed uninstall flow including installer self-cleanup handling.
- Improved task-board dragging behavior and covered it with widget tests.
- Reworked dialog contrast coverage to test the real parented dialog context.
- Added dialog surface tokens and dialog-scoped list styling for low-contrast themes.
- Documented the dialog investigation in `.agents/context/qt-pitfalls.md`.

## Active Work

- The black-theme `AddGroupDialog` is technically visible again, but the current result is still visually rough.
- A follow-up session should review the live screenshot and refine dialog width/body composition without reintroducing translucency.

## Verification Snapshot

- Unit and widget coverage was expanded substantially around installer behavior.
- Prior verification on recent work was clean for `pytest`, `ruff`, and most `ty` checks, with only previously-known type noise noted at the time.
- Recent focused verification was clean for `tests/widget/test_transparency.py`, `test_theme_validation.py`, `test_theme_load.py`, and `test_dialogs.py`.
