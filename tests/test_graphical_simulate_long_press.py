"""
Graphical test for the simulate_long_press() testing helper.

A long press must deliver LV_EVENT_LONG_PRESSED to the pressed widget,
which requires the simulated touch indev to keep reporting the pressed
state for the whole press duration. A short click must NOT deliver
LONG_PRESSED.
"""

import unittest

import lvgl as lv

from mpos import simulate_click, simulate_long_press, wait_for_render


class TestGraphicalSimulateLongPress(unittest.TestCase):

    def setUp(self):
        self.events = []
        self.screen = lv.obj()
        lv.screen_load(self.screen)

        self.button = lv.button(self.screen)
        self.button.set_size(120, 60)
        self.button.align(lv.ALIGN.CENTER, 0, 0)
        label = lv.label(self.button)
        label.set_text("Hold me")
        label.center()

        self.button.add_event_cb(
            lambda e: self.events.append("long_pressed"), lv.EVENT.LONG_PRESSED, None
        )
        self.button.add_event_cb(
            lambda e: self.events.append("short_clicked"), lv.EVENT.SHORT_CLICKED, None
        )
        wait_for_render()

    def _button_center(self):
        area = lv.area_t()
        self.button.get_coords(area)
        return (area.x1 + area.x2) // 2, (area.y1 + area.y2) // 2

    def test_long_press_fires_long_pressed(self):
        x, y = self._button_center()
        simulate_long_press(x, y)
        wait_for_render()
        self.assertTrue(
            "long_pressed" in self.events,
            "simulate_long_press did not deliver LONG_PRESSED, got: %s" % self.events,
        )

    def test_short_click_does_not_fire_long_pressed(self):
        x, y = self._button_center()
        simulate_click(x, y)
        wait_for_render()
        self.assertTrue(
            "long_pressed" not in self.events,
            "short click unexpectedly delivered LONG_PRESSED, got: %s" % self.events,
        )
        self.assertTrue(
            "short_clicked" in self.events,
            "short click did not deliver SHORT_CLICKED, got: %s" % self.events,
        )


if __name__ == "__main__":
    unittest.main()
