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

- Draft black-theme `AddGroupDialog` fix is in place: dialog translucency remains disabled, black dialog tokens are restored to standard black theme surfaces, and dialog list rows no longer use the rough blocky override from `example-2.png`.
- Known remaining visual issue: borders around the parent card/dialog card area still read black or insufficiently distinct in the live black-theme view. Handle this in a new follow-up session.
- A follow-up session should review the live screenshot and refine card/dialog border contrast without reintroducing top-level translucency or blocky list-item styling.

## Verification Snapshot

- Unit and widget coverage was expanded substantially around installer behavior.
- Prior verification on recent work was clean for `pytest`, `ruff`, and most `ty` checks, with only previously-known type noise noted at the time.
- Recent focused verification was clean for `tests/widget/test_transparency.py`, `test_theme_validation.py`, `test_theme_load.py`, and `test_dialogs.py`.
- Current dialog-focused verification is clean: `uv run pytest tests/widget/test_transparency.py tests/widget/test_theme_validation.py tests/widget/test_theme_load.py tests/widget/test_dialogs.py` and `uv run ruff check .`.
- Full `uv run pytest` reached 99% with printed tests passing but hit the tool timeout; the remaining transparency cases were run separately and passed.
