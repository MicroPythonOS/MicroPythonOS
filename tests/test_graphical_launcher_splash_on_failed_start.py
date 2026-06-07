"""
Graphical regression test for launcher splash recovery.

When launching an app, the launcher briefly switches to splash mode
(single centered icon). If app startup fails, the launcher must clear
that splash state and return to the normal icon grid.
"""

import unittest

import mpos.ui

from mpos import AppManager
from mpos.ui.testing import verify_text_on_any_layer, wait_for_render, wait_for_widget
from mpos.ui.view import close_top_layer_msgboxes


def _go_back_to_launcher(max_steps=6):
    for _ in range(max_steps):
        if len(mpos.ui.screen_stack) <= 1:
            return
        mpos.ui.back_screen()
        wait_for_render(10)


class TestLauncherSplashRecovery(unittest.TestCase):
    def setUp(self):
        AppManager.restart_launcher()
        wait_for_render(20)
        _go_back_to_launcher()

    def tearDown(self):
        close_top_layer_msgboxes()
        wait_for_render(10)
        _go_back_to_launcher()

    def _assert_failed_launch_recovers_launcher(
        self,
        fullname,
        expected_dialog_text,
        expect_activity_push=False,
    ):
        launcher = mpos.ui.screen_stack[-1][0]
        self.assertIsNotNone(launcher, "Launcher activity should exist")
        self.assertIsNone(
            launcher._splash_fullname,
            "Launcher should not start in splash mode",
        )

        launcher._launch_app(fullname)

        dialog_visible = wait_for_widget(
            lambda: True if verify_text_on_any_layer(expected_dialog_text) else None,
            timeout=8,
            interval=0.1,
        )
        self.assertTrue(dialog_visible, "Expected failure dialog after failed start")

        wait_for_render(20)

        if expect_activity_push:
            self.assertGreaterEqual(
                len(mpos.ui.screen_stack),
                2,
                "Lifecycle-failing app should push an activity before failing",
            )
            self.assertIsNot(
                mpos.ui.screen_stack[-1][0],
                launcher,
                "A launched app activity should be foreground before navigating back",
            )
            mpos.ui.back_screen()
            wait_for_render(15)

        self.assertEqual(
            len(mpos.ui.screen_stack),
            1,
            "Launcher should be the only remaining activity after failure handling",
        )
        self.assertIs(
            mpos.ui.screen_stack[-1][0],
            launcher,
            "Launcher should be foreground after failed app launch handling",
        )
        self.assertIsNone(
            launcher._splash_fullname,
            "Launcher splash state should be cleared after failed app launch",
        )

    def test_failed_app_start_clears_splash_mode(self):
        self._assert_failed_launch_recovers_launcher(
            "com.micropythonos.errortest",
            "Could not load app",
        )

    def test_lifecycle_failure_clears_splash_mode(self):
        self._assert_failed_launch_recovers_launcher(
            "com.micropythonos.errortest_resume",
            "threw an exception",
            expect_activity_push=True,
        )
