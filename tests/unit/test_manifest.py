"""Tests for grouper_install/manifest.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from grouper_install.manifest import (
    InstallManifest,
    read_manifest,
    remove_manifest,
    write_manifest,
)


@pytest.fixture(autouse=True)
def _override_manifest_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("grouper_install.manifest.MANIFEST_DIR", tmp_path / "Grouper")
    monkeypatch.setattr("grouper_install.manifest.MANIFEST_FILE", tmp_path / "Grouper" / "install-manifest.json")


def _sample_manifest() -> InstallManifest:
    return InstallManifest(
        version="1.0.0",
        variant="core_cli",
        install_time="2026-04-20T12:00:00Z",
        destinations={"app": "C:/Program Files/Grouper Apps/Grouper"},
        path_entries=["C:/Program Files/Grouper Apps/Grouper CLI"],
        shortcuts=["C:/Users/test/Desktop/Grouper.lnk"],
        installer_path="C:/Program Files/Grouper Apps/Installer/setup.exe",
    )


class TestWriteManifest:
    def test_creates_file(self, tmp_path: Path) -> None:
        manifest = _sample_manifest()
        write_manifest(manifest)
        manifest_file = tmp_path / "Grouper" / "install-manifest.json"
        assert manifest_file.exists()
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert data["version"] == "1.0.0"

    def test_roundtrip(self) -> None:
        original = _sample_manifest()
        write_manifest(original)
        loaded = read_manifest()
        assert loaded is not None
        assert loaded.version == original.version
        assert loaded.variant == original.variant
        assert loaded.install_time == original.install_time
        assert loaded.destinations == original.destinations
        assert loaded.path_entries == original.path_entries
        assert loaded.shortcuts == original.shortcuts
        assert loaded.installer_path == original.installer_path
        assert loaded.manifest_version == original.manifest_version


class TestReadManifest:
    def test_returns_none_when_missing(self) -> None:
        assert read_manifest() is None

    def test_returns_none_on_corrupt(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "Grouper"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "install-manifest.json").write_text("not valid json {{{")
        assert read_manifest() is None

    def test_reads_old_manifest_without_installer_path(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "Grouper"
        manifest_dir.mkdir(parents=True)
        data = {
            "version": "0.9.0",
            "variant": "core",
            "install_time": "2026-01-01T00:00:00Z",
            "destinations": {"app": "C:/Grouper"},
            "path_entries": [],
            "shortcuts": [],
        }
        (manifest_dir / "install-manifest.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        loaded = read_manifest()
        assert loaded is not None
        assert loaded.version == "0.9.0"
        assert loaded.installer_path == ""
        assert loaded.path_entries == []
        assert loaded.shortcuts == []


class TestRemoveManifest:
    def test_deletes_file(self) -> None:
        manifest = _sample_manifest()
        write_manifest(manifest)
        remove_manifest()
        assert read_manifest() is None

    def test_cleans_empty_dir(self, tmp_path: Path) -> None:
        manifest = _sample_manifest()
        write_manifest(manifest)
        manifest_dir = tmp_path / "Grouper"
        assert manifest_dir.exists()
        remove_manifest()
        assert not manifest_dir.exists()
