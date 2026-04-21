"""test_app.py -- Consolidated E2E tests for Grouper.

Five tests that launch the real app in a subprocess and validate
end-to-end behavior via pywinauto. These are the "does the app work"
tests -- everything else is covered by unit and widget tests.
"""

from __future__ import annotations

import time

import pytest

from tests.e2e.helpers import (
    click_sidebar_button,
    find_all_by_name_substring,
    find_by_name_substring,
    seed_activity_via_db,
    select_combo_item,
    wait_for_animation,
    wait_for_element,
)

pytestmark = pytest.mark.e2e

SIDEBAR_ITEMS = [
    "Dashboard",
    "Time Tracker",
    "Task Board",
    "Task List",
    "Calendar",
    "History",
    "Summary",
    "Settings",
    "About",
]


def test_app_launches_and_renders(main_window, capture) -> None:
    """App starts, window is visible, title is correct, has non-zero size."""
    capture("launched")
    assert main_window.is_visible()

    title = main_window.window_text()
    assert "Grouper" in title
    assert "Productivity Hub" in title

    rect = main_window.rectangle()
    assert rect.width() > 0
    assert rect.height() > 0

    heading = find_by_name_substring(main_window, "Text", "Dashboard")
    assert heading.is_visible()
    capture("dashboard_loaded")


def test_sidebar_navigation_all_views(main_window, capture) -> None:
    """Click every sidebar item; confirm window stays visible after each."""
    for item in SIDEBAR_ITEMS:
        click_sidebar_button(main_window, item)
        time.sleep(0.3)
        assert main_window.is_visible(), f"Window gone after clicking {item}"

    capture("all_views_visited")


def test_title_bar_controls(main_window, capture) -> None:
    """Verify min/max/close buttons exist and maximize/restore toggles."""
    # Check buttons exist
    buttons = main_window.descendants(control_type="Button")
    button_texts = []
    for btn in buttons:
        try:
            button_texts.append(btn.window_text())
        except Exception:
            continue

    assert any("\u2014" in t for t in button_texts), "Minimize button not found"
    assert any("\u2610" in t or "\u2750" in t for t in button_texts), "Maximize button not found"
    assert any("\u2715" in t for t in button_texts), "Close button not found"

    capture("buttons_visible")

    # Test maximize/restore toggle
    rect_max = main_window.rectangle()

    # Click restore (find the maximize/restore button)
    for btn in buttons:
        try:
            txt = btn.window_text()
            if "\u2750" in txt or "\u2610" in txt:
                btn.click_input()
                break
        except Exception:
            continue
    time.sleep(0.8)

    rect_normal = main_window.rectangle()
    assert main_window.is_visible()
    assert rect_normal.width() <= rect_max.width()

    capture("restored")

    # Re-maximize
    buttons = main_window.descendants(control_type="Button")
    for btn in buttons:
        try:
            txt = btn.window_text()
            if "\u2610" in txt or "\u2750" in txt:
                btn.click_input()
                break
        except Exception:
            continue
    time.sleep(0.8)

    assert main_window.is_visible()
    capture("remaximized")

    # Test minimize and restore
    for btn in main_window.descendants(control_type="Button"):
        try:
            if "\u2014" in btn.window_text():
                btn.invoke()
                break
        except Exception:
            continue
    time.sleep(1.0)

    main_window.restore()
    time.sleep(0.5)
    main_window.wait("visible", timeout=5)
    assert main_window.is_visible()
    capture("minimize_restore_done")


def test_theme_switch_survives(main_window, capture) -> None:
    """Switch to Light theme, navigate away, switch back to Dark."""
    click_sidebar_button(main_window, "Settings")
    time.sleep(0.5)

    combos = main_window.descendants(control_type="ComboBox")
    assert combos, "No ComboBox found on Settings page"

    select_combo_item(combos[0], "Light")
    time.sleep(0.5)
    assert main_window.is_visible()
    capture("light_theme")

    click_sidebar_button(main_window, "Dashboard")
    time.sleep(0.3)
    assert main_window.is_visible()

    click_sidebar_button(main_window, "Settings")
    time.sleep(0.3)

    combos = main_window.descendants(control_type="ComboBox")
    select_combo_item(combos[0], "Dark")
    time.sleep(0.5)
    assert main_window.is_visible()
    capture("dark_theme_restored")


def test_session_lifecycle(main_window, test_data_dir, capture) -> None:
    """Seed activity, start session, pause, resume, stop -- full lifecycle."""
    seed_activity_via_db(test_data_dir, "Coding", groups=["Dev"])

    # Navigate to trigger refresh
    click_sidebar_button(main_window, "Settings")
    click_sidebar_button(main_window, "Time Tracker")

    capture("tracker_loaded")

    # Select group and click activity to start session
    combos = main_window.descendants(control_type="ComboBox")
    if combos:
        select_combo_item(combos[0], "Dev")
        time.sleep(0.5)

    label = wait_for_element(main_window, "Text", "Coding", timeout=5)
    label.click_input()
    wait_for_animation()

    capture("session_started")

    # Verify running state
    pause_btn = find_by_name_substring(main_window, "Button", "Pause")
    assert pause_btn.is_visible()
    stop_btn = find_by_name_substring(main_window, "Button", "Stop")
    assert stop_btn.is_visible()

    # Pause
    pause_btn.click_input()
    wait_for_animation()
    resume_btn = wait_for_element(main_window, "Button", "Resume", timeout=5)
    assert resume_btn.is_visible()
    assert len(find_all_by_name_substring(main_window, "Button", "Pause")) == 0
    capture("session_paused")

    # Resume
    resume_btn.click_input()
    wait_for_animation()
    pause_btn = wait_for_element(main_window, "Button", "Pause", timeout=5)
    assert pause_btn.is_visible()
    capture("session_resumed")

    # Stop
    stop_btn = find_by_name_substring(main_window, "Button", "Stop")
    stop_btn.click_input()
    time.sleep(0.5)

    confirm = wait_for_element(main_window, "Button", "Confirm", timeout=5)
    confirm.click_input()
    wait_for_animation(1.0)

    placeholder = wait_for_element(main_window, "Text", "No active sessions", timeout=5)
    assert placeholder.is_visible()
    capture("session_stopped")
