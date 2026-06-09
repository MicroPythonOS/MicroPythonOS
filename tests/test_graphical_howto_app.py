"""
Graphical test for the HowTo app focus/keyboard navigation.

Verifies that the HowTo app can be fully controlled via focus-direction
(arrow key) navigation: all interactive widgets (checkbox, close button)
are reachable via directional navigation, and the close button finishes
the activity.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_howto_app.py
    Device:  ./tests/unittest.sh tests/test_graphical_howto_app.py --ondevice
"""

import time
import unittest
import lvgl as lv
import mpos.ui
from mpos import (
    AppManager,
    wait_for_text,
    retry_action_until,
    find_label_with_text,
    find_button_with_text,
    simulate_click,
    get_widget_coords,
)
from mpos.ui import focus_direction
from mpos.activity_navigator import get_foreground_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_ms(ms):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        lv.task_handler()
        time.sleep(0.01)


def _focused_obj():
    group = lv.group_get_default()
    return group.get_focused() if group else None


def _move(angle):
    focus_direction.move_focus_direction(angle)
    _wait_ms(50)


DOWN = 180


def _click_focused():
    focused = _focused_obj()
    if focused is not None:
        coords = get_widget_coords(focused)
        if coords:
            simulate_click(coords["center_x"], coords["center_y"])
            _wait_ms(150)


def _checkbox_checked_state(checkbox):
    return bool(checkbox.get_state() & lv.STATE.CHECKED)


def _toggle_checkbox_with_retries(checkbox, expected_checked, attempts=3):
    result = retry_action_until(
        lambda: (lv.group_focus_obj(checkbox), _wait_ms(50), _click_focused()),
        lambda: checkbox if _checkbox_checked_state(checkbox) == expected_checked else None,
        attempts=attempts,
        timeout=1.5,
        interval=0.05,
    )
    return result is not None


def _find_checkbox(screen):
    return find_label_with_text(screen, "Don't show again")


def _navigate_to_widget(target, max_steps=15):
    """Navigate DOWN repeatedly until target widget is focused."""
    if _focused_obj() is None:
        first_label = find_label_with_text(lv.screen_active(), "How to Navigate")
        if first_label:
            lv.group_focus_obj(first_label)
            _wait_ms(50)
    for _ in range(max_steps):
        if _focused_obj() is target:
            return True
        _move(DOWN)
    return _focused_obj() is target


def _ensure_checkbox_is_checked():
    """If Don't-show-again checkbox exists and is unchecked, toggle it on
    so that onPause will clear auto_start_app_early, preventing the
    launcher from re-launching this app."""
    screen = lv.screen_active()
    checkbox = _find_checkbox(screen)
    if checkbox is None:
        return
    if checkbox.get_state() & lv.STATE.CHECKED:
        return
    reached = _navigate_to_widget(checkbox)
    if not reached:
        return
    checkbox.add_state(lv.STATE.CHECKED)
    _wait_ms(50)


def _go_back_to_launcher():
    """Call back_screen repeatedly until only the launcher remains."""
    for _ in range(5):
        if len(mpos.ui.screen_stack) <= 1:
            return
        mpos.ui.back_screen()
        _wait_ms(500)


# ---------------------------------------------------------------------------

class TestHowToAppFocusNavigation(unittest.TestCase):
    """Verify that the HowTo app supports keyboard/focus navigation."""

    def setUp(self):
        # Clean up any leftover activities (e.g. from auto-start re-launch)
        _go_back_to_launcher()

        result = AppManager.start_app("com.micropythonos.howto")
        self.assertTrue(result, "HowTo app failed to launch")
        self.assertTrue(
            wait_for_text("How to Navigate", timeout=10),
            "HowTo app did not load within timeout",
        )
        _wait_ms(200)

    def tearDown(self):
        try:
            # Ensure the checkbox is checked so onPause clears
            # auto_start_app_early and prevents re-launch
            _ensure_checkbox_is_checked()
            _wait_ms(50)
            _go_back_to_launcher()
        except Exception:
            pass

    # ------------------------------------------------------------------

    def test_checkbox_reachable_and_togglable_via_focus(self):
        """The checkbox must be reachable via DOWN and toggleable with a click."""
        screen = lv.screen_active()
        checkbox = _find_checkbox(screen)
        self.assertIsNotNone(
            checkbox,
            "Could not find checkbox ('Don't show again') in HowTo app",
        )

        reached = _navigate_to_widget(checkbox)
        self.assertTrue(
            reached,
            "Could not navigate to checkbox via DOWN key",
        )

        initially_checked = bool(checkbox.get_state() & lv.STATE.CHECKED)
        self.assertFalse(initially_checked, "Checkbox should start unchecked")

        self.assertTrue(
            _toggle_checkbox_with_retries(checkbox, expected_checked=True),
            "Checkbox should be checked after clicking",
        )

        self.assertTrue(
            _toggle_checkbox_with_retries(checkbox, expected_checked=False),
            "Checkbox should be unchecked after clicking it again",
        )

    def test_close_button_reachable_and_closes_app(self):
        """The close button must be reachable via DOWN and closes the app."""
        screen = lv.screen_active()
        close_button = find_button_with_text(screen, "Close")
        self.assertIsNotNone(
            close_button,
            "Could not find Close button in HowTo app",
        )

        checkbox = _find_checkbox(screen)
        self.assertIsNotNone(
            checkbox,
            "Could not find checkbox in HowTo app",
        )

        # Toggle the checkbox to prevent autostart re-launch
        reached = _navigate_to_widget(checkbox)
        self.assertTrue(reached, "Could not navigate to checkbox")

        checkbox.add_state(lv.STATE.CHECKED)
        _wait_ms(50)

        checked = bool(checkbox.get_state() & lv.STATE.CHECKED)
        self.assertTrue(
            checked,
            "Checkbox should be checked (Don't show again) before closing",
        )

        # Navigate from checkbox to close button
        lv.group_focus_obj(checkbox)
        _wait_ms(50)
        _move(DOWN)

        self.assertIs(
            _focused_obj(),
            close_button,
            "Close button should be focused after DOWN from checkbox",
        )

        # Send CLICKED event to close the activity
        close_button.send_event(lv.EVENT.CLICKED, None)
        _wait_ms(200)

        # After clicking close, we should be back at the launcher
        foreground = get_foreground_app()
        self.assertNotEqual(
            foreground,
            "com.micropythonos.howto",
            f"HowTo should not be the foreground app after closing. "
            f"Got: {foreground}",
        )
