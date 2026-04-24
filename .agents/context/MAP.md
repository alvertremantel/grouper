# Repo Map

## Top Level

- `grouper_core/`: shared models, config, and database logic
- `grouper/`: desktop GUI
- `grouper_cli/`: CLI entrypoints and commands
- `grouper_server/`: sync server and web dashboard
- `grouper_install/`: Windows installer and release-bundle metadata
- `tests/`: unit, widget, CLI, integration, and e2e coverage
- `scripts/`: build and release batch scripts
- `userdocs/`: user-facing docs

## Key Entry Points

- `grouper/main.py`: desktop startup
- `grouper/app.py`: main window
- `grouper_cli/__main__.py`: CLI entry
- `grouper_server/__main__.py`: server entry
- `grouper_install/setup.py`: installer UI and install/uninstall flow
- `grouper/ui/dialogs.py`: shared frameless dialogs and dialog base behavior
- `grouper/ui/activity_config.py`: activity editor flow that launches `AddGroupDialog`

## Installer Modules

- `grouper_install/dist_meta.py`: parse and validate `dist.toml`
- `grouper_install/path_env.py`: machine PATH updates
- `grouper_install/elevation.py`: UAC helpers
- `grouper_install/manifest.py`: install manifest persistence
- `grouper_install/registry.py`: ARP uninstall registration

## Test Buckets

- `tests/unit/`: fast logic tests
- `tests/widget/`: Qt widget tests
- `tests/cli/`: CLI tests
- `tests/integration/`: cross-module tests
- `tests/e2e/`: full Windows flows

## Dialog / Theme Hotspots

- `grouper/styles/_base.qss`: shared widget and dialog QSS
- `grouper_core/colors.py`: theme palettes and dialog surface tokens
- `tests/widget/test_transparency.py`: dialog contrast regressions, including parented dialog checks
- `tests/widget/test_theme_validation.py`: token coverage for dialog surface palette entries
- `.agents/context/qt-pitfalls.md`: lessons learned from the dialog contrast investigation
