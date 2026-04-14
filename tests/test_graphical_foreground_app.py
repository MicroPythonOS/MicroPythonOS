"""
Graphical test to verify get_foreground_app returns the active app.
"""

import time
import unittest

from mpos import AppManager
from mpos.ui import get_foreground_app
from mpos.ui.testing import wait_for_render


class TestForegroundApp(unittest.TestCase):
    """Ensure get_foreground_app tracks the top activity in the UI stack."""

    def _wait_for_foreground(self, expected, timeout_ms=2500):
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            fg = get_foreground_app()
            if fg == expected:
                return True
            wait_for_render(iterations=10)
        return False

    def test_get_foreground_app_after_starting_apps(self):
        launcher_fullname = "com.micropythonos.launcher"
        about_fullname = "com.micropythonos.about"

        AppManager.start_app(launcher_fullname)
        wait_for_render(iterations=30)
        self.assertTrue(
            self._wait_for_foreground(launcher_fullname),
            f"Expected foreground app to be {launcher_fullname}, got {get_foreground_app()}",
        )

        AppManager.start_app(about_fullname)
        wait_for_render(iterations=30)
        self.assertTrue(
            self._wait_for_foreground(about_fullname),
            f"Expected foreground app to be {about_fullname}, got {get_foreground_app()}",
        )

        fg = get_foreground_app()
        self.assertIsNotNone(fg, "Foreground app should not be None after start_app")
        self.assertEqual(
            fg,
            about_fullname,
            f"Foreground app mismatch: expected {about_fullname}, got {fg}",
        )
