"""test_theme_validation.py -- Theme color palette validation.

Verifies that each theme has distinct, non-clashing error/success colors
and that all color values are valid hex.
"""

from __future__ import annotations

import re

import pytest


class TestThemePaletteColors:
    """Verify _THEME_PALETTE has sane error/success colors for every theme."""

    @pytest.fixture(autouse=True)
    def _load_palette(self) -> None:
        from grouper.styles import _THEME_PALETTE

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
        hex_re = re.compile(r"^#[0-9a-fA-F]{6}$")
        for name, colors in self.palette.items():
            for key in ("danger", "success"):
                assert hex_re.match(colors[key]), f"{name}.{key} is not valid hex: {colors[key]}"
