"""Regression tests for sync entrypoint import purity.

Verify that importing grouper_sync.__main__ has no DB side effects,
and that main() calls init_database() exactly once when executed.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import patch


def test_import_does_not_call_init_database():
    sentinel = []
    module_name = "grouper_sync.__main__"

    saved = sys.modules.pop(module_name, None)

    def _mock_init(*args, **kwargs):
        sentinel.append(1)

    with patch("grouper_core.database.connection.init_database", side_effect=_mock_init):
        try:
            importlib.import_module(module_name)
        finally:
            if saved is not None:
                sys.modules[module_name] = saved
            else:
                sys.modules.pop(module_name, None)

    assert sentinel == []


def test_main_calls_init_database_once(monkeypatch):
    import grouper_sync.__main__ as mod

    calls: list[object] = []
    # Patch the module object directly (not via dotted-path string) so the
    # patch always targets whatever module object is currently in
    # sys.modules — the preceding test swaps sys.modules entries which can
    # leave the dotted-path resolver pointing at a stale object.
    monkeypatch.setattr(mod, "init_database", lambda: calls.append(None))
    monkeypatch.setattr(sys, "argv", ["grouper-sync"])

    mod.main()

    assert len(calls) == 1
