"""test_theme_validation.py -- Theme palette and QSS token validation."""

from __future__ import annotations

import re
from typing import ClassVar

import pytest
from desktop.styles import _THEME_PALETTE, _get_template

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_TOKEN_RE = re.compile(r"\{\{([\w-]+)\}\}")


class TestThemePaletteColors:
    """Verify _THEME_PALETTE has sane error/success colors for every theme."""

    @pytest.fixture(autouse=True)
    def _load_palette(self) -> None:
        self.palette = _THEME_PALETTE

    def test_all_themes_have_danger_and_success(self) -> None:
        for name, colors in self.palette.items():
            assert "danger" in colors, f"{name} missing 'danger'"
            assert "success" in colors, f"{name} missing 'success'"

    def test_danger_and_success_differ(self) -> None:
        for name, colors in self.palette.items():
            assert colors["danger"] != colors["success"], (
                f"{name}: danger and success are identical ({colors['danger']})"
            )

    def test_colors_are_valid_hex(self) -> None:
        for name, colors in self.palette.items():
            for key in ("danger", "success"):
                assert _HEX_RE.match(colors[key]), f"{name}.{key} is not valid hex: {colors[key]}"


class TestThemeTokenCompleteness:
    """Verify every theme can fully satisfy the QSS template."""

    REQUIRED_TOKENS: ClassVar[tuple[str, ...]] = (
        "bg-primary",
        "bg-secondary",
        "bg-tertiary",
        "bg-sidebar",
        "border",
        "text",
        "text-muted",
        "accent",
        "accent-hover",
        "accent-active",
        "danger",
        "success",
        "warning",
        "dialog-bg",
        "dialog-content-bg",
        "dialog-title-bg",
        "dialog-border",
    )

    def test_all_themes_have_required_tokens(self) -> None:
        required = set(self.REQUIRED_TOKENS)
        for name, colors in _THEME_PALETTE.items():
            assert required.issubset(colors), f"{name} missing {sorted(required - set(colors))}"

    def test_all_token_values_are_valid_hex(self) -> None:
        for name, colors in _THEME_PALETTE.items():
            for token, value in colors.items():
                assert _HEX_RE.match(value), f"{name}.{token} is not valid hex: {value}"

    def test_no_duplicate_tokens_within_theme(self) -> None:
        for name, colors in _THEME_PALETTE.items():
            keys = list(colors)
            assert len(keys) == len(set(keys)), f"{name} contains duplicate token keys"


class TestQssTemplateTokenCoverage:
    """Verify template placeholders and palette tokens stay in sync."""

    def test_all_qss_tokens_have_palette_values(self) -> None:
        tokens = set(_TOKEN_RE.findall(_get_template()))
        assert tokens, "expected _base.qss to contain theme tokens"
        for name, colors in _THEME_PALETTE.items():
            assert tokens.issubset(colors), f"{name} missing QSS tokens {sorted(tokens - set(colors))}"

    def test_no_unresolved_tokens_after_render(self) -> None:
        template = _get_template()
        for name, colors in _THEME_PALETTE.items():
            rendered = template
            for token, value in colors.items():
                rendered = rendered.replace("{{" + token + "}}", value)
            assert "{{" not in rendered, name
            assert "}}" not in rendered, name
