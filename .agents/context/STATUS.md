# GROUPER STATUS

## Current State

- App, CLI, server, and Windows installer all working. Four release variants: `core`, `core_cli`, `core_server`, `core_cli_server`.
- Installer: machine-wide install, elevation, PATH, manifest, ARP, upgrade detection, uninstall.
- Dialogs: no top-level translucency, `WA_StyledBackground` on container/title/content, dialog surface tokens per theme, `#card`-scoped QSS prevents bleed-through. See `.agents/context/qt-pitfalls.md`.
- Tests: widget tests (no pywinauto). Root autouse fixture sandboxes DB + config paths; no test writes to `~/.grouper/`. DB init only inside `main()`, not at import time.

## Recent Changes

- **Summary bars**: recompute `MiniBarTrend` colors on `QEvent.PaletteChange`; zero-value trend bars now blend from active `bg-secondary` instead of a nonexistent `card_bg` fallback, covering DARK to SAGE switches with mixed zero/nonzero days.
- **Black dialogs**: black-theme dialog title bar now uses the existing tertiary black surface so non-parented dialog chrome remains perceptibly distinct from the page while body/content stay on standard black surfaces.
- **Activity renames**: `editingFinished` signal (not `returnPressed`) for both `_ActivityDetailEditor` and `_GroupSection`; empty renames revert UI. Covered by `test_activity_config.py`.
- **Test isolation**: conftest patches `grouper_core.config`, re-exported `grouper.config`, and `ConfigManager._instance` **before** calling `_init_paths()` so `_save_data_directory()` always writes to the temp dir. `db_path.txt` routed through `APP_DIR`. Regression tests in `test_test_isolation.py` and `test_sync_entrypoint_import.py`.
- **Dialog QSS**: consolidated `#card` selectors into base rules; `EditTaskDialog` warns on missing prereq `id`.
- **Installer**: `dist_meta`, `path_env`, `elevation`, `manifest`, `registry` modules; full uninstall with self-cleanup.

## Active Work

- Dialog translucency and blocky list-item styling must remain disabled.

## Verification

- `ruff check .` clean. Split pytest chunks pass: CLI, integration, unit core/db/sync/top-level, and widget groups. `ty check .` still reports pre-existing broad test/model nullability and Qt-stub diagnostics unrelated to the Summary/theme changes.
