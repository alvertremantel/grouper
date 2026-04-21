"""Tests for grouper_install/dist_meta.py."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from grouper_install.dist_meta import (
    VARIANTS,
    default_destinations,
    load_dist_toml,
    validate_source_bundle,
)


class TestLoadDistToml:
    def test_loads_valid_variant(self, tmp_path: Path) -> None:
        (tmp_path / "dist.toml").write_text('variant = "core_cli"\n')
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "grouper.exe").touch()
        (tmp_path / "cli").mkdir()
        (tmp_path / "cli" / "grouper-cli.exe").touch()

        info = load_dist_toml(tmp_path)
        assert info.has_app is True
        assert info.has_cli is True
        assert info.has_server is False

    def test_rejects_unknown_variant(self, tmp_path: Path) -> None:
        (tmp_path / "dist.toml").write_text('variant = "foobar"\n')
        with pytest.raises(ValueError, match="Unknown variant"):
            load_dist_toml(tmp_path)

    def test_rejects_missing_toml(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_dist_toml(tmp_path)

    def test_rejects_malformed_toml(self, tmp_path: Path) -> None:
        (tmp_path / "dist.toml").write_text("this is not valid toml {{{\n")
        with pytest.raises(tomllib.TOMLDecodeError):
            load_dist_toml(tmp_path)


class TestValidateSourceBundle:
    def _make_bundle(self, tmp_path: Path, *, app=True, cli=False, server=False) -> None:
        if app:
            (tmp_path / "app").mkdir(exist_ok=True)
            (tmp_path / "app" / "grouper.exe").touch()
        if cli:
            (tmp_path / "cli").mkdir(exist_ok=True)
            (tmp_path / "cli" / "grouper-cli.exe").touch()
        if server:
            (tmp_path / "server").mkdir(exist_ok=True)
            (tmp_path / "server" / "grouper-server.exe").touch()

    def test_passes_when_all_present(self, tmp_path: Path) -> None:
        info = VARIANTS["core_cli_server"]
        self._make_bundle(tmp_path, app=True, cli=True, server=True)
        validate_source_bundle(tmp_path, info)

    def test_fails_missing_app(self, tmp_path: Path) -> None:
        info = VARIANTS["core_cli_server"]
        self._make_bundle(tmp_path, app=False, cli=True, server=True)
        with pytest.raises(FileNotFoundError, match="Missing app executable"):
            validate_source_bundle(tmp_path, info)

    def test_fails_missing_cli(self, tmp_path: Path) -> None:
        info = VARIANTS["core_cli"]
        self._make_bundle(tmp_path, app=True, cli=False, server=False)
        with pytest.raises(FileNotFoundError, match="Missing CLI executable"):
            validate_source_bundle(tmp_path, info)

    def test_fails_missing_server(self, tmp_path: Path) -> None:
        info = VARIANTS["core_server"]
        self._make_bundle(tmp_path, app=True, cli=False, server=False)
        with pytest.raises(FileNotFoundError, match="Missing server executable"):
            validate_source_bundle(tmp_path, info)

    def test_core_variant_ignores_missing_cli(self, tmp_path: Path) -> None:
        info = VARIANTS["core"]
        self._make_bundle(tmp_path, app=True, cli=False, server=False)
        validate_source_bundle(tmp_path, info)


class TestDefaultDestinations:
    def test_core_returns_app_only(self) -> None:
        info = VARIANTS["core"]
        dests = default_destinations(info)
        assert set(dests.keys()) == {"app"}

    def test_core_cli_returns_app_and_cli(self) -> None:
        info = VARIANTS["core_cli"]
        dests = default_destinations(info)
        assert set(dests.keys()) == {"app", "cli"}

    def test_core_cli_server_returns_all_three(self) -> None:
        info = VARIANTS["core_cli_server"]
        dests = default_destinations(info)
        assert set(dests.keys()) == {"app", "cli", "server"}


class TestVariantInfo:
    def test_all_variants_have_app(self) -> None:
        for info in VARIANTS.values():
            assert info.has_app is True

    def test_component_flags_match_name(self) -> None:
        assert VARIANTS["core"].has_cli is False
        assert VARIANTS["core"].has_server is False
        assert VARIANTS["core_cli"].has_cli is True
        assert VARIANTS["core_cli"].has_server is False
        assert VARIANTS["core_server"].has_cli is False
        assert VARIANTS["core_server"].has_server is True
        assert VARIANTS["core_cli_server"].has_cli is True
        assert VARIANTS["core_cli_server"].has_server is True
