# Qt Pitfalls

## Dialog contrast investigation notes

- We chased the wrong problem first.
- The original theory was "dialog body is transparent."
- The real user-visible failure was "dialog blends into the host so hard it reads as missing."

- `widget.grab()` and child-widget pixel checks were not enough.
- They proved a widget could paint a color offscreen.
- They did not prove the shown dialog looked correct in the real app flow.

- `WA_TranslucentBackground` on a top-level frameless dialog was the biggest trap.
- In isolation it looked workable.
- In the live app it distorted the shown dialog surface enough that on-screen colors did not match the widget's own painted colors.
- This produced false confidence from offscreen tests.

- The bad assumption was: if `dialogContent.grab()` looks opaque, the user sees that same surface.
- That assumption was wrong.

- Another trap: improving the dialog shell is not the same as improving the visible dialog body.
- `AddGroupDialog` is visually dominated by its inner `QListWidget`.
- The shell could be more distinct while the large list surface still blended into the activity editor behind it.

- Theme-token checks also were not enough.
- Distinct `dialog-*` tokens helped, but they only proved intent.
- They did not prove the live dialog path was using those colors in a perceptible way.

- The stylesheet had stale frameless-dialog assumptions baked in.
- Transparent top-level dialog behavior made sense only for the old translucent-shell idea.
- That was actively unhelpful once the goal became "make the actual dialog body clearly visible."

- `autoFillBackground` was also a red herring.
- Qt docs explicitly warn that stylesheet backgrounds disable the usefulness of that signal.
- Tests should not treat it as evidence that a styled widget will render correctly.

- The useful regression ended up being specific to the real flow.
- Compare `AddGroupDialog` surfaces against the host activity editor surface.
- Test the parented dialog context, not just a free-floating shell.

- The fix direction that finally mapped to reality was:
- remove `WA_TranslucentBackground` from shared frameless dialogs;
- keep inner dialog surfaces explicitly stylesheet-painted;
- style dialog-scoped list surfaces, not just the outer frame;
- tune low-contrast themes only after the real surface path is correct.

- Rule for future Qt visual bugs:
- do not trust offscreen grabs alone;
- do not confuse shell contrast with content contrast;
- test the exact user-visible widget hierarchy;
- if a frameless top-level window is involved, treat translucency as suspect until proven otherwise.
