from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VariantInfo:
    variant: str
    has_app: bool
    has_cli: bool
    has_server: bool


VARIANTS: dict[str, VariantInfo] = {
    "core": VariantInfo(variant="core", has_app=True, has_cli=False, has_server=False),
    "core_cli": VariantInfo(variant="core_cli", has_app=True, has_cli=True, has_server=False),
    "core_server": VariantInfo(variant="core_server", has_app=True, has_cli=False, has_server=True),
    "core_cli_server": VariantInfo(variant="core_cli_server", has_app=True, has_cli=True, has_server=True),
}


def load_dist_toml(release_root: Path) -> VariantInfo:
    dist_toml = release_root / "dist.toml"
    with dist_toml.open("rb") as f:
        data = tomllib.load(f)
    variant = data.get("variant")
    if variant is None:
        raise ValueError(f"Missing 'variant' key in {dist_toml}")
    if variant not in VARIANTS:
        raise ValueError(
            f"Unknown variant {variant!r} in {dist_toml}. "
            f"Expected one of: {', '.join(VARIANTS)}"
        )
    info = VARIANTS[variant]
    validate_source_bundle(release_root, info)
    return info


def validate_source_bundle(release_root: Path, info: VariantInfo) -> None:
    app_exe = release_root / "app" / "grouper.exe"
    if not app_exe.exists():
        raise FileNotFoundError(f"Missing app executable: {app_exe}")

    if info.has_cli:
        cli_exe = release_root / "cli" / "grouper-cli.exe"
        if not cli_exe.exists():
            raise FileNotFoundError(f"Missing CLI executable: {cli_exe}")

    if info.has_server:
        server_exe = release_root / "server" / "grouper-server.exe"
        if not server_exe.exists():
            raise FileNotFoundError(f"Missing server executable: {server_exe}")


def default_destinations(info: VariantInfo) -> dict[str, Path]:
    base = Path("C:/Program Files/Grouper Apps")
    dests: dict[str, Path] = {"app": base / "Grouper"}
    if info.has_cli:
        dests["cli"] = base / "Grouper CLI"
    if info.has_server:
        dests["server"] = base / "Grouper Server"
    return dests
