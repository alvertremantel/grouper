# Refactor Grouper Server Package

**Date:** 2026-04-27
**Status:** draft

---

## Goal

Refactor the current `grouper_server` implementation into a renamed, more maintainable `server` package while completely removing the Textual TUI. Decouple sync from both the desktop application and the server package by moving it to a separate root-level `grouper_sync` package, so the desktop app imports sync functionality without importing the server package and the server imports only shared core/sync code.

## Understanding

Current relevant structure and coupling:

- `grouper_server/` is the standalone server package and contains:
  - `grouper_server/__main__.py:1-313`: CLI entry point for `serve`, `connect`, `status`, and `web`. It imports `grouper_server.runner` at `:142`, `grouper_server.tui` at `:159-162`, `grouper_server.sync.*` at `:204-206`, and `grouper_server.web` at `:294`.
  - `grouper_server/runner.py:1-152`: lifecycle manager for sync + web; it imports `.sync.server`/`.sync.discovery` via type checking and runtime imports at `:72`, `:103`, and `.web` at `:121`.
  - `grouper_server/sync/*.py`: peer-to-peer sync implementation. These modules already depend on `grouper_core.database.connection` rather than `desktop`, e.g. `sync/runtime.py:11` and `sync/changelog.py:19`.
  - `grouper_server/web/*.py` and `grouper_server/web/templates/*.html`: Flask dashboard. It depends on `grouper_core`, e.g. `web/css.py:11-12`, `web/rendering.py:10-11`, and `web/routes.py:101/138`.
  - `grouper_server/tui/__init__.py:1-8` and `grouper_server/tui/app.py:1-180`: Textual TUI. `__main__.py` conditionally imports it and exposes `--no-tui`.
- The desktop application currently imports the server package directly for sync:
  - `desktop/ui/views/sync_view.py:40-41` type checks `grouper_server.sync.discovery`.
  - `desktop/ui/views/sync_view.py:74-77`, `:107`, `:153-159`, `:685-687`, `:781-783` import `grouper_server.sync.*` at runtime.
  - This violates the requested “main app and server no longer import each other” boundary even though the desktop only uses sync, not web/server lifecycle.
- Packaging/build config references the old package:
  - `pyproject.toml:20-22` defines a `tui` extra with `textual>=0.50`.
  - `pyproject.toml:24-28` includes `textual>=0.50` in `server` extra.
  - `pyproject.toml:43`, `:50`, `:62` include `grouper_server` in package discovery, console script, and Ruff sources.
  - `uv.lock` still contains `textual` dependency records and extras metadata.
  - `scripts/build_grouper_server.bat:47-55` optionally bundles `grouper_server.tui` and `textual`.
  - `scripts/build_grouper_server.bat:68-78` uses `grouper_server/web/templates`, includes `grouper_server.sync` and `grouper_server.web`, and compiles `grouper_server\__main__.py`.
  - `scripts/build_grouper.bat:72` includes `grouper_server.sync` in the desktop build, causing the desktop executable to bundle from the server package.
- Tests reference `grouper_server.sync` heavily:
  - `tests/unit/sync/test_sync.py` imports `grouper_server.sync.*` throughout.
  - `tests/unit/sync/test_sync_runtime.py:63-187` imports and monkeypatches `grouper_server.sync.*`.
  - `tests/unit/sync/test_sync_entrypoint_import.py:3-40` asserts import purity for `grouper_server.sync.__main__`.
  - `tests/integration/sync/test_sync_round_trip.py:11-12`, `:40-42`, `:77-79`, `:117-118` imports `grouper_server.sync.*`; its helper also imports `desktop.database.connection` at `:115-116`, which should be updated to `grouper_core.database.connection` to reinforce sync/core separation.
- Documentation/comments refer to the old package:
  - `desktop/web_server.py:7-8` mentions `grouper_server.web`.
  - `grouper_core/database/migrations/v018_sync_support.py:9` and `:20` mention `grouper_server.sync` in comments.
  - `README.md:21-24` describes release variants but does not appear to describe package internals.
- There are no root-level `STATUS.md` or `NOTES.md` files currently; the implementation should create/update both after verification.

Constraints and decisions:

- Do not leave a compatibility package or shim named `grouper_server`; the package rename requirement means repository code should no longer contain an importable `grouper_server` package.
- Preserve the external executable/console-script name `grouper-server` unless explicitly requested otherwise. The Python package changes from `grouper_server` to `server`; the installed command remains `grouper-server` and points to `server.__main__:main`.
- Move sync to `grouper_sync`, not to `server.sync`, so desktop can import sync without importing `server`. The server can import `grouper_sync` and `grouper_core`; `grouper_sync` must not import `desktop` or `server`.
- Remove Textual completely from source, packaging extras, build scripts, tests, and lock metadata. The `serve` command should always use the existing headless/plain logging path.

## Approach

Use a staged refactor that preserves behavior while changing package boundaries:

1. Extract sync first by moving `grouper_server/sync` to a new root package `grouper_sync` and updating every import from `grouper_server.sync` to `grouper_sync`. This immediately breaks the desktop-to-server dependency while preserving sync behavior.
2. Rename and deepen server package structure by creating `server/cli`, `server/runtime`, and nested web subpackages (`server/web/assets`, `server/web/views`) instead of keeping most server files at package root. The minimal root API should be `server.__main__` delegating to `server.cli.main`, plus public web startup via `server.web.start_web_server`.
3. Remove Textual/TUI as a separate cleanup: delete TUI files, remove CLI flags/branches, remove `textual` dependencies/extras, and remove build script optional TUI logic.
4. Update packaging, build scripts, docs/comments, and tests to the new package names.
5. Verify with import-boundary checks, targeted sync/server tests, lint, and full test suite. Then document completion in `STATUS.md` and `NOTES.md`.

Expected end-state structure:

```text
server/
  __init__.py
  __main__.py                 # delegates to server.cli.main.main
  cli/
    __init__.py
    main.py                   # former grouper_server/__main__.py without TUI
  runtime/
    __init__.py
    runner.py                 # former grouper_server/runner.py
  web/
    __init__.py               # start_web_server public API
    app.py
    routes.py
    assets/
      __init__.py
      css.py                  # former web/css.py
    views/
      __init__.py
      rendering.py            # former web/rendering.py
    templates/
      404.html
      base.html
      dashboard.html
      error.html
      summary.html
      tasks.html

grouper_sync/
  __init__.py
  __main__.py
  bootstrap.py
  changelog.py
  client.py
  device.py
  discovery.py
  protocol.py
  runtime.py
  schema.py
  server.py
  sync_ops.py
```

## Steps

### Phase 1: Extract sync into `grouper_sync`

1. **Move sync package to a root-level package**
   - **Location:** `grouper_server/sync/` -> `grouper_sync/`
   - **Action:** Move all Python files from `grouper_server/sync` into a new root-level `grouper_sync` package, preserving filenames and relative imports. Keep `grouper_sync/__init__.py` and `grouper_sync/__main__.py`.
   - **Verification:** Run `python -c "import grouper_sync, grouper_sync.protocol, grouper_sync.server, grouper_sync.client"` and confirm it exits 0.

2. **Update sync entrypoint strings and import purity tests**
   - **Location:** `grouper_sync/__main__.py:1-24`; `tests/unit/sync/test_sync_entrypoint_import.py:1-47`
   - **Action:** Change docstring from `python -m grouper_server.sync` to `python -m grouper_sync`. Keep `prog="grouper-server"`. Update tests to use `module_name = "grouper_sync.__main__"`, import `from grouper_sync.__main__ import main`, and monkeypatch `grouper_sync.__main__.init_database`.
   - **Verification:** Run `pytest tests/unit/sync/test_sync_entrypoint_import.py`.

3. **Update desktop sync imports to use `grouper_sync`**
   - **Location:** `desktop/ui/views/sync_view.py:40-41`, `:74-77`, `:107`, `:153-159`, `:685-687`, `:781-783`
   - **Action:** Replace every `grouper_server.sync.*` reference with `grouper_sync.*` while preserving lazy imports inside worker methods. Type-checking imports should become `from grouper_sync.discovery import Peer, SyncBrowser`.
   - **Verification:** Run `python -c "import desktop.ui.views.sync_view"` and `pytest tests/widget/test_main_window.py tests/widget/test_sidebar.py`.

4. **Update server-side imports to use `grouper_sync`**
   - **Location:** `grouper_server/__main__.py:204-206`; `grouper_server/runner.py:17-19`, `:72`, `:103`
   - **Action:** Replace `grouper_server.sync.changelog/client/device` with `grouper_sync.changelog/client/device`. Replace relative sync imports in `runner.py` with `grouper_sync.discovery` and `grouper_sync.server`.
   - **Verification:** Before renaming the server package, run `python -c "import grouper_server.__main__; import grouper_server.runner"`.

5. **Update all sync tests to `grouper_sync` and remove desktop database imports from sync integration helpers**
   - **Location:** `tests/unit/sync/test_sync.py`; `tests/unit/sync/test_sync_runtime.py`; `tests/integration/sync/test_sync_round_trip.py:10-129`
   - **Action:** Replace all `grouper_server.sync` imports/monkeypatch paths with `grouper_sync`. In `tests/integration/sync/test_sync_round_trip.py:_init_sync_database`, replace `import desktop.database.connection as conn_mod` and `from desktop.database.connection import register_sqlite_functions` with `import grouper_core.database.connection as conn_mod` and `from grouper_core.database.connection import register_sqlite_functions`. In `_insert_activity`, import `register_sqlite_functions` from `grouper_core.database.connection`.
   - **Verification:** Run `pytest tests/unit/sync tests/integration/sync`.

### Phase 2: Rename `grouper_server` to `server` and deepen its structure

6. **Create the new nested `server` package and move server entry files**
   - **Location:** `grouper_server/__init__.py`, `grouper_server/__main__.py`, `grouper_server/runner.py`
   - **Action:** Create `server/__init__.py`, `server/__main__.py`, `server/cli/__init__.py`, `server/cli/main.py`, `server/runtime/__init__.py`, and `server/runtime/runner.py`. Move the CLI implementation from `grouper_server/__main__.py` to `server/cli/main.py`; make `server/__main__.py` contain only `from server.cli.main import main` and the standard `if __name__ == "__main__": main()`. Move `grouper_server/runner.py` to `server/runtime/runner.py`.
   - **Verification:** Run `python -c "import server, server.__main__, server.cli.main, server.runtime.runner"`.

7. **Remove TUI logic from the server CLI**
   - **Location:** `server/cli/main.py` (moved from `grouper_server/__main__.py:1-313`)
   - **Action:** Update the docstring so `serve` says “Start sync + web servers” without “with TUI if available”. Remove `import sys` only if no longer needed; keep it if still used by address validation. Remove the `--no-tui` argument formerly at `grouper_server/__main__.py:72-76`. Replace `_cmd_serve` formerly at `:141-173` with direct creation of `ServerConfig`/`ServerRunner` from `server.runtime.runner` followed by `_cmd_serve_headless(runner)`; delete the `sys.stdout.isatty()` branch and all imports of `grouper_server.tui`/`ServerTUI`.
   - **Verification:** Run `python -m server --help`, `python -m server serve --help`, and confirm there is no `--no-tui` in the output.

8. **Update server CLI imports after move**
   - **Location:** `server/cli/main.py:141-294` equivalent after move
   - **Action:** Import `ServerConfig` and `ServerRunner` from `server.runtime.runner`. Import sync operations from `grouper_sync.changelog`, `grouper_sync.client`, and `grouper_sync.device`. Import web startup from `server.web` in `_cmd_web`.
   - **Verification:** Run `python -c "from server.cli.main import main; from server.runtime.runner import ServerConfig, ServerRunner"`.

9. **Update runtime runner imports after move**
   - **Location:** `server/runtime/runner.py` (moved from `grouper_server/runner.py:17-152`)
   - **Action:** Change TYPE_CHECKING imports to `from grouper_sync.discovery import SyncAdvertiser` and `from grouper_sync.server import SyncServer`. Change runtime imports in `start_sync()` from `.sync.server` and `.sync.discovery` to `grouper_sync.server` and `grouper_sync.discovery`. Change `start_web()` import from `.web` to `server.web` (or `from server.web import start_web_server`). Keep `grouper_core.database.connection.get_database_path` as-is.
   - **Verification:** Run `python -c "from server.runtime.runner import ServerConfig, ServerRunner; r=ServerRunner(ServerConfig(no_web=True, no_mdns=True)); print(r.status.sync_running)"` and confirm it prints `False`.

10. **Move and nest web modules under `server.web`**
    - **Location:** `grouper_server/web/` -> `server/web/`
    - **Action:** Move `grouper_server/web/__init__.py` to `server/web/__init__.py`, `web/app.py` to `server/web/app.py`, `web/routes.py` to `server/web/routes.py`, templates to `server/web/templates/`. Move `web/css.py` to `server/web/assets/css.py` and `web/rendering.py` to `server/web/views/rendering.py`. Add `server/web/assets/__init__.py` and `server/web/views/__init__.py`.
    - **Verification:** Run `python -c "import server.web, server.web.app, server.web.routes, server.web.assets.css, server.web.views.rendering"`.

11. **Fix web imports for nested modules**
    - **Location:** `server/web/routes.py:8-19`; `server/web/app.py:30`; `server/web/__init__.py:23`
    - **Action:** In `server/web/routes.py`, change `from .css import get_css` to `from .assets.css import get_css` and `from .rendering import ...` to `from .views.rendering import ...`. Keep `from . import routes` in `server/web/app.py` if `routes.py` remains directly under `server/web`. Keep `from .app import create_app` in `server/web/__init__.py`.
    - **Verification:** Run `python -c "from server.web.app import create_app; app=create_app(); print(app.name)"` and confirm no import errors.

12. **Delete the old package directory**
    - **Location:** `grouper_server/`
    - **Action:** After moves and import updates are complete, remove the old `grouper_server` directory entirely, including `grouper_server/tui`, any remaining `grouper_server/web`, and `grouper_server/__pycache__` if present. Do not add a compatibility shim.
    - **Verification:** Run `python -c "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('grouper_server') is None else 1)"` and confirm it exits 0.

### Phase 3: Remove Textual/TUI from packaging and build scripts

13. **Remove Textual dependencies and old package references from `pyproject.toml`**
    - **Location:** `pyproject.toml:20-28`, `:43`, `:50`, `:62`
    - **Action:** Delete the `tui = [...]` optional dependency group. Remove `"textual>=0.50"` from the `server` extra so it contains only `flask>=3.0` and `zeroconf>=0.131`. Change package discovery include from `"grouper_server*"` to `"server*"` and add `"grouper_sync*"`. Change console script `grouper-server = "grouper_server.__main__:main"` to `grouper-server = "server.__main__:main"`. Change Ruff `src` from `"grouper_server"` to `"server"` and add `"grouper_sync"`.
   - **Verification:** Run `python -m pip install -e .` or the repository’s preferred editable install command, then run `python -c "import server, grouper_sync"`.

14. **Refresh lockfile to remove Textual metadata**
   - **Location:** `uv.lock`
   - **Action:** Regenerate the lockfile with the project’s lock command, preferably `uv lock`, so `textual` is no longer listed as a project extra or package dependency. If `uv` is unavailable, manually update only as a last resort and document that in `NOTES.md`.
   - **Verification:** Run a repository search for `textual` and confirm matches are absent except historical notes if intentionally retained.

15. **Update server build script paths and remove optional TUI bundling**
   - **Location:** `scripts/build_grouper_server.bat:47-78`
   - **Action:** Delete the `GROUPER_INCLUDE_TUI` block at `:47-55`. Change `--include-data-dir=grouper_server/web/templates=grouper_server/web/templates` to `--include-data-dir=server/web/templates=server/web/templates`. Replace `--include-package=grouper_server.sync` with `--include-package=grouper_sync`. Replace `--include-package=grouper_server.web` with `--include-package=server.web`. Change the compiled entry file from `grouper_server\__main__.py` to `server\__main__.py`.
   - **Verification:** Run `Select-String -Path scripts/build_grouper_server.bat -Pattern 'grouper_server|textual|GROUPER_INCLUDE_TUI'` and confirm no matches.

16. **Update desktop build script to bundle sync without server**
   - **Location:** `scripts/build_grouper.bat:72`
   - **Action:** Replace `--include-package=grouper_server.sync` with `--include-package=grouper_sync`.
   - **Verification:** Run `Select-String -Path scripts/build_grouper.bat -Pattern 'grouper_server'` and confirm no matches.

### Phase 4: Update references, docs, and tests for the renamed packages

17. **Update all remaining source/documentation references to old server package**
   - **Location:** `desktop/web_server.py:7-8`; `grouper_core/database/migrations/v018_sync_support.py:9`, `:20`; any remaining files found by search
   - **Action:** Change documentation references from `grouper_server.web` to `server.web` and from `grouper_server.sync.schema.SYNCED_TABLES` to `grouper_sync.schema.SYNCED_TABLES`. Search the repository excluding `.venv`, `__pycache__`, and `.agents/plans` for `grouper_server` and update every non-plan match.
   - **Verification:** Run `Get-ChildItem -Recurse -File -Exclude *.pyc -Path . | Where-Object { $_.FullName -notmatch '\\.venv\\|\\.agents\\plans\\|__pycache__' } | Select-String -Pattern 'grouper_server'` and confirm no output.

18. **Update tests for new package names and monkeypatch paths**
   - **Location:** `tests/unit/sync/`, `tests/integration/sync/`, and any other tests found by search
   - **Action:** Replace all `grouper_server.sync` imports with `grouper_sync`. Replace monkeypatch path strings such as `grouper_server.sync.client.apply_changes` with `grouper_sync.client.apply_changes`. Add/adjust tests to assert `importlib.util.find_spec('server') is not None`, `find_spec('grouper_sync') is not None`, and `find_spec('grouper_server') is None` after install.
   - **Verification:** Run `pytest tests/unit/sync tests/integration/sync`.

19. **Add explicit import-boundary regression tests**
   - **Location:** create `tests/unit/test_package_boundaries.py`
   - **Action:** Add tests that parse source files using `ast` and fail if:
     - any file under `server/` imports `desktop` or `grouper_server`;
     - any file under `desktop/` imports `server` or `grouper_server`;
     - any file under `grouper_sync/` imports `desktop`, `server`, or `grouper_server`;
     - any non-plan source/config file imports or references `textual`.
     Allow `desktop` to import `grouper_sync`.
   - **Verification:** Run `pytest tests/unit/test_package_boundaries.py`.

20. **Add/adjust CLI tests for TUI removal and server package rename**
   - **Location:** create or update tests under `tests/unit/server/` (create `tests/unit/server/__init__.py` if needed)
   - **Action:** Add a test that runs the parser/help path via `python -m server serve --help` using `subprocess.run(..., capture_output=True, text=True)` and asserts exit code 0, `--no-tui` absent, `--no-web` present, and `--no-mdns` present. Add a test that imports `server.cli.main` without initializing the database if feasible; if the current CLI intentionally initializes only in `main()`, mirror the existing sync entrypoint import-purity pattern.
   - **Verification:** Run `pytest tests/unit/server`.

21. **Update installer/release metadata only if package paths are referenced**
   - **Location:** `installer/dist_meta.py:52`; `scripts/assemble_release.bat`; `scripts/build_release*.bat`; `README.md:21-24`
   - **Action:** Do not rename release folder `server\` or executable `grouper-server.exe` unless requested; these are distribution artifacts, not Python package names. Only update comments/docs if they mention `grouper_server`. Preserve `grouper-server.exe` behavior.
   - **Verification:** Run `pytest tests/unit/test_dist_meta.py` and search for `grouper_server` again.

### Phase 5: Final verification and documentation

22. **Run format/lint/type checks for changed packages**
   - **Location:** repository root
   - **Action:** Run Ruff on affected packages and tests after updating `pyproject.toml` sources.
   - **Verification:** Run `ruff check server grouper_sync desktop tests` and `ruff format --check server grouper_sync desktop tests` if Ruff is available in the environment.

23. **Run targeted and full test suites**
   - **Location:** repository root
   - **Action:** Run targeted suites first, then the full suite.
   - **Verification:** Run:
     - `pytest tests/unit/sync tests/integration/sync`
     - `pytest tests/unit/server tests/unit/test_package_boundaries.py`
     - `pytest tests/widget/test_main_window.py tests/widget/test_sidebar.py`
     - `pytest`

24. **Run final repository searches for forbidden remnants**
   - **Location:** repository root
   - **Action:** Search source/config/docs excluding `.venv`, `__pycache__`, `.agents/plans`, and lockfile if lock regeneration is intentionally deferred.
   - **Verification:** Confirm no unwanted matches for:
     - `grouper_server`
     - `textual`
     - `--no-tui`
     - `GROUPER_INCLUDE_TUI`
     - `server.sync` imports (sync should be `grouper_sync`, not under `server`)

25. **Update implementation notes and status**
   - **Location:** `STATUS.md`; `NOTES.md`
   - **Action:** Create the files if absent. In `STATUS.md`, record the refactor completion status, verification commands run, and pass/fail results. In `NOTES.md`, record key decisions: `grouper_sync` chosen to decouple desktop from server, no `grouper_server` compatibility shim, TUI/Textual removed, executable remains `grouper-server`.
   - **Verification:** Confirm both files exist and include the verification command results from this refactor.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Import path churn leaves hidden `grouper_server` references | High | High | Add source-search verification and AST boundary tests; run full test suite. |
| Moving sync breaks desktop sync UI | Medium | High | Keep sync API names unchanged inside `grouper_sync`; update `desktop/ui/views/sync_view.py`; run widget/import tests and sync unit/integration tests. |
| Package name `server` is generic and may conflict in some environments | Medium | Medium | Rely on local editable/install package precedence; keep no old shim; add import tests. If conflict appears, document and ask whether a less generic name is acceptable, but current requirement explicitly says rename to `server`. |
| Lockfile regeneration may fail if `uv` is unavailable | Medium | Medium | Try `uv lock`; if unavailable, update dependency metadata carefully and document in `NOTES.md`; verify no `textual` references remain. |
| Removing TUI changes behavior for users expecting terminal dashboard | High | Medium | This is requested behavior; preserve headless logging output and CLI commands; add help-output tests proving `--no-tui` is gone. |
| Build scripts use stale paths after package move | Medium | High | Update Nuitka include paths and entry file; search scripts for old names; run build preflight or script if feasible. |
| Tests currently import `desktop.database` in sync helpers | Medium | Medium | Change sync/integration test helpers to `grouper_core.database` to enforce boundaries. |

## Verification

Overall verification strategy:

1. **Import/package checks**
   - `python -c "import server, server.cli.main, server.runtime.runner, server.web, grouper_sync"`
   - `python -c "import importlib.util; assert importlib.util.find_spec('grouper_server') is None"`
   - `python -m server --help`
   - `python -m server serve --help` and confirm no `--no-tui`.

2. **Boundary checks**
   - Run the new `tests/unit/test_package_boundaries.py` to enforce:
     - `server` does not import `desktop` or `grouper_server`;
     - `desktop` does not import `server` or `grouper_server`;
     - `grouper_sync` does not import `desktop`, `server`, or `grouper_server`;
     - no remaining Textual/TUI imports/references in active source/config.

3. **Behavioral tests**
   - `pytest tests/unit/sync tests/integration/sync`
   - `pytest tests/unit/server tests/unit/test_package_boundaries.py`
   - `pytest tests/widget/test_main_window.py tests/widget/test_sidebar.py`
   - `pytest`

4. **Static checks**
   - `ruff check server grouper_sync desktop tests`
   - `ruff format --check server grouper_sync desktop tests`

5. **Repository searches**
   - Search active source/config/docs for `grouper_server`, `textual`, `--no-tui`, `GROUPER_INCLUDE_TUI`, and unintended `server.sync` references. Exclude `.venv`, `__pycache__`, `.agents/plans`, and any explicitly documented generated artifacts.

6. **Documentation/status**
   - Verify `STATUS.md` and `NOTES.md` exist and summarize completed work, decisions, and actual verification results.
