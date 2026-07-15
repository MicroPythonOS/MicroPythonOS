"""Graphical capture of the TFL Player About modal (dev iteration helper).

Starts the app, opens the About modal via the running activity, and writes a
raw RGB565 screenshot to tests/screenshots/tfl_about.raw for visual iteration.

"""

import unittest
import lvgl as lv
import mpos.ui
from mpos import (
    AppManager,
    DisplayMetrics,
    capture_screenshot,
    wait_for_render,
    find_label_with_text,
)
from mpos.ui.view import screen_stack


class TestTFLAbout(unittest.TestCase):
    def test_capture_about_modal(self):
        ok = AppManager.start_app("com.micropythonos.thefreelanternplayer")
        self.assertTrue(ok, "failed to start app")
        wait_for_render(60)

        self.assertTrue(len(screen_stack) > 0, "no activity on stack")
        activity = screen_stack[-1][0]
        self.assertTrue(
            hasattr(activity, "show_about"),
            "top activity has no show_about: got %r" % (type(activity),),
        )
        activity.show_about()
        wait_for_render(60)

        # Regression guard: the About modal must actually render (it previously
        # failed to display on repeat opens due to stale stacked modals).
        screen = lv.screen_active()
        self.assertIsNotNone(
            find_label_with_text(screen, "The Free Lantern Player"),
            "About modal did not render (title label not found on screen)",
        )

        w, h = DisplayMetrics.width(), DisplayMetrics.height()
        path = "../tests/screenshots/tfl_about.raw"
        capture_screenshot(path, width=w, height=h)
        print("SCREENSHOT_WRITTEN %s %dx%d" % (path, w, h))
