"""Tests for grouper_sync CLI argument validation."""

from __future__ import annotations

import sys

import pytest


def test_connect_rejects_non_integer_port(monkeypatch, capsys):
    from grouper_sync.__main__ import main

    monkeypatch.setattr(sys, "argv", ["grouper-sync", "connect", "host:notaport"])
    monkeypatch.setattr(
        "grouper_sync.__main__.init_database",
        lambda: None,
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Invalid port" in captured.err


def test_connect_rejects_out_of_range_port(monkeypatch, capsys):
    from grouper_sync.__main__ import main

    monkeypatch.setattr(sys, "argv", ["grouper-sync", "connect", "host:70000"])
    monkeypatch.setattr(
        "grouper_sync.__main__.init_database",
        lambda: None,
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "must be 1-65535" in captured.err
