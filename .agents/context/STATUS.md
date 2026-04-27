# GROUPER STATUS

## Current State

- Server refactor is underway on this branch: sync has moved from `grouper_server.sync` to root package `grouper_sync`, and the standalone server package has moved from `grouper_server` to `server`.
- Textual/TUI has been removed; `grouper-server` remains the external command name and now points to `server.__main__:main`.
- Do not recreate root-level `STATUS.md` or `NOTES.md`; keep session context in `.agents/context/`.
- Desktop package has been renamed from `grouper/` to `desktop/`; core remains `grouper_core`, CLI remains `cli`, and server is now `server` plus `grouper_sync`.
- `desktop/ui/` is now domain-organized into `shared/`, `time/`, `tasks/`, `calendar/`, and `views/`.
- Shared Qt foundations now live in `desktop/ui/shared/base_card.py` and `desktop/ui/shared/base_dialog.py`.
- Tests and package metadata use `desktop.*` imports; the installed GUI command is still `grouper` and points at `desktop.main:main`.
- Context plans include `.agents/plans/refactor-grouper-server-package.md` for the active server/sync refactor and `.agents/plans/refactor-grouper-desktop-maintainability.md` for the earlier desktop refactor.

## Recent Changes

- Added `tests/unit/test_package_boundaries.py` and `tests/unit/server/test_cli.py` to enforce package boundaries and TUI removal.
- Regenerated `uv.lock` after removing Textual metadata.
- Updated build scripts and package metadata to use `server`, `server.web`, and `grouper_sync` paths.
- Added `BaseCard` for card object names, standard row layout helpers, `WA_StyledBackground`, and drag child passthrough.
- Moved `FramelessDialog` to `shared/base_dialog.py`, added `BaseFormDialog`, centralized dialog background/styled-surface handling, and retained re-export compatibility from `desktop.ui.tasks.dialogs`.
- Added generic QSS error-state styling and `QLabel#errorLabel` styling.
- Added launch compatibility for `python -m desktop`, `python desktop/__main__.py`, `python desktop/main.py`, and the installed `grouper.exe` GUI wrapper.
- Suppressed expected PySide disconnect warnings in the shared `reconnect()` helper.

## Active Work

- Server package refactor implementation is complete; verification is being run in separate groups.
- Do not run monolithic `python -m pytest`; split by test group.

## Verification

- Server/sync targeted: `python -m pytest tests/unit/sync tests/integration/sync tests/unit/server tests/unit/test_package_boundaries.py` → `123 passed`.
- CLI group: `python -m pytest tests/cli` → `104 passed`.
- Core unit group: `python -m pytest tests/unit/core` → `22 passed`.
- DB unit group: `python -m pytest tests/unit/db` → `290 passed`.
- Root-level unit utility group: `python -m pytest tests/unit/test_dist_meta.py tests/unit/test_elevation.py tests/unit/test_install_copy.py tests/unit/test_install_setup.py tests/unit/test_manifest.py tests/unit/test_path_env.py tests/unit/test_registry.py tests/unit/test_test_isolation.py tests/unit/test_uninstall_helpers.py` → `78 passed`.
- Widget batches completed except `tests/widget/test_title_bar_unit.py`, which exits with Windows access-violation code `-1073740791` in this environment before reporting results. Passing widget batches: batch 1 (`59 passed`), batch 2 (`75 passed`), `test_theme_load.py` (`12 passed`), `test_theme_validation.py` (`11 passed`), `test_transparency.py` (`34 passed`).
- Ruff lint: `ruff check server grouper_sync desktop tests` → clean.
- Refactor format check: `ruff format --check server grouper_sync tests/unit/server tests/unit/test_package_boundaries.py tests/cli/test_parser.py` → clean. Full format check still reports pre-existing formatting diffs in unrelated desktop/widget/unit files.
- Historical full suite before this server refactor: `python -m pytest tests/ -q --tb=short` → `799 passed`; do not use this as current verification.
- Historical lint before this server refactor: `ruff check desktop tests` → clean.
- Launch smoke checks stayed alive for 8s under offscreen Qt: `python -m desktop`, `python desktop\__main__.py`, `python desktop\main.py`, installed `grouper.exe`.
- Entry point metadata resolves `grouper` GUI script to `desktop.main:main`.
