"""Tests for the _copy_tree helper in grouper_install/setup.py."""

from __future__ import annotations

from pathlib import Path

import pytest
from grouper_install.setup import _copy_tree


class TestCopyTree:
    def test_copies_directory(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "file1.txt").write_text("hello")
        (src / "file2.txt").write_text("world")

        dst = tmp_path / "dst"
        _copy_tree(src, dst)

        assert (dst / "file1.txt").exists()
        assert (dst / "file2.txt").exists()
        assert (dst / "file1.txt").read_text() == "hello"
        assert (dst / "file2.txt").read_text() == "world"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "data.txt").write_text("new content")

        dst = tmp_path / "dst"
        dst.mkdir()
        (dst / "data.txt").write_text("old content")

        _copy_tree(src, dst)

        assert (dst / "data.txt").read_text() == "new content"

    def test_raises_on_bad_src(self, tmp_path: Path) -> None:
        src = tmp_path / "nonexistent"
        dst = tmp_path / "dst"
        with pytest.raises(FileNotFoundError):
            _copy_tree(src, dst)
