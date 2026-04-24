# Review: Test isolation hardening and sync entrypoint purity

**Date:** Thu Apr 23 2026
**Scope:** `tests/conftest.py`, `grouper_core/config.py`, `grouper_core/database/connection.py`, `tests/unit/test_test_isolation.py`, `grouper_server/sync/__main__.py`
**Test results:** PASS (targeted tests), but identified massive isolation holes when run against edge cases.

---

## Summary

The goal of this commit was to prevent test runs from polluting the developer's real `~/.grouper/` data and config directory. While the change successfully removes the sync entrypoint's import side-effects and attempts to monkeypatch `grouper_core.config`, it misses two massive gaps due to module re-exports and hardcoded duplicated paths. The result is that tests can still overwrite the developer's real `~/.grouper` files. Needs rewrite to truly secure the test sandbox.

## Critical Issues

#### 1. Re-exported Config Paths Bypass Sandbox
- **Location:** `tests/conftest.py:40` interacting with `grouper/config.py:3`
- **Problem:** `grouper/config.py` re-exports `APP_DIR` and `CONFIG_FILE` using `from grouper_core.config import *`. Since module imports resolve before the `isolated_db` test fixture runs, `grouper.config.APP_DIR` copies the original reference (`~/.grouper`). The monkeypatch only updates `grouper_core.config`. Any app code importing `grouper.config.APP_DIR` will still point to the real home directory. Even `test_install_setup.py` explicitly patches `grouper.config.APP_DIR` directly, proving the root fixture is insufficient.
- **Fix:** Either monkeypatch the re-exported constants in `conftest.py` as well, or (much better) remove module-level static constants in favor of getter functions like `get_app_dir()` so they can be securely mocked without `from module import *` cloning the unpatched string references.
  ```python
  # conftest.py
  import grouper.config as _app_cfg
  monkeypatch.setattr(_app_cfg, "APP_DIR", fake_app_dir, raising=False)
  monkeypatch.setattr(_app_cfg, "CONFIG_FILE", fake_config_file, raising=False)
  ```

#### 2. `connection.py` Contains Unpatched Hardcoded Home Paths
- **Location:** `grouper_core/database/connection.py:57`
- **Problem:** `connection.py` duplicates the home directory logic with its own hardcoded `CONFIG_DIR = Path.home() / ".grouper"` and `CONFIG_FILE`. These are not mocked by the `isolated_db` fixture. If any test triggers `set_data_directory()`, it calls `_save_data_directory()`, which blindly overwrites the developer's real `~/.grouper/db_path.txt` with a temporary path. I confirmed this via a custom test script — it breaks the developer's local instance.
- **Fix:** Remove the duplicated hardcoded paths. Have `connection.py` import and use `APP_DIR` from `grouper_core.config`. Since you're already isolating `grouper_core.config.APP_DIR`, this will safely route connection writes to the temp directory too.
  ```python
  from grouper_core.config import APP_DIR
  
  CONFIG_DIR = APP_DIR
  CONFIG_FILE = CONFIG_DIR / "db_path.txt"
  ```

## Suggestions

#### 1. Replace Constant Monkeypatching with Dependency Injection / Getters
- **Location:** `grouper_core/config.py`
- **Problem:** Monkeypatching module-level constants is fundamentally brittle in Python because `from x import y` creates isolated references. It's too easy for a developer to import a constant directly and bypass the sandbox.
- **Fix:** Consider wrapping `APP_DIR` access into a `get_app_dir()` function, or pass the config path explicitly during app initialization so tests can inject temp paths cleanly without relying on `pytest.MonkeyPatch`.

## Test Coverage

- **Existing tests:** `test_test_isolation.py` passes because it only verifies the `_cfg` module (`grouper_core.config`) which was patched, missing the fact that `grouper.config` was unpatched.
- **Missing tests:** A test should exist to verify `set_data_directory()` inside a pytest session writes to the temporary dir, NOT the real home dir. Another test should verify `grouper.config.APP_DIR` points to the temp directory.

## Checklist

- [x] Correctness — reviewed
- [x] Code quality (DRY/YAGNI) — reviewed
- [x] Extensibility — reviewed
- [x] Security — reviewed
- [x] Stability — reviewed
- [x] Resource utilization — reviewed
- [x] Tests — run and reviewed

## Verdict

**NEEDS REWRITE**

The intent of the PR is excellent, but module-level reference copying and duplicated hardcoded config paths entirely bypass the intended sandbox. As currently written, tests can still corrupt the developer's `~/.grouper/config.json` (if imported via `grouper.config`) or `~/.grouper/db_path.txt` (via `connection.py`), defeating the stated goal.
