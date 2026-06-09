"""
Graphical tests for AppStore focus/keyboard navigation.

Verifies that every interactive button in the AppStore is reachable via
directional (arrow-key) navigation using the Android FocusFinder algorithm
implemented in mpos.ui.focus_direction.

Regression tests:
- settings_button is a small top-left button nested inside top_bar (an
  lv.obj container).  With the old ±45° cone algorithm it was only reachable
  via LEFT, not UP, because the angle from a full-width list item center to
  the corner button was outside the cone.  The Android algorithm uses edge
  overlap + beam priority instead, so it reaches the button correctly.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_appstore_focus.py
    Device:  ./tests/unittest.sh tests/test_graphical_appstore_focus.py --ondevice
"""

import time
import unittest
import lvgl as lv
import mpos
import mpos.ui

from mpos import (
    App,
    AppManager,
    retry_action_until,
    wait_for_focus,
    wait_for_text,
)
from mpos.ui import focus_direction


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


UP   = 0
DOWN = 180


def _get_appstore_activity():
    if not mpos.ui.screen_stack:
        return None
    activity, _, _, _ = mpos.ui.screen_stack[-1]
    return activity


def _inject_fake_apps(activity):
    """Populate activity.apps with two dummy entries and rebuild the list."""
    activity.apps = [
        App("Alpha App", "Test", "Short desc", "Long desc",
            None, "http://example.com/a.mpk", "com.test.alpha", "1.0.0", "test", []),
        App("Beta App",  "Test", "Short desc", "Long desc",
            None, "http://example.com/b.mpk", "com.test.beta",  "1.0.0", "test", []),
    ]
    activity.create_apps_list()
    _wait_ms(100)


# ---------------------------------------------------------------------------

class TestAppStoreFocus(unittest.TestCase):
    """Verify keyboard/arrow-key focus navigation inside the AppStore."""

    def setUp(self):
        result = AppManager.start_app("com.micropythonos.appstore")
        self.assertTrue(result, "AppStore failed to launch")
        self.assertTrue(wait_for_text("App Store", timeout=10),
                        "AppStore title never appeared")
        _wait_ms(200)
        activity = _get_appstore_activity()
        self.assertIsNotNone(activity, "Could not get AppStore activity instance")
        _inject_fake_apps(activity)

    def tearDown(self):
        mpos.ui.back_screen()
        _wait_ms(200)

    # ------------------------------------------------------------------

    def test_settings_button_is_focusable(self):
        """settings_button must be focusable via group_focus_obj."""
        activity = _get_appstore_activity()
        settings_btn = activity.settings_button

        lv.group_focus_obj(settings_btn)
        self.assertIsNotNone(
            wait_for_focus(settings_btn, timeout=0.5),
            "settings_button should be focused after group_focus_obj",
        )

    def test_settings_button_reachable_from_list_item_via_up(self):
        """Pressing UP from a list item must reach the settings_button.

        Regression test for the old ±45° cone algorithm: settings_button is a
        small (~34×34 px) button in the top-left corner, nested inside top_bar.
        Its center is at roughly (22, 22).  A full-width list item has its center
        at roughly (160, 76).  The angle between them is ~292° (close to LEFT),
        which the old cone algorithm excluded from the UP (0°±45°) cone.

        The Android FocusFinder algorithm uses edge-overlap + beam priority
        instead of a cone.  settings_button's rect (≈5,5–39,39) has its bottom
        edge (y=39) above the list item's top edge (y=44), so it passes
        isCandidate for UP, and its horizontal span overlaps the screen width so
        it is in the beam — meaning it wins regardless of lateral offset.
        """
        activity = _get_appstore_activity()
        settings_btn = activity.settings_button

        group = lv.group_get_default()
        self.assertIsNotNone(group, "No default focus group")

        # Focus any non-settings, non-hidden widget below the top bar
        candidate = None
        for i in range(group.get_obj_count()):
            obj = group.get_obj_by_index(i)
            if obj is settings_btn:
                continue
            if obj.has_flag(lv.obj.FLAG.HIDDEN):
                continue
            candidate = obj
            break

        self.assertIsNotNone(candidate,
                             "No non-settings focusable object found after injecting fake apps")

        lv.group_focus_obj(candidate)
        self.assertIsNotNone(
            wait_for_focus(candidate, timeout=0.5),
            "Could not focus candidate list item",
        )

        # Press UP repeatedly — settings_button is directly above
        self.assertIsNotNone(
            retry_action_until(
                lambda: _move(UP),
                lambda: settings_btn if _focused_obj() is settings_btn else None,
                attempts=5,
                timeout=0.5,
            ),
            "settings_button was not reachable by pressing UP from a list item.\n"
            "Expected the Android FocusFinder beam-priority algorithm to route UP\n"
            "to the small corner button even though its center is far to the left.",
        )

    def test_update_all_button_reachable_when_visible(self):
        """When 'Update N App(s)' is visible it must be reachable via DOWN from settings_button."""
        activity = _get_appstore_activity()

        # Show the update button and reposition the list below it
        try:
            from appstore_core import AppUpdateManager, AppUpdateState
            um = AppUpdateManager.get_instance()
            um.updatable_apps = [{"fullname": "com.test.fake", "name": "Fake",
                                   "download_url": "http://x.com/a.mpk"}]
            activity._sync_update_banner(AppUpdateState.UPDATES_AVAILABLE, um.updatable_apps)
        except Exception:
            activity.update_all_label.set_text("Update 1 App")
            activity.update_all_button.remove_flag(lv.obj.FLAG.HIDDEN)
            if hasattr(activity, "apps_list") and activity.apps_list:
                activity.apps_list.align(
                    lv.ALIGN.TOP_LEFT, 0,
                    activity._TOP_BAR_HEIGHT + activity._UPDATE_BUTTON_HEIGHT + 8)
        _wait_ms(50)

        settings_btn = activity.settings_button
        update_btn = activity.update_all_button

        lv.group_focus_obj(settings_btn)
        self.assertIsNotNone(
            wait_for_focus(settings_btn, timeout=0.5),
            "settings_button should be focused before moving DOWN",
        )

        self.assertIsNotNone(
            retry_action_until(
                lambda: _move(DOWN),
                lambda: update_btn if _focused_obj() is update_btn else None,
                attempts=3,
                timeout=0.5,
            ),
            "Update All button was not reachable by pressing DOWN from settings_button.",
        )
