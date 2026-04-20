"""
Graphical test for SettingActivity radio-button invariant.

Clicking the already-selected radio option previously let the user
un-select it and save an empty string for the setting. This broke the
radio-group convention (exactly one option selected once the user has
made a choice) and let apps with required radio settings — Lightning
Piggy's wallet_type being the motivating case — silently lose their
configuration on a stray tap.

The fix: when the user clicks the currently-active option, re-add the
CHECKED state so the selection sticks. Changing the pick by clicking a
different option works exactly as before.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_setting_activity_radio.py
    Device:  ./tests/unittest.sh tests/test_graphical_setting_activity_radio.py --ondevice
"""

import unittest
import lvgl as lv

from mpos.ui.setting_activity import SettingActivity
from mpos import wait_for_render


class _FakeEvent:
    """Minimal stand-in for an LVGL event — SettingActivity.radio_event_handler
    only calls event.get_target_obj()."""
    def __init__(self, target):
        self._target = target
    def get_target_obj(self):
        return self._target


class _RadioHandlerFixture:
    """Holds the same attributes SettingActivity.radio_event_handler reads on
    `self`. Avoids instantiating the full Activity (which needs a running
    AppManager) just to exercise one callback."""
    def __init__(self, container, active_index):
        self.radio_container = container
        self.active_radio_index = active_index


class TestSettingActivityRadioInvariant(unittest.TestCase):
    """Verify the radio-group invariant: exactly one option stays selected
    after the user has made a pick."""

    def setUp(self):
        self.screen = lv.obj()
        self.screen.set_size(320, 240)
        lv.screen_load(self.screen)

        self.container = lv.obj(self.screen)
        self.container.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        self.cb0 = lv.checkbox(self.container)
        self.cb0.set_text("Option 0")
        self.cb1 = lv.checkbox(self.container)
        self.cb1.set_text("Option 1")

        wait_for_render(2)

    def tearDown(self):
        lv.screen_load(lv.obj())
        wait_for_render(2)

    def _invoke(self, target, active_index):
        """Run radio_event_handler as it would run in production — we bind the
        unbound function to a fixture that exposes the attributes the handler
        reads on `self`."""
        fixture = _RadioHandlerFixture(self.container, active_index)
        SettingActivity.radio_event_handler(fixture, _FakeEvent(target))
        return fixture

    def test_click_active_option_keeps_it_selected(self):
        """Clicking the already-selected option must NOT un-select it.

        Before the fix: fixture.active_radio_index flips to -1 and the
        checkbox stays un-checked, so save_setting would persist "".
        After the fix: the checkbox is re-checked and active_radio_index
        stays pointing at the same option.
        """
        self.cb0.add_state(lv.STATE.CHECKED)
        # Simulate LVGL's "checkbox toggle on click" behaviour: STATE.CHECKED
        # has just been removed and VALUE_CHANGED is about to fire.
        self.cb0.remove_state(lv.STATE.CHECKED)
        self.assertFalse(bool(self.cb0.get_state() & lv.STATE.CHECKED))

        fixture = self._invoke(self.cb0, active_index=0)

        self.assertTrue(
            bool(self.cb0.get_state() & lv.STATE.CHECKED),
            "active option must be re-checked when user tries to un-select it",
        )
        self.assertEqual(
            fixture.active_radio_index, 0,
            "active_radio_index must stay pointing at the active option",
        )

    def test_click_different_option_switches_selection(self):
        """Clicking a *different* option still switches normally: the new one
        becomes checked, the old one loses its checked state, and
        active_radio_index moves."""
        self.cb0.add_state(lv.STATE.CHECKED)
        # LVGL toggled cb1 on, firing VALUE_CHANGED with cb1 as the target.
        self.cb1.add_state(lv.STATE.CHECKED)

        fixture = self._invoke(self.cb1, active_index=0)

        self.assertFalse(
            bool(self.cb0.get_state() & lv.STATE.CHECKED),
            "previously-active option must lose its CHECKED state",
        )
        self.assertTrue(
            bool(self.cb1.get_state() & lv.STATE.CHECKED),
            "newly-clicked option must stay CHECKED",
        )
        self.assertEqual(fixture.active_radio_index, 1)

    def test_first_selection_from_empty_state(self):
        """Before any choice is made, active_radio_index = -1. Clicking any
        option selects it normally."""
        # Nothing checked yet; user clicks cb1.
        self.cb1.add_state(lv.STATE.CHECKED)

        fixture = self._invoke(self.cb1, active_index=-1)

        self.assertTrue(bool(self.cb1.get_state() & lv.STATE.CHECKED))
        self.assertEqual(fixture.active_radio_index, 1)
