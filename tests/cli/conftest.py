"""conftest.py — Fixtures for Grouper CLI tests.

Every test gets a fully isolated temp database via the root conftest's
``isolated_db`` fixture (autouse).  No GUI.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def run_cli():
    """Return a helper that calls the CLI main() and captures output.

    Usage:
        result = run_cli("session", "active")
        result = run_cli("--json", "task", "list")
    Returns a SimpleNamespace with .code, .stdout, .stderr
    """
    import io
    import sys
    from types import SimpleNamespace

    from cli.main import main

    def _run(*args: str) -> SimpleNamespace:
        out, err = io.StringIO(), io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, err
        try:
            code = main(list(args))
        except SystemExit as exc:
            code = exc.code if exc.code is not None else 0
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        return SimpleNamespace(
            code=code,
            stdout=out.getvalue(),
            stderr=err.getvalue(),
        )

    return _run
