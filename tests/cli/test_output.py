"""test_output.py — Unit tests for output formatting helpers."""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timedelta

from grouper_cli.output import print_error, print_json, print_kv, print_table


def _capture(fn, *args, **kwargs) -> str:
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        fn(*args, **kwargs)
    finally:
        sys.stdout = old
    return buf.getvalue()


def _capture_err(fn, *args, **kwargs) -> str:
    buf = io.StringIO()
    old = sys.stderr
    sys.stderr = buf
    try:
        fn(*args, **kwargs)
    finally:
        sys.stderr = old
    return buf.getvalue()


class TestPrintJson:
    def test_simple_dict(self):
        out = _capture(print_json, {"a": 1, "b": "hello"})
        parsed = json.loads(out)
        assert parsed == {"a": 1, "b": "hello"}

    def test_list(self):
        out = _capture(print_json, [1, 2, 3])
        assert json.loads(out) == [1, 2, 3]

    def test_datetime_serialization(self):
        dt = datetime(2026, 3, 25, 10, 30, 0)
        out = _capture(print_json, {"ts": dt})
        parsed = json.loads(out)
        assert parsed["ts"] == "2026-03-25T10:30:00"

    def test_timedelta_serialization(self):
        td = timedelta(hours=2, minutes=30)
        out = _capture(print_json, {"dur": td})
        parsed = json.loads(out)
        assert parsed["dur"] == 9000  # 2.5 hours in seconds

    def test_empty_dict(self):
        out = _capture(print_json, {})
        assert json.loads(out) == {}


class TestPrintTable:
    def test_empty_rows(self):
        out = _capture(print_table, [], ["a", "b"])
        assert "(no results)" in out

    def test_single_row(self):
        out = _capture(print_table, [{"name": "Alice", "age": "30"}], ["name", "age"])
        lines = out.strip().split("\n")
        assert len(lines) == 3  # header, separator, row
        assert "NAME" in lines[0]
        assert "AGE" in lines[0]
        assert "Alice" in lines[2]
        assert "30" in lines[2]

    def test_custom_headers(self):
        out = _capture(print_table, [{"x": "1"}], ["x"], headers=["Value"])
        assert "Value" in out
        assert "X" not in out

    def test_column_width_adapts(self):
        rows = [{"name": "A"}, {"name": "LongName"}]
        out = _capture(print_table, rows, ["name"])
        lines = out.strip().split("\n")
        # Separator should be at least as wide as "LongName"
        assert len(lines[1].strip()) >= 8

    def test_missing_keys_show_empty(self):
        out = _capture(print_table, [{"a": "1"}], ["a", "b"])
        lines = out.strip().split("\n")
        assert "1" in lines[2]


class TestPrintKv:
    def test_basic_pairs(self):
        out = _capture(print_kv, [("Name", "Alice"), ("Age", "30")])
        assert "Name: Alice" in out
        assert "Age: 30" in out

    def test_empty_pairs(self):
        out = _capture(print_kv, [])
        assert out == ""

    def test_alignment(self):
        out = _capture(print_kv, [("Short", "1"), ("Long Key", "2")])
        lines = [ln for ln in out.split("\n") if ln]
        # Both colons should be at the same column
        colon_pos = [line.index(":") for line in lines]
        assert colon_pos[0] == colon_pos[1]


class TestPrintError:
    def test_goes_to_stderr(self):
        out = _capture_err(print_error, "something broke")
        assert "error: something broke" in out
