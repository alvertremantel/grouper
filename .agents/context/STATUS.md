# GROUPER STATUS

## Current State

- App, CLI, server, and Windows installer all working. Four release variants: `core`, `core_cli`, `core_server`, `core_cli_server`.
- Installer: machine-wide install, elevation, PATH, manifest, ARP, upgrade detection, uninstall.
- Dialogs: no top-level translucency, `WA_StyledBackground` on container/title/content, dialog surface tokens per theme, `#card`-scoped QSS prevents bleed-through. See `.agents/context/qt-pitfalls.md`.
- Tests: widget tests (no pywinauto). Root autouse fixture sandboxes DB + config paths; no test writes to `~/.grouper/`. DB init only inside `main()`, not at import time.

## Recent Changes

- **Summary bars**: recompute `MiniBarTrend` colors on `QEvent.PaletteChange` for theme switches.
- **Activity renames**: `editingFinished` signal (not `returnPressed`) for both `_ActivityDetailEditor` and `_GroupSection`; empty renames revert UI. Covered by `test_activity_config.py`.
- **Test isolation**: conftest patches `grouper_core.config`, re-exported `grouper.config`, and `ConfigManager._instance` **before** calling `_init_paths()` so `_save_data_directory()` always writes to the temp dir. `db_path.txt` routed through `APP_DIR`. Regression tests in `test_test_isolation.py` and `test_sync_entrypoint_import.py`.
- **Dialog QSS**: consolidated `#card` selectors into base rules; `EditTaskDialog` warns on missing prereq `id`.
- **Installer**: `dist_meta`, `path_env`, `elevation`, `manifest`, `registry` modules; full uninstall with self-cleanup.

## Active Work

- Black-theme dialog title bar still perceptually close to page background in non-parented case; regression test now passes.
- Dialog translucency and blocky list-item styling must remain disabled.

## Verification

- `ruff check .` clean. `pytest` 530/531 (1 pre-existing `win32com` import failure). Pre-existing `ty` noise unrelated to recent changes.
