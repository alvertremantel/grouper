# Rename CLI and Installer Packages

**Date:** 2026-04-27
**Status:** draft

---

## Goal

Plan the two scoped refactors requested: rename `grouper_cli` to `cli` and rename `grouper_install` to `installer` throughout the repository. The plan must preserve behavior while updating imports, packaging/configuration references, tests, and any documentation or scripts that mention the old names.

## Understanding

The repository currently has top-level Python packages `grouper_cli/` and `grouper_install/` alongside `desktop/`, `grouper_core/`, and `grouper_server/`. The requested refactor is package/module renaming only: `grouper_cli` becomes `cli`, and `grouper_install` becomes `installer`.

Current package references found during inspection:

- Packaging/config: `pyproject.toml:43` includes `grouper_cli*`; `pyproject.toml:49` maps the `grouper-cli` console script to `grouper_cli.main:main`; `pyproject.toml:62` lists `grouper_cli` as a Ruff source root. `grouper_install` is not currently included in setuptools/Ruff source lists.
- CLI source imports: `grouper_cli/__main__.py:1,5`, `grouper_cli/main.py:8`, and every file under `grouper_cli/commands/` imports `grouper_cli.output`.
- Installer source imports: `grouper_install/setup.py:15,45-56` references `grouper_install` in the Nuitka comment and imports support modules from `grouper_install.*`.
- Core docstrings: `grouper_core/formatting.py:3` and `grouper_core/operations.py:3` mention `grouper_cli` in descriptive text.
- Build/release scripts: `scripts/build_grouper_cli.bat:48` compiles `grouper_cli\main.py`; `scripts/build_setup.bat:2,62` references `grouper_install/setup.py`; `scripts/assemble_release.bat:172` and `scripts/build_release.bat:221` copy TOML metadata from `grouper_install\dist\...`.
- Tests import/patch old module paths in `tests/cli/conftest.py:25`, `tests/cli/test_output.py:10`, `tests/cli/test_parser.py:6`, installer unit tests under `tests/unit/test_dist_meta.py`, `test_elevation.py`, `test_install_copy.py`, `test_install_setup.py`, `test_manifest.py`, `test_path_env.py`, `test_registry.py`, `test_uninstall_helpers.py`, and widget tests in `tests/widget/test_setup_dialog.py`.
- Agent context docs mention old package names in `.agents/context/MAP.md:7,9,34,36,37` and `.agents/context/NOTES.md:9,11`.
- Ignored/generated directories exist under both old packages (`__pycache__/`), and ignored release metadata currently exists at `grouper_install/dist/*.toml`. `.gitignore:2-3,11-12` ignores caches and any `dist/` directory.
- Targeted test collection succeeds today with `python -m pytest tests\cli tests\unit\test_dist_meta.py tests\unit\test_elevation.py tests\unit\test_install_copy.py tests\unit\test_install_setup.py tests\unit\test_manifest.py tests\unit\test_path_env.py tests\unit\test_registry.py tests\unit\test_uninstall_helpers.py tests\widget\test_setup_dialog.py --collect-only -q` and collects 198 tests.

Constraints and non-goals:

- Keep user-facing command/executable names unchanged unless the user explicitly asks otherwise: `grouper-cli`, `grouper-cli.exe`, `grouper-server`, `setup.exe`, release component folder `cli\`, and release variant names such as `core_cli` remain as-is.
- Do not add compatibility shim packages named `grouper_cli` or `grouper_install`; the requested end state is a direct rename, and stale imports should fail during tests/search.
- Preserve file history by using rename/move operations for source directories rather than recreate-and-delete where possible.
- Do not commit ignored generated artifacts (`__pycache__/`, `dist/`, build outputs). If local ignored TOML metadata exists, move/copy it only for local build-script continuity; do not force-track it unless separately requested.
- Update `STATUS.md` and `NOTES.md` after verification, as required for completed changes in this repository.

## Approach

Use a mechanical rename with a narrow blast radius:

1. Rename the two top-level package directories (`grouper_cli/` -> `cli/`, `grouper_install/` -> `installer/`) and update every import string, patch target, package discovery setting, and build-script path that refers to the old package names.
2. Keep external product names stable. The package import path changes to `cli.*`, but the installed console command remains `grouper-cli`, the Nuitka output remains `grouper-cli.exe`, and release folders/variants remain `cli`, `core_cli`, and `core_cli_server`.
3. Treat tests as the authoritative safety net: update import and monkeypatch strings first, then run targeted CLI/installer/widget tests before broader lint/type checks.
4. Update repo/agent documentation and root `STATUS.md`/`NOTES.md` so future work does not reintroduce the old package names.

Cost/benefit: this is a low-risk, low-complexity refactor because behavior is unchanged and most edits are search-and-replace. The main cost is churn in tests/build scripts and the increased namespace-collision risk from a generic top-level package name `cli`; mitigate that with import-origin verification and targeted tests.

## Steps

### Phase 1: Rename package directories and source imports

1. **Rename the CLI package directory**
   - **Location:** `grouper_cli/` -> `cli/`
   - **Action:** Move the top-level directory with history-preserving rename semantics (for example, `git mv grouper_cli cli`). If ignored `__pycache__/` files block the move, delete only generated cache files/directories and retry. Do not create a compatibility `grouper_cli/` shim.
   - **Verification:** `Test-Path cli` returns true, `Test-Path grouper_cli` returns false, and `git status --short` shows a rename from `grouper_cli/...` to `cli/...` rather than unrelated delete/add churn where possible.

2. **Rename the installer package directory**
   - **Location:** `grouper_install/` -> `installer/`
   - **Action:** Move the top-level directory with history-preserving rename semantics. If local ignored release metadata exists at `grouper_install/dist/*.toml`, keep it with the renamed tree as `installer/dist/*.toml` for local release-script continuity; do not force-track it because `dist/` is ignored by `.gitignore`.
   - **Verification:** `Test-Path installer` returns true, `Test-Path grouper_install` returns false, `Test-Path installer\dist` matches whether the old local metadata directory existed, and `git status --short` shows tracked installer source files under `installer/`.

3. **Update CLI source imports and package docstrings**
   - **Location:** `cli/__init__.py:2`, `cli/__main__.py:1,5`, `cli/main.py:8`, `cli/commands/activity.py:12`, `cli/commands/board.py:10`, `cli/commands/dashboard.py:13`, `cli/commands/event.py:12`, `cli/commands/project.py:10`, `cli/commands/session.py:11`, `cli/commands/task.py:14`
   - **Action:** Replace package references from `grouper_cli` to `cli`. Examples: `from grouper_cli.main import main` -> `from cli.main import main`; `from grouper_cli.output import ...` -> `from cli.output import ...`; update `__main__.py` docstring to say `python -m cli`. Keep `prog="grouper-cli"` in `cli/main.py:22` unchanged.
   - **Verification:** Run `python -c "from cli.main import build_parser; p = build_parser(); assert p.prog == 'grouper-cli'; print(p.prog)"` from the repository root.

4. **Update installer source imports and package docstrings/comments**
   - **Location:** `installer/setup.py:15,45-56` plus any package docstring in `installer/__init__.py`
   - **Action:** Replace `grouper_install` module references with `installer`. Examples: `from installer.dist_meta import load_dist_toml`, `from installer.elevation import is_elevated, relaunch_elevated`, and update the Nuitka comment path to `installer/setup.py`.
   - **Verification:** Run `python -c "import installer.dist_meta as dm; import installer.elevation as el; assert 'core_cli' in dm.VARIANTS; print('installer imports ok')"` from the repository root.

5. **Update core documentation strings that mention the old CLI module**
   - **Location:** `grouper_core/formatting.py:3`, `grouper_core/operations.py:3`
   - **Action:** Change descriptive text from the old CLI package name to `cli` or to a package-neutral phrase such as "the CLI package".
   - **Verification:** Run a targeted text search for `grouper_cli` in `grouper_core/`; it should return no matches.

### Phase 2: Update configuration and build/release scripts

6. **Update Python project configuration**
   - **Location:** `pyproject.toml:43,49,62`
   - **Action:** Change setuptools package discovery from `grouper_cli*` to `cli*` while preserving the existing distribution scope for other packages. Change `[project.scripts] grouper-cli = "grouper_cli.main:main"` to `"cli.main:main"`. Change Ruff `src` from `grouper_cli` to `cli`; add `installer` to Ruff `src` if the implementer wants installer imports classified as first-party during linting, but do not add `installer*` to setuptools package discovery unless the project owner explicitly wants the installer shipped in the wheel (the previous `grouper_install` package was not included there).
   - **Verification:** Run `python -c "import tomllib, pathlib; data = tomllib.loads(pathlib.Path('pyproject.toml').read_text()); assert data['project']['scripts']['grouper-cli'] == 'cli.main:main'; print(data['project']['scripts']['grouper-cli'])"`.

7. **Update CLI build script input path**
   - **Location:** `scripts/build_grouper_cli.bat:48`
   - **Action:** Change the Nuitka source path from `grouper_cli\main.py` to `cli\main.py`. Keep script name `build_grouper_cli.bat`, output filename `grouper-cli.exe`, and output directory names `grouper-cli.dist`/`grouper-cli.build` unchanged because these are user/release-facing names, not Python package names.
   - **Verification:** Run a text search in `scripts/build_grouper_cli.bat`; it should contain `cli\main.py` and no `grouper_cli` string.

8. **Update installer build script input path**
   - **Location:** `scripts/build_setup.bat:2,62`
   - **Action:** Change comment text and Nuitka source path from `grouper_install/setup.py` and `grouper_install\setup.py` to `installer/setup.py` and `installer\setup.py`. Keep output `setup.exe` unchanged.
   - **Verification:** Run a text search in `scripts/build_setup.bat`; it should contain `installer\setup.py` and no `grouper_install` string.

9. **Update release assembly metadata paths**
   - **Location:** `scripts/assemble_release.bat:172`, `scripts/build_release.bat:221`
   - **Action:** Change metadata copy source paths from `%PROJECT_ROOT%\grouper_install\dist\%VARIANT_NAME%.toml` to `%PROJECT_ROOT%\installer\dist\%VARIANT_NAME%.toml`. Keep variant names (`core`, `core_cli`, `core_server`, `core_cli_server`) and release component folder `cli\` unchanged.
   - **Verification:** Run a text search across `scripts/*.bat`; there should be no `grouper_install` or `grouper_cli` strings. Expected remaining hyphenated product strings like `grouper-cli.exe` are okay.

### Phase 3: Update tests and monkeypatch targets

10. **Update CLI tests**
    - **Location:** `tests/cli/conftest.py:25`, `tests/cli/test_output.py:10`, `tests/cli/test_parser.py:6`
    - **Action:** Replace imports from `grouper_cli.*` with `cli.*`. Keep test directory `tests/cli/` unchanged.
    - **Verification:** Run `python -m pytest tests\cli\test_parser.py tests\cli\test_output.py -q`.

11. **Update installer unit-test imports and patch strings**
    - **Location:** `tests/unit/test_dist_meta.py`, `tests/unit/test_elevation.py:1,8,19,25,31,46,61`, `tests/unit/test_install_copy.py`, `tests/unit/test_install_setup.py`, `tests/unit/test_manifest.py`, `tests/unit/test_path_env.py`, `tests/unit/test_registry.py`, `tests/unit/test_uninstall_helpers.py`
    - **Action:** Replace imports from `grouper_install.*` with `installer.*`. Replace every `unittest.mock.patch(...)` and `pytest.MonkeyPatch.setattr(...)` string target beginning with `grouper_install.` with `installer.`. Update module docstrings/comments to avoid exact old package identifiers.
    - **Verification:** Run `python -m pytest tests\unit\test_dist_meta.py tests\unit\test_elevation.py tests\unit\test_install_copy.py tests\unit\test_install_setup.py tests\unit\test_manifest.py tests\unit\test_path_env.py tests\unit\test_registry.py tests\unit\test_uninstall_helpers.py -q`.

12. **Update installer widget-test monkeypatch targets**
    - **Location:** `tests/widget/test_setup_dialog.py:1,10,33,80-82,121,168-169,192-193,220-224,250-254,280-283,316-318,332-334,350-352,367-369,386-397`
    - **Action:** Replace imports and monkeypatch targets from `grouper_install.setup` with `installer.setup`. Update docstrings/comments to reference `installer/setup.py` or package-neutral wording.
    - **Verification:** Run `python -m pytest tests\widget\test_setup_dialog.py -q`.

### Phase 4: Update repository context and status notes

13. **Update agent context documentation**
    - **Location:** `.agents/context/MAP.md:7,9,34,36,37`; `.agents/context/NOTES.md:9,11`
    - **Action:** Replace package entries with `cli/` and `installer/`; update entry-point notes to `cli/main.py` and `installer/setup.py`. Do not edit historical completed plan files under `.agents/plans/` or review artifacts under `.agents/reviews/` unless separately requested.
    - **Verification:** Search `.agents/context/` for `grouper_cli` and `grouper_install`; both searches should return no matches.

14. **Update root durable project notes after tests pass**
    - **Location:** `STATUS.md` and `NOTES.md`
    - **Action:** After successful verification, add a new completed status section to `STATUS.md` summarizing the package rename and listing the exact verification commands/results. Add a durable note to `NOTES.md` stating that the source packages are now `cli` and `installer` while the user-facing commands remain `grouper-cli` and `setup.exe`; avoid reintroducing the exact old underscore identifiers in these notes if possible.
    - **Verification:** Re-read both files and confirm the new sections are present, dated 2026-04-27 (or the implementation date), and accurately reflect executed verification.

### Phase 5: Final cleanup and exhaustive checks

15. **Remove stale generated caches and old empty directories**
    - **Location:** old directories `grouper_cli/`, `grouper_install/`; generated caches under `cli/__pycache__/`, `cli/commands/__pycache__/`, `installer/__pycache__/`
    - **Action:** Ensure no old package directories remain. Delete generated `__pycache__/` directories that were moved with the source rename; they are ignored artifacts and should not be part of review noise.
    - **Verification:** `Test-Path grouper_cli` and `Test-Path grouper_install` both return false; `git status --short --ignored` shows no tracked old package files.

16. **Run broad stale-reference searches**
    - **Location:** repository-wide, excluding `.git/`, `.venv/`, generated caches, `uv.lock`, `.agents/plans/`, and `.agents/reviews/`
    - **Action:** Search for exact old underscore identifiers `grouper_cli` and `grouper_install`. Fix any remaining non-historical source/config/test/doc references by changing them to `cli` or `installer` as appropriate. Do not change expected hyphenated product strings (`grouper-cli`, `grouper-cli.exe`) unless they are part of an old module import/path.
    - **Verification:** The filtered search returns no actionable references. If unavoidable historical mentions remain in `STATUS.md`/`NOTES.md`, document why they are historical and not import/config paths.

17. **Run final targeted and broad verification**
    - **Location:** full repository
    - **Action:** Execute the verification suite listed in the `Verification` section below. Fix any import, patch-target, lint, or build-path failures and rerun the failing command(s).
    - **Verification:** All listed commands pass, and `git diff --check` reports no whitespace/errors.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| The generic package name `cli` collides with an installed third-party module named `cli`. | Medium | Medium | Verify imports from repository root with `python -c "import cli, pathlib; print(cli.__file__)"`; keep tests running from repo root; rely on package discovery mapping `grouper-cli = "cli.main:main"` for installed execution. |
| Test monkeypatch strings still point at `grouper_install.*`, causing runtime patch failures. | Medium | High | Update all string targets found by search, then run installer unit and widget tests that exercise those patches. |
| Build scripts compile/copy from stale source paths. | Medium | High for release builds | Update `scripts/build_grouper_cli.bat`, `scripts/build_setup.bat`, `scripts/assemble_release.bat`, and `scripts/build_release.bat`; verify with text search and, if Nuitka is available, optional build-script smoke tests. |
| Ignored `grouper_install/dist/*.toml` metadata is lost during rename. | Low/Medium | Medium for local release assembly | If the local ignored directory exists, move it to `installer/dist/`; do not force-track it unless the project owner requests a separate release-metadata tracking change. |
| Historical `.agents/plans/` or `.agents/reviews/` files keep old identifiers and confuse verification search. | High | Low | Exclude historical plan/review artifacts from final stale-reference searches; update active context docs only. |
| Adding `installer*` to setuptools package discovery changes wheel contents unexpectedly. | Low | Medium | Preserve current distribution scope unless owner explicitly requests shipping the installer package; only replace existing `grouper_cli*` with `cli*`. |

## Verification

Run these checks after implementation, in this order:

1. **Import-origin smoke checks**
   - `python -c "import cli, installer, pathlib; print(cli.__file__); print(installer.__file__); assert pathlib.Path(cli.__file__).parts[-2] == 'cli'; assert pathlib.Path(installer.__file__).parts[-2] == 'installer'"`
   - `python -c "from cli.main import build_parser; assert build_parser().prog == 'grouper-cli'"`
   - `python -c "import installer.dist_meta as dm; assert 'core_cli' in dm.VARIANTS"`

2. **Targeted tests**
   - `python -m pytest tests\cli -q`
   - `python -m pytest tests\unit\test_dist_meta.py tests\unit\test_elevation.py tests\unit\test_install_copy.py tests\unit\test_install_setup.py tests\unit\test_manifest.py tests\unit\test_path_env.py tests\unit\test_registry.py tests\unit\test_uninstall_helpers.py -q`
   - `python -m pytest tests\widget\test_setup_dialog.py -q`

3. **Lint/import ordering**
   - `python -m ruff check cli installer grouper_core tests\cli tests\unit\test_dist_meta.py tests\unit\test_elevation.py tests\unit\test_install_copy.py tests\unit\test_install_setup.py tests\unit\test_manifest.py tests\unit\test_path_env.py tests\unit\test_registry.py tests\unit\test_uninstall_helpers.py tests\widget\test_setup_dialog.py`

4. **Stale-reference search**
   - PowerShell command:
     ```powershell
     Get-ChildItem -Recurse -File |
       Where-Object { $_.FullName -notmatch '\\.git|\\.venv|__pycache__|\\.agents\\plans|\\.agents\\reviews|uv\\.lock' } |
       Select-String -Pattern 'grouper_cli','grouper_install'
     ```
   - Expected result: no actionable matches. If `STATUS.md` or `NOTES.md` intentionally contains historical wording, confirm those lines are not import/config/build paths.

5. **Build-script path sanity checks**
   - Search `scripts\*.bat` for `grouper_cli` and `grouper_install`; expected: no matches.
   - Confirm expected retained names still exist where appropriate: `grouper-cli`, `grouper-cli.exe`, `grouper-cli.dist`, and release folder `cli\`.

6. **Full project regression (recommended)**
   - `python -m pytest -q`
   - If full widget coverage is slow or environment-dependent, at minimum report any skipped/failed environment-dependent widget tests separately and include the targeted passing results above.

7. **Git hygiene**
   - `git diff --check`
   - `git status --short --ignored` to confirm no old tracked package files remain and only expected ignored generated artifacts are present.

Completion criteria: package imports use `cli.*` and `installer.*`; external command/executable names remain unchanged; targeted tests and lint pass; `STATUS.md` and `NOTES.md` document the verified refactor; no stale actionable references to the old underscore package identifiers remain outside historical plan/review artifacts.
