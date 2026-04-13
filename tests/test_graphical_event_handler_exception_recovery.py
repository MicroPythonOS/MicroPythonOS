"""
Test that LVGL event callback exceptions do not prevent other callbacks from working.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_event_handler_exception_recovery.py
    Device:  ./tests/unittest.sh tests/test_graphical_event_handler_exception_recovery.py --ondevice
"""

import time
import unittest

import lvgl as lv
from mpos import wait_for_render
from mpos.ui.testing import click_button


class TestGraphicalEventHandlerExceptionRecovery(unittest.TestCase):
    """Graphical test for event handler exception recovery."""

    def setUp(self):
        self.screen = lv.obj()
        self.screen.set_size(320, 240)
        lv.screen_load(self.screen)
        wait_for_render(5)

    def tearDown(self):
        lv.screen_load(lv.obj())
        wait_for_render(5)

    def test_event_handler_exception_recovery(self):
        good_clicked = {"count": 0}

        def bad_click_cb(event):
            # Intentional failure to validate event-dispatch recovery.
            raise ValueError("bad button click failure")

        def good_click_cb(event):
            good_clicked["count"] += 1

        bad_button = lv.button(self.screen)
        bad_button.set_size(120, 50)
        bad_button.align(lv.ALIGN.TOP_MID, 0, 20)
        bad_label = lv.label(bad_button)
        bad_label.set_text("Bad")

        good_button = lv.button(self.screen)
        good_button.set_size(120, 50)
        good_button.align(lv.ALIGN.TOP_MID, 0, 90)
        good_label = lv.label(good_button)
        good_label.set_text("Good")

        bad_button.add_event_cb(bad_click_cb, lv.EVENT.CLICKED, None)
        good_button.add_event_cb(good_click_cb, lv.EVENT.CLICKED, None)

        wait_for_render(10)

        self.assertTrue(click_button("Bad"), "Bad button not found/clicked")
        time.sleep(0.05)
        lv.task_handler()  # flush event loop after the failing callback

        self.assertTrue(click_button("Good"), "Good button not found/clicked")
        time.sleep(0.05)
        lv.task_handler()  # ensure good callback is processed after the failure

        self.assertTrue(
            good_clicked["count"] > 0,
            "Good button callback did not run after bad button exception",
        )
