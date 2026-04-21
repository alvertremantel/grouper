"""Tests for grouper_install/path_env.py."""

from __future__ import annotations

from unittest.mock import patch

from grouper_install.path_env import (
    add_to_machine_path,
    normalize_path_entry,
    remove_from_machine_path,
    split_path,
)


class TestSplitPath:
    def test_splits_semicolons(self) -> None:
        result = split_path("C:\\a;D:\\b;;C:\\c")
        assert result == ["C:\\a", "D:\\b", "C:\\c"]

    def test_empty_string(self) -> None:
        assert split_path("") == []

    def test_strips_whitespace(self) -> None:
        result = split_path("  C:\\a  ; D:\\b ")
        assert result == ["C:\\a", "D:\\b"]


class TestNormalizePathEntry:
    def test_case_insensitive(self) -> None:
        assert normalize_path_entry("C:\\FOO") == normalize_path_entry("c:\\foo")

    def test_trailing_slash(self) -> None:
        assert normalize_path_entry("C:\\Foo\\") == normalize_path_entry("C:\\Foo")


class TestAddToMachinePath:
    def test_appends_when_missing(self) -> None:
        with (
            patch("grouper_install.path_env.get_machine_path", return_value="C:\\Existing"),
            patch("grouper_install.path_env.set_machine_path") as mock_set,
        ):
            result = add_to_machine_path("C:\\New")
            assert result is True
            mock_set.assert_called_once_with("C:\\Existing;C:\\New")

    def test_skips_when_present(self) -> None:
        with (
            patch("grouper_install.path_env.get_machine_path", return_value="C:\\Existing;C:\\New"),
            patch("grouper_install.path_env.set_machine_path") as mock_set,
        ):
            result = add_to_machine_path("c:\\new")
            assert result is False
            mock_set.assert_not_called()

    def test_handles_trailing_backslash_dedup(self) -> None:
        with (
            patch("grouper_install.path_env.get_machine_path", return_value="C:\\Foo"),
            patch("grouper_install.path_env.set_machine_path") as mock_set,
        ):
            result = add_to_machine_path("C:\\Foo\\")
            assert result is False
            mock_set.assert_not_called()


class TestRemoveFromMachinePath:
    def test_removes_entry(self) -> None:
        with (
            patch("grouper_install.path_env.get_machine_path", return_value="C:\\A;C:\\B;C:\\C"),
            patch("grouper_install.path_env.set_machine_path") as mock_set,
        ):
            result = remove_from_machine_path("C:\\B")
            assert result is True
            mock_set.assert_called_once_with("C:\\A;C:\\C")

    def test_noop_when_absent(self) -> None:
        with (
            patch("grouper_install.path_env.get_machine_path", return_value="C:\\A;C:\\B"),
            patch("grouper_install.path_env.set_machine_path") as mock_set,
        ):
            result = remove_from_machine_path("C:\\Z")
            assert result is False
            mock_set.assert_not_called()
