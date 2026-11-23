"""The launch message must be painted while the start-up blocks.

``Doom._loading()`` is the only thing on screen for the seconds the WAD takes
to inflate, and it repaints by hand because the frame loop is not running yet.
The display binding's ``refr_now()`` takes the display as an argument; the
no-argument form raises ``TypeError`` on a badge, and the old
``except Exception: pass`` hid it, so nothing was painted until the engine's
first frame - the launch looked frozen on the launcher's splash.

Laying the label out is what the repaint buys us, so that is what this pins:
without a refresh, a freshly created label reports a zero size.
"""

import sys
import unittest

import lvgl as lv

from mpos.ui.native_activity import NativeActivity

APP_DIR = "apps/com.micropythonos.doom"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import doom  # noqa: E402


class _StubActivity(NativeActivity):

    def make_engine(self):
        return None


class TestLoadingMessage(unittest.TestCase):

    def setUp(self):
        self.screen = lv.obj()
        self.screen.set_size(240, 320)
        # The repaint refreshes the display's active screen, which is what a
        # real launch has; an off-screen object is never laid out.
        lv.screen_load(self.screen)
        self.activity = _StubActivity()
        self.activity.screen = self.screen
        self.activity.hint = None
        self.activity._rotated = True

    def tearDown(self):
        self.activity._clear_hint()
        # The loaded screen must not be deleted while it is still displayed.
        lv.screen_load(lv.obj())
        self.screen.delete()

    def test_the_launch_message_is_laid_out_for_the_panel(self):
        doom.Doom._loading(self.activity, "Unpacking WAD", 50, 100)
        label = self.activity.hint
        self.assertIsNotNone(label)
        self.assertEqual(label.get_text(), "Unpacking WAD 50%")
        self.assertTrue(label.get_width() > 0, "the message was never laid out")
        self.assertTrue(label.get_height() > 0, "the message was never laid out")

    def test_a_percentage_is_only_shown_when_it_is_known(self):
        doom.Doom._loading(self.activity, "Checking the Doom engine")
        self.assertEqual(
            self.activity.hint.get_text(), "Checking the Doom engine")
        doom.Doom._loading(self.activity, "Unpacking WAD", 0, 100)
        self.assertEqual(self.activity.hint.get_text(), "Unpacking WAD 0%")
