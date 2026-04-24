# Plan: Practical Test Isolation Hardening (No Multi-DB Feature)

## Goal

Ensure test runs never touch or clutter the developer's real Grouper data/config home directory, while keeping application behavior single-database in production. Do **not** implement user-facing multi-database switching.

## Scope and Constraints

- In scope:
  - Harden pytest isolation so tests use temp paths for both DB and config artifacts.
  - Remove import-time database initialization side effects from sync entrypoint code.
  - Add/adjust tests to lock these guarantees.
- Out of scope:
  - Settings UX for multiple databases.
  - Runtime DB hot-swap support.
  - Data migration between named DB profiles.

## Current State (Observed)

- Root test fixture already isolates DB per test in `tests/conftest.py` by setting `GROUPER_DATA_DIR`, then calling `_init_paths()` + `init_database()`.
- DB path selection already prioritizes env override in `grouper_core/database/connection.py` (`_load_data_directory`).
- Config currently defaults to `Path.home() / ".grouper"` in `grouper_core/config.py` (`APP_DIR`, `CONFIG_FILE`) and can create `config.json` plus data directories when `ConfigManager` is used.
- Legacy sync CLI module initializes DB at import time in `grouper_server/sync/__main__.py` via top-level `init_database()` call.

## Intended End State

- Test runs are fully sandboxed (DB + config artifacts) under pytest temp directories.
- Importing `grouper_server.sync.__main__` has no DB side effects; DB initialization occurs only in `main()` execution flow.
- Regression tests fail if either guarantee is broken.

## Implementation Plan

### Phase 1 - Harden test sandboxing for config/home artifacts

1. Extend root autouse fixture in `tests/conftest.py` to isolate config paths in addition to DB.
   - In the existing `isolated_db` fixture:
     - Create a temp app/config directory sibling to the temp DB directory.
     - Monkeypatch `grouper_core.config.APP_DIR` and `grouper_core.config.CONFIG_FILE` to temp paths.
     - Reset `grouper_core.config.ConfigManager._instance = None` before tests use config.
   - Keep existing DB isolation behavior (`GROUPER_DATA_DIR`, `_init_paths()`, `init_database()`).
   - Ensure fixture returns isolated DB directory as before to avoid downstream fixture breakage.
   - Verification:
     - `uv run pytest tests/unit/test_install_setup.py`
     - `uv run pytest tests/widget/test_settings_view.py` (or nearest existing settings widget test file)

2. Add a focused regression test proving config writes stay inside pytest temp directories.
   - Add a new unit test file (for example `tests/unit/test_test_isolation.py`) with a test that:
     - Calls `get_config()` / `ConfigManager()`.
     - Asserts effective config file location is under `tmp_path` (using monkeypatched constants from root fixture).
     - Asserts user-home `~/.grouper/config.json` is not created as a consequence of this test.
   - Use robust assertions that do not depend on machine-specific user names.
   - Verification:
     - `uv run pytest tests/unit/test_test_isolation.py`

3. Keep local test-specific overrides compatible.
   - Validate files that already monkeypatch config internals (notably `tests/unit/test_install_setup.py`) still work with root fixture layering.
   - If needed, make test-local fixture ordering explicit so local overrides supersede root defaults without cross-test leakage.
   - Verification:
     - `uv run pytest tests/unit/test_install_setup.py`

### Phase 2 - Remove import-time DB side effects from sync entrypoint

4. Refactor `grouper_server/sync/__main__.py` to avoid DB initialization at import time.
   - Remove top-level `init_database()` call.
   - Keep imports at module scope as needed, but perform `init_database()` inside `main()` before command dispatch.
   - Preserve current runtime behavior when launched as CLI (`python -m grouper_server.sync ...`).
   - Verification:
     - `uv run pytest tests/unit/sync/test_sync_runtime.py`

5. Add regression test for import-time purity.
   - Add a new test file under `tests/unit/sync/` (for example `test_sync_entrypoint_import.py`) that:
     - Monkeypatches `grouper_core.database.connection.init_database` to a sentinel/mock.
     - Imports/reloads `grouper_server.sync.__main__`.
     - Asserts sentinel was **not** called on import.
   - Add a companion test that executes `main()` with harmless args and asserts `init_database()` is called exactly once.
   - Use `importlib` + `sys.modules` cleanup to avoid cache false positives.
   - Verification:
     - `uv run pytest tests/unit/sync/test_sync_entrypoint_import.py`

### Phase 3 - Validation, docs context, and completion hygiene

6. Run targeted suite covering DB/config + sync entrypoint areas.
   - Command set:
     - `uv run pytest tests/unit/test_test_isolation.py tests/unit/test_install_setup.py tests/unit/sync/test_sync_entrypoint_import.py tests/unit/sync/test_sync_runtime.py`

7. Run quality gates for changed files.
   - `uv run ruff check .`
   - `uv run ty check`

8. Run a broader confidence pass.
   - `uv run pytest`
   - If full run hits tool timeout, run remaining failed/unfinished buckets explicitly and record results.

9. Update project context docs after successful verification.
   - Update `.agents/context/STATUS.md` with what changed and current verification snapshot.
   - Update `.agents/context/NOTES.md` with durable guidance: tests isolate DB + config, and sync legacy entrypoint has no import-time init side effects.

## Risks and Mitigations

- Risk: Some tests may implicitly rely on persistent config singleton state.
  - Mitigation: Reset `ConfigManager._instance` in root fixture and keep fixture function-scoped.
- Risk: Import/reload tests can become flaky due to module cache interactions.
  - Mitigation: Use deterministic `sys.modules` cleanup and narrow monkeypatch scope.
- Risk: Assertions about user-home filesystem may be brittle on CI.
  - Mitigation: Prefer asserting effective config path is temp-scoped; avoid requiring destructive cleanup of real home files.

## Cost/Benefit Decision

- Benefit: Solves the real pain (test clutter in user environment) with low risk and minimal surface area.
- Cost: Small fixture/test refactor + one entrypoint cleanup.
- Why not multi-DB now: Full multi-DB is a product-level feature with substantial UI/state/sync implications and is unnecessary to solve test isolation.
