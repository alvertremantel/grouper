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
