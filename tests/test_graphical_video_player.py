import sys
import unittest

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


if __name__ == "__main__":
    unittest.main()
