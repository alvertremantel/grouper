# Fix Summary Zero-Bar Theme Colors

## Goal

Fix the Summary tab vertical trend chart so zero-hour days use the active theme colors after a theme switch, specifically covering the observed DARK to SAGE transition where only some bars are zero and other bars have data.

## Current Understanding

- The vertical daily trend chart is implemented in `grouper/ui/summary.py` by `MiniBarTrend` and `_TrendBar`.
- `MiniBarTrend.update_data()` stores the current data in `self._days`, recomputes colors from `theme_colors(get_config().theme)`, and applies inline `background-color` styles through `_TrendBar.populate()`.
- `MiniBarTrend.changeEvent()` handles `QEvent.Type.PaletteChange` by calling `update_data(self._days, self._bar_width)`, so existing bars are recolored when the app theme changes.
- The recent regression test `tests/widget/test_summary_stats.py::test_trend_bars_update_on_theme_switch` only checks nonzero data (`3600.0`, `7200.0`) and switches DARK to LIGHT.
- The likely cause is `grouper/ui/summary.py:269`: `card_bg = colors.get("card_bg", "#24263a")`.
- No palette defines a `card_bg` token. The chart therefore always uses the hardcoded dark fallback `#24263a` as the low-end blend source.
- For zero-value days, `ratio = val / max_val` is `0`, so the color is mostly this fallback: `lerp_hex("#24263a", accent, 0.2)`.
- For nonzero days, the color moves toward the active theme accent (`0.2 + 0.8 * ratio`), which explains why bars with data appear to update while zero-hour bars still look like the old/dark theme.
- Reproduction by direct widget simulation currently gives DARK zero `#353e5f`, SAGE zero `#39444b`, and expected SAGE-from-card-surface around `#4b604c` if blending from `bg-secondary`.

## Intended Approach

- Use an actual palette token for the chart surface instead of the nonexistent `card_bg` key.
- Prefer `bg-secondary` as the low-end blend source because `_base.qss` documents `bg-secondary` as the card/panel background and `#card` uses `{{bg-secondary}}`.
- Keep the existing interpolation behavior and minimum-height zero bar behavior intact; only correct the theme base color.
- Add a targeted widget regression test that includes both a zero-value bar and a nonzero-value bar while switching DARK to SAGE.

## Implementation Steps

1. Update `grouper/ui/summary.py` in `MiniBarTrend.update_data()`.
   - Replace `card_bg = colors.get("card_bg", "#24263a")` with `card_bg = colors["bg-secondary"]`.
   - If choosing a defensive fallback, use `colors.get("bg-secondary", "#24263a")`; do not introduce a new `card_bg` token unless there is a separate design requirement.
   - Leave `accent = colors["accent"]`, the interpolation formula, and `_TrendBar.populate()` unchanged.

2. Add a regression test in `tests/widget/test_summary_stats.py`.
   - Keep the existing `test_trend_bars_update_on_theme_switch` or adjust it only if it remains equivalent.
   - Add a new test such as `test_zero_trend_bars_use_active_theme_on_theme_switch`.
   - In the new test, patch `grouper.ui.summary.get_config` to DARK, call `load_theme(qapp, "dark")`, create `MiniBarTrend`, and call `update_data([("M", 0.0), ("T", 7200.0)], bar_width=22)`.
   - Capture the zero bar stylesheet from `chart._bars[0]._bar.styleSheet()`.
   - Patch `grouper.ui.summary.get_config` to SAGE, call `load_theme(qapp, "sage")`, and `qapp.processEvents()`.
   - Compute the expected SAGE zero color with `lerp_hex(theme_colors("sage")["bg-secondary"], theme_colors("sage")["accent"], 0.2)`.
   - Assert the new zero bar stylesheet contains `background-color: <expected>;` and differs from the original DARK zero stylesheet.
   - Include the nonzero bar in the data to preserve the user-observed condition that the issue happens when other bars have data.

3. Verify the targeted behavior.
   - Run `uv run pytest tests/widget/test_summary_stats.py`.
   - Confirm the existing nonzero theme-switch test still passes.
   - Confirm the new zero-bar DARK to SAGE test fails before the code change and passes after the code change if validating red/green locally.

4. Run style and broader verification.
   - Run `uv run ruff check grouper/ui/summary.py tests/widget/test_summary_stats.py`.
   - Run `uv run pytest` if practical.
   - If full `pytest` reports the known pre-existing `win32com` import failure, document that separately and ensure the targeted Summary tests pass.

5. Update project context after verification.
   - Update `.agents/context/STATUS.md` Recent Changes or Active Work to note that Summary zero-value trend bars now derive from the active theme card surface on theme changes.
   - Update `.agents/context/NOTES.md` only if a durable rule is useful; suggested note: Summary trend bar low-end colors should use real palette surface tokens such as `bg-secondary`, not ad-hoc nonexistent aliases.

## Assumptions And Decisions

- The correct visual target for a zero-hour bar is a low-intensity accent blend over the chart/card surface, not a full accent color and not the generic track color.
- `bg-secondary` is the right base because the chart lives on card/panel surfaces and `_base.qss` identifies `bg-secondary` as the card/panel background.
- The fix should not add backward compatibility for the nonexistent `card_bg` token because it is internal code, not persisted data or an external API.
- The scope is limited to the Summary vertical trend chart. Horizontal activity bars already use QSS theme tokens and are not part of this bug.

## Risks

- Some themes may have subtle zero-bar contrast if `bg-secondary` and `accent` are close. The targeted test should check exact color recomputation, not subjective contrast.
- Qt may emit style-related events differently by platform; preserve the existing `PaletteChange` path and use `load_theme(...); qapp.processEvents()` in the test, matching the existing test pattern.
- If maintainers prefer zero-hour bars to visually match the chart track instead of the card surface, switch the base token to `bg-tertiary` and update the test expectation accordingly.
