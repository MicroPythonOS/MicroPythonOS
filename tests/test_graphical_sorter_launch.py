"""
Test that Sorter launches and exits without errors.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_sorter_launch.py
    Device:  ./tests/unittest.sh tests/test_graphical_sorter_launch.py --ondevice
"""

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
        """Sorter should render the level label after launch."""
        result = AppManager.start_app("com.micropythonos.sorter")
        self.assertTrue(result, "Sorter should start")

        self.assertTrue(wait_for_text("Level: 1", timeout=15), "Level label should appear")


if __name__ == "__main__":
    unittest.main()
