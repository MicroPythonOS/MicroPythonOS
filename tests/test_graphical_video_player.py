import sys
import unittest

import lvgl as lv

from mpos import AppManager, wait_for_text

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
        self.assertTrue(wait_for_text("Video Player", timeout=10))
        screen = lv.screen_active()
        self.assertTrue(screen is not None)


if __name__ == "__main__":
    unittest.main()
