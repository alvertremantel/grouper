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
- Fixed stale trend-bar colors on theme switch by re-running `MiniBarTrend.update_data` on `QEvent.PaletteChange`.
- Hardened test sandboxing: root autouse fixture isolates DB paths, `grouper_core.config`, re-exported `grouper.config` paths, and `ConfigManager._instance` so tests never write config artifacts to `~/.grouper/`.
- Routed database `db_path.txt` persistence through `grouper_core.config.APP_DIR` instead of duplicated hardcoded home paths.
- Removed import-time `init_database()` side effect from `grouper_server/sync/__main__.py`; DB init now happens only inside `main()`.
- Added regression tests for test isolation (`tests/unit/test_test_isolation.py`) and sync entrypoint import purity (`tests/unit/sync/test_sync_entrypoint_import.py`).

## Active Work

- Known remaining visual issue: the black-theme dialog title bar is perceptually too close to the plain page background in the free-floating (non-parented) dialog case. The `test_dialog_chrome_differs_from_plain_page[black]` test previously failed but now passes after earlier dialog token adjustments.
- Dialog translucency and blocky list-item styling should remain disabled.

## Verification Snapshot

- Unit and widget coverage was expanded substantially around installer behavior.
- Prior verification on recent work was clean for `pytest`, `ruff`, and most `ty` checks, with only previously-known type noise noted at the time.
- Recent focused verification is clean: `uv run pytest tests/widget/test_transparency.py tests/widget/test_theme_validation.py tests/widget/test_theme_load.py tests/widget/test_dialogs.py` and `uv run ruff check .`.
- Full `uv run pytest` reached 99% with printed tests passing but hit the tool timeout; the remaining transparency cases were run separately and passed.
- Test isolation hardening verified clean: `uv run pytest tests/unit/test_test_isolation.py tests/unit/sync/test_sync_entrypoint_import.py tests/unit/sync/test_sync_runtime.py` passes. `uv run ruff check tests/conftest.py tests/unit/test_test_isolation.py grouper_core/database/connection.py` passes. Pre-existing `ty` type noise is unrelated to these changes.
