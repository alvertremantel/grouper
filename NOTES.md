# Notes

## Standardize Frameless Dialog Styling and Drag Behavior

### Architectural rule for future dialogs

- **`BaseFormDialog`** — use **only** when the dialog contains form rows (`add_row()` / `QFormLayout`).
- **`BaseButtonDialog`** — use for **all other** dialogs that need standard Ok/Cancel (or custom) buttons plus stacked/custom content.
- Never use `self.contentLayout().removeItem(self._form)` as an escape hatch. If you find yourself doing that, the dialog should inherit `BaseButtonDialog` instead.

### Root cause of the parent-cascade bug

The QSS rule `#card QDialog { background-color: {{bg-secondary}}; }` caused any `QDialog` parented beneath a `#card` widget (like `_ActivityDetailEditor`) to paint its top-level background as a solid `bg-secondary` band. Because `FramelessDialog` previously had `autoFillBackground=True`, the 16 px shadow gutter became a visible thick border instead of a transparent margin. Removing the `#card QDialog` rule and adding `QDialog#framelessDialog { background: transparent; }` fixes this without reintroducing black margins, because `dialogFrame` and `dialogContent` remain opaque via `WA_StyledBackground=True`.

### Drag behavior

`DialogTitleBar` previously had `if sys.platform == "win32": return` guards in its mouse event handlers. These were copied from the main-window `TitleBar`, which delegates Windows drag/maximize to native `WM_NCHITTEST` events in `desktop/app.py`. Dialogs have no such native-event path, so the guards simply disabled dragging entirely for frameless dialogs on Windows. Removing them restores cross-platform click-drag movement.

### Color token changes

All themes in `_DIALOG_SURFACE_TOKENS` were moved closer to their respective `bg-secondary`/`border` values while preserving a visible title-bar/border/content distinction. The exact replacement values are recorded in `grouper_core/colors.py`.

### Platform-specific observations

- **Windows:** Drag test passes with `QTest.mouseMove`. The dialog position changes after simulated drag.
- **Screen pixel compositing:** Real screen grabs can differ from expected hex by ~5–8 % due to drop-shadow blur, anti-aliasing, and GPU compositing. Tests use a tolerance of `< 0.08` for frame/title pixel matching and `>= 0.015` for gutter-vs-border distinction.
- **Black theme:** The elevation between `bg-primary` (`#0a0a0a`) and `dialog-title-bg` (`#1e1e1e`) is minimal by design, so the parented-dialog contrast test uses a lower threshold (`0.006`).

### Unresolved visual caveats

- Very slight shadow spillover can still make the gutter margin a few pixels darker/lighter than the host page. This is expected compositor behavior and does not create a visible bug.
- If future themes set `dialog-bg` extremely close to `bg-secondary`, the gutter may be hard to distinguish visually, but it will still not be a solid `bg-secondary` band.
