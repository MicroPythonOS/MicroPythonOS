"""Graphical integration test for the File Manager "Open With" flow.

Creates a temporary directory with sample files, opens the File Manager,
clicks files, and verifies that the right app is launched.
"""

import os
import shutil
import time
import unittest

import lvgl as lv
import mpos.ui
from mpos import (
    AppManager,
    click_label,
    wait_for_render,
    wait_for_text,
)
from mpos.activity_navigator import get_foreground_app


TEST_DIR = "openwith_test"


def _wait_ms(ms):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        lv.task_handler()
        time.sleep(0.01)


class TestGraphicalOpenWithFileManager(unittest.TestCase):

    def setUp(self):
        """Create a temporary directory with sample files."""
        self.test_path = TEST_DIR
        try:
            shutil.rmtree(self.test_path)
        except OSError:
            pass
        os.mkdir(self.test_path)
        for name in ("sample.wav", "sample.png", "sample.txt", "sample.rtttl"):
            with open("{}/{}".format(self.test_path, name), "wb") as f:
                f.write(b"dummy")

    def tearDown(self):
        """Go back to the launcher and remove the temporary files."""
        for _ in range(5):
            if len(mpos.ui.screen_stack) <= 1:
                break
            mpos.ui.back_screen()
            _wait_ms(300)
        try:
            shutil.rmtree(self.test_path)
        except OSError:
            pass

    def _start_file_manager(self):
        result = AppManager.start_app("com.micropythonos.file_manager")
        self.assertTrue(result, "File Manager failed to launch")
        self.assertTrue(
            wait_for_text(TEST_DIR, timeout=10),
            "Test directory not visible in File Manager",
        )
        click_label(TEST_DIR)
        self.assertTrue(
            wait_for_text("sample.wav", timeout=10),
            "Could not navigate into test directory",
        )

    def test_wav_file_opens_music_player(self):
        """Clicking a .wav file should launch the Music Player app."""
        self._start_file_manager()

        self.assertTrue(click_label("sample.wav"), "Could not click sample.wav")
        self.assertTrue(
            wait_for_text("Stop", timeout=10),
            "Music Player did not open",
        )
        self.assertEqual(
            get_foreground_app(),
            "com.micropythonos.musicplayer",
            "Foreground app is not Music Player",
        )

    def test_rtttl_file_opens_music_player_without_buzzer(self):
        """Clicking a .rtttl file should launch Music Player and report the missing buzzer output."""
        self._start_file_manager()

        self.assertTrue(click_label("sample.rtttl"), "Could not click sample.rtttl")
        self.assertTrue(
            wait_for_text("RTTTL requires a buzzer output", timeout=10),
            "Music Player did not show buzzer-required error",
        )
        self.assertEqual(
            get_foreground_app(),
            "com.micropythonos.musicplayer",
            "Foreground app is not Music Player",
        )

    def test_png_file_opens_image_view(self):
        """Clicking a .png file should launch the Image View app."""
        self._start_file_manager()

        self.assertTrue(click_label("sample.png"), "Could not click sample.png")
        self.assertTrue(
            wait_for_text("sample.png", timeout=10),
            "Image View did not open with the selected PNG file",
        )
        self.assertEqual(
            get_foreground_app(),
            "com.micropythonos.imageview",
            "Foreground app is not Image View",
        )

    def test_unknown_extension_falls_back_to_view_activity(self):
        """Clicking an unsupported file should fall back to ViewActivity."""
        self._start_file_manager()

        self.assertTrue(click_label("sample.txt"), "Could not click sample.txt")
        self.assertTrue(
            wait_for_text("sample.txt", timeout=10),
            "Fallback ViewActivity did not show the file path",
        )
        self.assertTrue(
            wait_for_text("dummy", timeout=10),
            "Fallback ViewActivity did not show the file contents",
        )


if __name__ == "__main__":
    unittest.main()
