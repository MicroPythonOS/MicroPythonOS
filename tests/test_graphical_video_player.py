import sys
import time
import unittest

import lvgl as lv

from mpos import AppManager
from mpos.ui.view import screen_stack

sys.path.insert(0, "apps/com.micropythonos.video_player")

import video_player


class TestVideoPlayer(unittest.TestCase):
    def test_compute_stats(self):
        stats = video_player.compute_stats([10] * 100)
        self.assertEqual(stats["frames"], 100)
        self.assertEqual(stats["avg_ms"], 10.0)
        self.assertEqual(stats["fps"], 100.0)
        self.assertEqual(stats["p95_ms"], 10)

    def test_make_frame_rgb565_sizes(self):
        full = video_player.make_frame_rgb565(320, 240, 0)
        self.assertEqual(len(full), 320 * 240 * 2)
        half = video_player.make_frame_rgb565(160, 120, 1)
        self.assertEqual(len(half), 160 * 120 * 2)
        self.assertTrue(full[:64] != half[:64] or len(full) != len(half))

    def test_app_starts_and_registers_sysmon_cb(self):
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player"))
        # Launching without a clip puts the file picker on top of the player, so
        # the title is on the player's own screen, not necessarily the active one.
        activity = None
        for entry in screen_stack:
            # The entrypoint is re-imported per launch, so match by shape.
            if hasattr(entry[0], "title_label"):
                activity = entry[0]
        self.assertIsNotNone(activity, "the player activity is not on the stack")
        self.assertEqual(activity.title_label.get_text(), "Video Player")

    def test_sysmon_echo_is_time_bounded_but_the_label_keeps_updating(self):
        activity = self.player_activity()
        self.assertIsNotNone(activity)
        activity._sysmon_log_deadline = time.ticks_add(time.ticks_ms(), 4000)
        self.assertTrue(activity._echo_sysmon())
        # Past the window: no console echo (it floods mpremote), but the overlay
        # must still show the latest value.
        activity._sysmon_log_deadline = time.ticks_add(time.ticks_ms(), -1000)
        self.assertFalse(activity._echo_sysmon())
        activity._sysmon_cb(20, "I sysmon: 27 FPS")
        self.assertEqual(activity.fps_label.get_text(), "sysmon: 27 FPS")
        self.assertEqual(activity._sysmon_samples[-1], 27)

    def player_activity(self):
        for entry in screen_stack:
            if hasattr(entry[0], "title_label"):
                return entry[0]
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player"))
        for entry in screen_stack:
            if hasattr(entry[0], "title_label"):
                return entry[0]
        return None

    def test_pause_control_accepts_the_event_argument(self):
        # _make_control wraps callbacks as action(event); passing the bound
        # _toggle_pause straight in used to raise TypeError when clicked.
        activity = self.player_activity()
        self.assertIsNotNone(activity, "the player activity is not on the stack")
        label = activity._make_control(lv.screen_active(), "x",
                                       activity._toggle_pause, 0)
        button = label.get_parent()
        try:
            button.send_event(lv.EVENT.CLICKED, None)
        finally:
            button.delete()

    def test_back_gesture_defers_the_exit(self):
        # A real back gesture is dispatched inside the pump's LVGL pass; the
        # activity must consume it and defer the teardown out of that callback.
        activity = self.player_activity()
        self.assertIsNotNone(activity, "the player activity is not on the stack")
        deferred = []
        original_defer = activity._defer
        activity._defer = lambda func: deferred.append(func)
        activity._exit_requested = False
        try:
            self.assertTrue(activity.onBackPressed(None))
            self.assertTrue(activity._exit_requested)
            self.assertEqual(deferred, [activity._finish_now])
        finally:
            activity._defer = original_defer
            activity._exit_requested = False


if __name__ == "__main__":
    unittest.main()
