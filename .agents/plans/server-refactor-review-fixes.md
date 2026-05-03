# Server Refactor Review Fixes (Non-Critical Issues)

**Date:** 2026-04-27
**Status:** draft

---

## Goal

Fix the five non-critical issues identified in the review of the server/sync package refactor (`@.agents/reviews/server-refactor-relative-to-b-111-1.md`): sync entrypoint prog name, port validation parity, null-safe status formatting, stale repo map, and disconnected version string. These are polish/hardening items that do not affect core functionality but prevent misleading output and future regressions.

## Understanding

The branch has completed the `grouper_server` → `server` + `grouper_sync` package split. Active imports are clean, packaging metadata is correct, and 123 targeted tests pass. The review found no critical issues but identified five areas where `grouper_sync/__main__.py` diverges from the hardened `server/cli/main.py` implementation, plus a stale repo map and version string.

### Relevant files and current state

| File | Current state |
|------|--------------|
| `grouper_sync/__main__.py:23` | `prog="grouper-server"` — misleading for standalone sync entrypoint |
| `grouper_sync/__main__.py` `_cmd_connect` (~lines 136-158) | No port validation; calls `int(port_str)` directly inside async path |
| `grouper_sync/__main__.py` `_cmd_status` (~lines 181-199) | `row['device_id'][:8]` and `p['peer_device_id'][:8]` — not null-safe |
| `server/cli/main.py:190-209` | Has correct port validation and null-safe formatting (reference implementation) |
| `tests/unit/sync/test_sync_entrypoint_import.py:43` | `monkeypatch.setattr(sys, "argv", ["grouper-server"])` — should match new prog |
| `.agents/context/MAP.md:8,35` | Still references `grouper_server/` layout that no longer exists |
| `server/__init__.py:9` | `__version__ = "0.1.0"` while project is `1.1.0.24`; nothing reads it |
| `pyproject.toml:3` | `version = "1.1.0.24"` — source of truth |

## Approach

Each fix is a small, isolated edit. They are ordered to minimize interference:
1. Fix the prog name + test first (smallest change, establishes correct identity).
2. Add port validation (mirrors existing server code exactly).
3. Add null-safe formatting (mirrors existing server code exactly).
4. Remove stale `__version__` (trivial deletion).
5. Update the repo map (documentation only).

Steps 1-4 are code changes that need verification. Step 5 is documentation.

## Steps

### Phase 1: Sync CLI identity and hardening

1. **Fix `prog` name in sync entrypoint**
   - **Location:** `grouper_sync/__main__.py:23-25`
   - **Action:** Change `prog="grouper-server"` to `prog="grouper-sync"` and update description to `"Grouper LAN Sync — sync your data between devices"`.
   - **Verification:** `python -m grouper_sync --help` should display `grouper-sync` as the program name.

2. **Update test argv to match new prog name**
   - **Location:** `tests/unit/sync/test_sync_entrypoint_import.py:43`
   - **Action:** Change `monkeypatch.setattr(sys, "argv", ["grouper-server"])` to `monkeypatch.setattr(sys, "argv", ["grouper-sync"])`.
   - **Verification:** Run `python -m pytest tests/unit/sync/test_sync_entrypoint_import.py -v` — both tests pass.

3. **Add port validation to `grouper_sync` connect command**
   - **Location:** `grouper_sync/__main__.py`, function `_cmd_connect`, after the host/port split check (currently line ~138) and before `db_path = get_database_path()` (currently line ~140).
   - **Action:** Insert the same validation block used in `server/cli/main.py:193-209`:
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
     ```
     Then change the later `int(port_str)` in the async call to use the validated `port` variable:
     ```python
     return await sync_with_peer(db_path, host, port)
     ```
   - **Verification:** Run `python -m pytest tests/unit/sync -v` — all existing tests pass.

4. **Add CLI tests for port validation**
   - **Location:** Create or extend `tests/unit/sync/test_sync_entrypoint_import.py` (or a new file `tests/unit/sync/test_sync_cli.py` if preferred)
   - **Action:** Add two tests:
     - `test_connect_rejects_non_integer_port`: Monkeypatch `sys.argv` to `["grouper-sync", "connect", "host:notaport"]`, call `main()`, assert `sys.exit(1)` is raised and stderr contains `"Invalid port"`.
     - `test_connect_rejects_out_of_range_port`: Monkeypatch `sys.argv` to `["grouper-sync", "connect", "host:70000"]`, call `main()`, assert `sys.exit(1)` is raised and stderr contains `"must be 1-65535"`.
   - **Verification:** Run the new tests — both pass.

5. **Apply null-safe device-id formatting to sync status**
   - **Location:** `grouper_sync/__main__.py`, function `_cmd_status`
   - **Action:** Change two formatting lines to match `server/cli/main.py:246-263`:
     - Line with `row['device_id'][:8]` → `(row['device_id'] or '')[:8]`
     - Line with `p['peer_device_id'][:8]` → `(p['peer_device_id'] or '')[:8]`
     - Also change the single-dash separator `f"- last sync:"` to double-dash `f"-- last sync:"` to match server formatting.
   - **Verification:** Run `python -m pytest tests/unit/sync -v` — all pass.

### Phase 2: Cleanup

6. **Remove stale `server.__version__`**
   - **Location:** `server/__init__.py:9`
   - **Action:** Remove the line `__version__ = "0.1.0"`. If any test imports `server.__version__`, update that test. Search first:
     ```bash
     rg "__version__" server/ tests/
     ```
     If nothing references it, simply delete the line.
   - **Verification:** `rg "__version__" server/` returns nothing. Run `python -m pytest tests/unit/server -v` — all pass.

7. **Update repo map to reflect new package layout**
   - **Location:** `.agents/context/MAP.md`
   - **Action:** Replace all references to `grouper_server/`:
     - Line ~8: `grouper_server/: sync server and web dashboard` → `server/: unified server package (sync + web dashboard lifecycle).` Add: `grouper_sync/: LAN peer-to-peer sync protocol and runtime helpers.`
     - Line ~35: `grouper_server/__main__.py: server entry; grouper_server/sync/ contains sync protocol helpers.` → `server/__main__.py: server entry (sync + web); grouper_sync/__main__.py: standalone sync entry.`
   - **Verification:** `rg "grouper_server" .agents/context/MAP.md` returns nothing.

8. **Update STATUS.md context**
   - **Location:** `.agents/context/STATUS.md`
   - **Action:** Add a note under "Recent Changes" documenting these review fixes.
   - **Verification:** File updated.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Port validation changes async call signature | Low | Low | The `port` variable is a local int; no signature change needed. |
| Removing `__version__` breaks an unknown consumer | Low | Low | Pre-search with `rg` before removal; nothing in tests or active code currently reads it. |
| Null-safe formatting hides a real schema bug | Very Low | Low | The `or ''` fallback is defensive only; the schema should still enforce non-null. |

## Verification

1. **Targeted sync tests:** `python -m pytest tests/unit/sync -v` — all pass.
2. **Server tests:** `python -m pytest tests/unit/server -v` — all pass.
3. **Package boundary tests:** `python -m pytest tests/unit/test_package_boundaries.py -v` — all pass.
4. **Lint:** `ruff check server grouper_sync tests/unit/sync tests/unit/server` — clean.
5. **Help smoke test:** `python -m grouper_sync --help` displays `grouper-sync` as prog name.
6. **Map check:** `rg "grouper_server" .agents/context/MAP.md` returns nothing.
7. **Version check:** `rg "__version__" server/` returns nothing.

## Status

done
