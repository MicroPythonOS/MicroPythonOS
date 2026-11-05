"""
Test that Sorter launches and exits without errors.

Usage:
"""

import time
import unittest

from mpos import AppManager, wait_for_render
from mpos.ui.testing import wait_for_text


class TestSorterLaunch(unittest.TestCase):
    """Verify Sorter starts up and shows its UI."""

    def setUp(self):
        AppManager.restart_launcher()
        wait_for_render(10)

    def tearDown(self):
        try:
            from mpos import ui

            ui.back_screen()
            wait_for_render(5)
        except Exception:
            pass

    def test_app_launches(self):
        """Sorter should return promptly and render the level label."""
        started = time.ticks_ms()
        result = AppManager.start_app("com.micropythonos.sorter")
        elapsed = time.ticks_diff(time.ticks_ms(), started)
        self.assertTrue(result, "Sorter should start")
        self.assertTrue(
            elapsed < 10000,
            "Sorter launch blocked the event loop for %s ms" % elapsed,
        )

        self.assertTrue(wait_for_text("Level: 1", timeout=60), "Level label should appear")


if __name__ == "__main__":
    unittest.main()
