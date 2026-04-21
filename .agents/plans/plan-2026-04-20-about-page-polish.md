# Plan: About Page Polish

**Branch:** `feat/polish`
**Date:** 2026-04-20

## Goal

Five targeted improvements to the About page (`grouper/ui/about.py`) plus supporting changes in `_urls.py`, `version_check.py`, and `icons.py`.

---

## Task A — Fix icon scaling in version card (3x)

**Problem:** The app icon in `_version_card()` is rendered at 96x96 (`QSize(96, 96)`) but it looks very small on screen.

**Approach:** Change the icon to render at 288x288 (exactly 3x each dimension). Update the pixmap size, the fixed width, and any related size hints.

**Files:**
- `grouper/ui/about.py` — `_version_card()` method, lines ~173-180
  - Change `QSize(96, 96)` → `QSize(288, 288)`
  - Change `icon_lbl.setPixmap(...)` to use `pixmap(QSize(288, 288))`
  - Change `icon_lbl.setFixedWidth(96)` → `icon_lbl.setFixedWidth(288)`

---

## Task B — Add GitHub repo and releases links

**Problem:** The links card only has one link (Contact). Need to add GitHub repo and GitHub releases links.

**Approach:** Add two new URL constants to `_urls.py`, add new icon templates for `github` and `download` to `icons.py`, and add two more link rows to `_links_card()`.

**Files:**
- `grouper/_urls.py` — add:
  ```
  GITHUB_REPO_URL = "https://github.com/alvertremantel/grouper"
  GITHUB_RELEASES_URL = "https://github.com/alvertremantel/grouper/releases"
  ```
- `grouper/ui/icons.py` — add two new SVG templates:
  - `github` — GitHub mark (simplified octocat silhouette, Feather-style)
  - `download` — download arrow icon
  - Register both in `_SVG_TEMPLATES`
- `grouper/ui/about.py` — `_links_card()`:
  - Add `_make_link_row("github", "GitHub Repository", GITHUB_REPO_URL)` after the heading
  - Add `_make_link_row("download", "Releases / Changelog", GITHUB_RELEASES_URL)` after GitHub repo
  - Keep existing Contact link and Threads note at the bottom
  - Update imports to include `GITHUB_REPO_URL`, `GITHUB_RELEASES_URL`

---

## Task C — Switch version checking to GitHub Releases API

**Problem:** Version checking currently uses the GitLab Releases API. The project is moving to GitHub.

**Approach:** Rewrite `version_check.py` to query the GitHub Releases API (`/repos/{owner}/{repo}/releases/latest`) instead of GitLab. Update `_urls.py` to replace GitLab constants with GitHub equivalents.

**Files:**
- `grouper/_urls.py`:
  - Remove `GITLAB_NAMESPACE`, `GITLAB_PROJECT`, `GITLAB_RELEASES_API_URL`, `GITLAB_RELEASES_URL`
  - Add:
    ```
    GITHUB_RELEASES_API_URL = "https://api.github.com/repos/alvertremantel/grouper/releases/latest"
    ```
  - `GITHUB_RELEASES_URL` already added in Task B
- `grouper/version_check.py`:
  - Update import: `from .._urls import GITHUB_RELEASES_API_URL, GITHUB_RELEASES_URL`
  - In `check_for_update()`:
    - Use `GITHUB_RELEASES_API_URL` instead of `GITLAB_RELEASES_API_URL`
    - GitHub returns a single release object (not an array) at the `/latest` endpoint
    - Parse `tag_name` from the JSON response directly (not `releases[0]`)
    - Set release URL to `GITHUB_RELEASES_URL`
  - The `_parse_version()` helper and `VersionCheckWorker` remain unchanged
- `grouper/app.py` (line 178, 310-316) — no changes needed (it consumes signals, not URLs directly)
- `grouper/main.py` (lines 118-125) — no changes needed
- **Tests:** Update `tests/unit/db/test_optimizations.py` (lines 1100-1141) if they reference GitLab URLs directly. The `_parse_version` tests should be unaffected.

---

## Task D — Move Features card to bottom, make it collapsible

**Problem:** The Features card (`_readme_card`) sits in the middle of the page. It should be at the bottom and collapsible to reduce visual clutter.

**Approach:** Move `_readme_card()` below `_sysinfo_card()` in the layout. Replace the static card with a collapsible section using a toggle button that expands/collapses the content. Start collapsed by default.

**Files:**
- `grouper/ui/about.py`:
  - Reorder `_build()` layout: version → links → shoutouts (Task E) → sysinfo → readme (collapsed)
  - Rename `_readme_card()` or create a new collapsible wrapper:
    - A `QPushButton` styled as a section header with a ▶/▼ toggle indicator
    - A `QWidget` container holding all the feature/data/built-with content, initially hidden
    - Click the button → `setVisible(not container.isVisible())` and update the arrow indicator
  - The content inside remains the same (features list, data storage note, built-with list)
  - May need to add minimal QSS for the toggle button (can reuse existing button styles or add a small rule to `_base.qss`)

---

## Task E — Add "Shoutouts" section

**Problem:** Need to give special mention to two early supporters who purchased Grouper on Gumroad before it was open-sourced.

**Approach:** Add a new card between Links and System Info (or between Links and Shoutouts, depending on final layout). Simple, tasteful card with their handles.

**Files:**
- `grouper/ui/about.py`:
  - Add `_shoutouts_card()` method — returns a `_card()` QFrame with:
    - Header: "Special Thanks" or "Shoutouts" (subheading style)
    - Content: "With gratitude to our early supporters who purchased Grouper on Gumroad before it went open-source:"
    - Two entries:
      - `@jackgrebin` — styled as a muted label
      - `@timecode.violation` — styled as a muted label
    - Keep it simple and brief. No external links needed (Threads handles aren't URLs).
  - Insert between `_links_card()` and `_sysinfo_card()` in `_build()`

---

## Execution Order

1. **Task A** — Icon scaling (simple, isolated)
2. **Task B** — Add GitHub/releases links (adds URLs + icons)
3. **Task C** — Switch version check to GitHub (builds on Task B's URL constants)
4. **Task D** — Collapsible Features card (UI restructure)
5. **Task E** — Shoutouts card (simple addition)

Then: lint (`ruff check`), typecheck (`ty check`), run full test suite.

---

## Risks / Notes

- GitHub API rate limit: unauthenticated requests are limited to 60/hour per IP. The existing caching (`_cache` in `version_check.py`) mitigates this — each process only checks once.
- The `.ico` file may not scale cleanly to 288x288. If it looks pixelated, we can fall back to a slightly smaller size (e.g., 192x192 = 2x). Test visually.
- `_parse_version` tests at `tests/unit/db/test_optimizations.py:1100-1141` may need updating if Task C changes any version-parsing logic (it shouldn't, but verify).
- No existing widget tests for `AboutView` — consider adding a basic `test_about.py` if time permits.
