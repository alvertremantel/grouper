# Review: server/sync package refactor relative to `b-111-1`

**Date:** 2026-04-27
**Scope:** 55 files changed; server package rename/extraction, `grouper_sync` extraction, packaging/build script updates, package-boundary tests, related docs/context files. Diff size: 1,488 insertions / 557 deletions.
**Test results:** Targeted refactor surface passed: `python -m pytest tests/unit/server tests/unit/test_package_boundaries.py tests/unit/sync tests/integration/sync -v` → 123 passed in 97.13s. Full-suite grouped runs were not completed because they time out in the widget/theme area; do not use the full suite as one command for this branch.

---

## Summary

The package refactor is mostly correct: active source imports are updated, `grouper_server` is removed, `grouper_sync` is package-discovered, and the new boundary tests cover the important architecture constraints. I found no blocking runtime regression in the changed server/sync paths. The remaining issues are cleanup and hardening items that should be addressed, but they do not require a rewrite.

## Critical Issues

None.

## Suggestions

#### 1. Standalone sync entrypoint still identifies itself as `grouper-server`
- **Location:** `grouper_sync/__main__.py:23-25`, `tests/unit/sync/test_sync_entrypoint_import.py:43`
- **Problem:** `python -m grouper_sync --help` prints `grouper-server` as the program name. After extracting sync into a first-class `grouper_sync` package, this is misleading because this entrypoint is sync-only and does not include the web subcommand/options from `server`.
- **Fix:** Give the standalone sync module its own `prog` and update the test argv to match.

```python
# grouper_sync/__main__.py
parser = argparse.ArgumentParser(
    prog="grouper-sync",
    description="Grouper LAN Sync — sync your data between devices",
)

# tests/unit/sync/test_sync_entrypoint_import.py
monkeypatch.setattr(sys, "argv", ["grouper-sync"])
```

#### 2. Port validation is inconsistent between `server` and `grouper_sync`
- **Location:** `grouper_sync/__main__.py:136-158`; compare with `server/cli/main.py:190-209`
- **Problem:** `server connect` validates non-integer and out-of-range ports before starting sync setup, but `python -m grouper_sync connect` calls `int(port_str)` inside the async path. Bad input like `host:notaport` produces an unhandled traceback instead of the clean CLI error used by the server command.
- **Fix:** Mirror the validation used in `server/cli/main.py` before opening the database and enabling CDC.

```python
try:
    port = int(port_str)
except ValueError:
    print(
        f"Invalid port: {port_str!r} in address {args.address!r} (port must be an integer)",
        file=sys.stderr,
    )
    sys.exit(1)

if not (1 <= port <= 65535):
    print(
        f"Invalid port {port} in address {args.address!r} (must be 1-65535)",
        file=sys.stderr,
    )
    sys.exit(1)

# later
return await sync_with_peer(db_path, host, port)
```

#### 3. Sync status formatting should use the same null-safe device-id handling as server status
- **Location:** `grouper_sync/__main__.py:181-199`; compare with `server/cli/main.py:246-263`
- **Problem:** `grouper_sync` slices `row['device_id']` and `p['peer_device_id']` directly. The server status path was hardened to use `(value or '')[:8]`. The schema normally prevents null IDs, but status commands should be defensive and consistent with the server CLI.
- **Fix:** Apply the same null-safe formatting.

```python
print(f"Device ID:  {(row['device_id'] or '')[:8]}...")

print(
    f"  {p['peer_name'] or 'unknown'} ({(p['peer_device_id'] or '')[:8]}...) "
    f"-- last sync: {p['last_sync_at'] or 'never'}, "
    f"hwm: {p['last_changelog_id']}"
)
```

#### 4. Repo map still documents the deleted `grouper_server` layout
- **Location:** `.agents/context/MAP.md:8`, `.agents/context/MAP.md:35`
- **Problem:** The branch updates context/status files but leaves the repo map saying `grouper_server/` still owns sync and web. That is now wrong and will mislead future agents/developers.
- **Fix:** Update the map to name the new packages.

```markdown
- `server/`: unified server package (sync + web dashboard lifecycle).
- `grouper_sync/`: LAN peer-to-peer sync protocol and runtime helpers.

- `server/__main__.py`: server entry; `grouper_sync/` contains sync protocol helpers.
```

#### 5. `server.__version__` is stale and disconnected from project metadata
- **Location:** `server/__init__.py:9`, `pyproject.toml:3`
- **Problem:** `server.__version__` is hard-coded to `0.1.0` while the project version is `1.1.0.24`. Nothing currently reads it, but if it is used later it will report a false version.
- **Fix:** Remove the unused package-local version or derive it from installed metadata.

```python
# simplest: remove __version__ entirely

# or, if a runtime version is needed:
from importlib.metadata import version

__version__ = version("grouper")
```

## Observations

#### 1. Active package references are clean
- **Location:** `server/`, `desktop/`, `grouper_sync/`, `pyproject.toml`
- **Note:** Searches found no active Python imports of `grouper_server`; remaining Python references are boundary tests asserting that the old package is gone.

#### 2. Package discovery and script entrypoint are aligned
- **Location:** `pyproject.toml:38-46`
- **Note:** Setuptools package discovery includes `server*` and `grouper_sync*`, excludes `grouper_server*`, and the installed `grouper-server` script points at `server.__main__:main`.

#### 3. TUI/Textual removal is complete in active source
- **Location:** `pyproject.toml:10-23`, `scripts/build_grouper_server.bat`, `tests/unit/test_package_boundaries.py`
- **Note:** The `tui` extra and `textual` server dependency are removed, the build script no longer has the optional TUI block, and boundary tests enforce no active Textual imports.

## Test Coverage

- **Existing tests:** Targeted server/sync/boundary coverage passed: 123 tests. Full-suite grouped execution was not completed due the known timeout behavior outside this refactor surface.
- **Missing tests:** Add CLI tests for `grouper_sync connect host:notaport` and `grouper_sync connect host:70000` to lock in graceful errors. Add a `python -m grouper_sync --help` assertion if the `prog` name is changed.
- **Weakened tests:** None found. The new package-boundary tests are useful and catch stale imports/monkeypatch paths.

## Checklist

- [x] Correctness — reviewed
- [x] Code quality (DRY/YAGNI) — reviewed
- [x] Extensibility — reviewed
- [x] Security — reviewed
- [x] Stability — reviewed
- [x] Resource utilization — reviewed
- [x] Tests — run and reviewed on targeted refactor surface

## Verdict

**APPROVE**

The branch accomplishes the intended refactor without leaving broken active imports or packaging configuration. Address the sync CLI polish/hardening and stale map documentation soon, but they do not block accepting the server/sync package split.
