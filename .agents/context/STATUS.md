# GROUPER STATUS

## Current State

- Server refactor is complete on this branch: sync lives in `grouper_sync/`, the unified server lives in `server/`. The old `grouper_server/` package no longer exists.
- Textual/TUI has been removed; `grouper-server` is the external command pointing to `server.__main__:main`.
- Desktop package renamed from `grouper/` to `desktop/`; core remains `grouper_core`, CLI remains `cli`.
- `desktop/ui/` is domain-organized into `shared/`, `time/`, `tasks/`, `calendar/`, and `views/`.
- Tests and package metadata use `desktop.*` imports; the installed GUI command is still `grouper` and points at `desktop.main:main`.

## Active Work

- Server refactor review fixes applied; no remaining active work on this branch.
- Do not run monolithic `python -m pytest`; split by test group.

## Recent Changes

- Applied review fixes to `grouper_sync/__main__.py`: renamed prog from `grouper-server` to `grouper-sync`, added port validation (ValueError + range check), and null-safe device-id formatting in status output.
- Added `tests/unit/sync/test_sync_cli.py` with port validation tests (non-integer and out-of-range).
- Fixed test ordering fragility in `test_sync_entrypoint_import.py`: switched from dotted-path monkeypatch to direct module object patching to avoid stale-object issues after `sys.modules` swaps.
- Removed stale `__version__ = "0.1.0"` from `server/__init__.py` (nothing reads it; project version is in `pyproject.toml`).
- Updated `.agents/context/MAP.md` to reflect `server/` + `grouper_sync/` layout.
- Added `tests/unit/test_package_boundaries.py` and `tests/unit/server/test_cli.py` to enforce package boundaries and TUI removal.

## Verification

- Sync tests: `python -m pytest tests/unit/sync -v` → `87 passed` (includes 2 new port validation tests).
- Server tests: `python -m pytest tests/unit/server -v` → `20 passed`.
- Package boundaries: `python -m pytest tests/unit/test_package_boundaries.py -v` → `15 passed`.
- CLI group: `python -m pytest tests/cli` → `104 passed`.
- Core unit group: `python -m pytest tests/unit/core` → `22 passed`.
- DB unit group: `python -m pytest tests/unit/db` → `290 passed`.
- Ruff lint: `ruff check server grouper_sync desktop tests` → clean.
- Refactor format check: `ruff format --check server grouper_sync tests/unit/server tests/unit/test_package_boundaries.py tests/cli/test_parser.py` → clean.
- Smoke test: `python -m grouper_sync --help` displays `grouper-sync` as prog name.
- Widget batches completed except `tests/widget/test_title_bar_unit.py` (Windows access-violation in this environment). Passing batches: batch 1 (`59 passed`), batch 2 (`75 passed`), `test_theme_load.py` (`12 passed`), `test_theme_validation.py` (`11 passed`), `test_transparency.py` (`34 passed`).
