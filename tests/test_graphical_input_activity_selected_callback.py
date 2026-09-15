"""
Graphical test for InputActivity's optional `selected_callback`.

A setting dict may carry `selected_callback`; InputActivity calls it with the
option VALUE on every radio pick before Save: on a new selection, and again
on a re-tap of the already-selected option (a preview hook wants to fire
again). It must not fire when allow_deselect un-checks the active option
(nothing is selected then), exceptions inside it must be swallowed, and
fixtures/instances without the attribute must keep working unchanged.

Same fixture technique as test_graphical_setting_activity_radio.py: the
unbound handler is run against a small object exposing the attributes it
reads on `self`, avoiding a full Activity/AppManager.

Usage:
    python3 scripts/test_runner.py tests/test_graphical_input_activity_selected_callback.py
"""

import unittest
import lvgl as lv

from mpos.ui.input_activity import InputActivity
from mpos import wait_for_render

OPTIONS = [("Off", "off"), ("Pig Oink", "oink"), ("Pig Squeal", "squeal")]


class _FakeEvent:
    def __init__(self, target):
        self._target = target
    def get_target_obj(self):
        return self._target


class _Fixture:
    def __init__(self, container, active_index, callback=None, options=OPTIONS, allow_deselect=False):
        self.radio_container = container
        self.active_radio_index = active_index
        self._radio_allow_deselect = allow_deselect
        if callback is not None:
            self._selected_callback = callback
            self._ui_options = options


class TestSelectedCallback(unittest.TestCase):
    def setUp(self):
        self.screen = lv.obj()
        self.screen.set_size(320, 240)
        lv.screen_load(self.screen)
        self.container = lv.obj(self.screen)
        self.container.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.cbs = []
        for label, _ in OPTIONS:
            cb = lv.checkbox(self.container)
            cb.set_text(label)
            self.cbs.append(cb)
        wait_for_render(2)

    def tearDown(self):
        lv.screen_load(lv.obj())
        wait_for_render(2)

    def _tap(self, fixture, index, check):
        # Emulate LVGL: a tap toggles the checkbox state, then the handler runs.
        if check:
            self.cbs[index].add_state(lv.STATE.CHECKED)
        else:
            self.cbs[index].remove_state(lv.STATE.CHECKED)
        InputActivity.radio_event_handler(fixture, _FakeEvent(self.cbs[index]))

    def test_new_selection_fires_with_value(self):
        seen = []
        f = _Fixture(self.container, -1, seen.append)
        self._tap(f, 1, check=True)
        self.assertEqual(seen, ["oink"])
        self.assertEqual(f.active_radio_index, 1)

    def test_switching_option_fires_new_value_only(self):
        seen = []
        self.cbs[1].add_state(lv.STATE.CHECKED)
        f = _Fixture(self.container, 1, seen.append)
        self._tap(f, 2, check=True)
        self.assertEqual(seen, ["squeal"])
        self.assertFalse(self.cbs[1].has_state(lv.STATE.CHECKED))
        self.assertTrue(self.cbs[2].has_state(lv.STATE.CHECKED))

    def test_retap_of_active_option_fires_again_and_stays_checked(self):
        seen = []
        self.cbs[1].add_state(lv.STATE.CHECKED)
        f = _Fixture(self.container, 1, seen.append)
        self._tap(f, 1, check=False)  # LVGL would un-check on the tap
        self.assertEqual(seen, ["oink"])
        self.assertTrue(self.cbs[1].has_state(lv.STATE.CHECKED))
        self.assertEqual(f.active_radio_index, 1)

    def test_allow_deselect_uncheck_does_not_fire(self):
        seen = []
        self.cbs[1].add_state(lv.STATE.CHECKED)
        f = _Fixture(self.container, 1, seen.append, allow_deselect=True)
        self._tap(f, 1, check=False)
        self.assertEqual(seen, [])
        self.assertEqual(f.active_radio_index, -1)

    def test_callback_exception_is_swallowed(self):
        def boom(v):
            raise RuntimeError("preview failed")
        f = _Fixture(self.container, -1, boom)
        self._tap(f, 2, check=True)  # must not raise
        self.assertEqual(f.active_radio_index, 2)

    def test_no_callback_attribute_is_fine(self):
        f = _Fixture(self.container, -1)  # no _selected_callback / _ui_options
        self._tap(f, 0, check=True)
        self.assertEqual(f.active_radio_index, 0)


if __name__ == "__main__":
    unittest.main()
