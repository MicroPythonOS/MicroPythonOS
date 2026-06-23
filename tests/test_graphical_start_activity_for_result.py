"""
Regression test for startActivityForResult navigation.

Verifies that a picker activity launched with startActivityForResult is
removed from the screen stack after it delivers a result, and that pressing
back from the caller returns to the previous activity (not the picker).
"""

import os
import time
import unittest

import lvgl as lv
import mpos.ui
from mpos import AppManager, Intent, wait_for_render
from mpos.ui.testing import wait_for_text


class TestGraphicalStartActivityForResult(unittest.TestCase):
    """Ensure startActivityForResult correctly pops the called activity."""

    def setUp(self):
        """Return to launcher so each test starts from a known stack state."""
        for _ in range(10):
            if len(mpos.ui.screen_stack) <= 1:
                break
            mpos.ui.back_screen()
            wait_for_render(5)

    def tearDown(self):
        """Clean up by returning to the launcher."""
        for _ in range(10):
            if len(mpos.ui.screen_stack) <= 1:
                break
            mpos.ui.back_screen()
            wait_for_render(5)

    def _stack_names(self):
        return [
            (type(a).__name__, a.appFullName)
            for a, _, _, _ in mpos.ui.screen_stack
        ]

    def _start_imageview(self):
        result = AppManager.start_app("com.micropythonos.imageview")
        self.assertTrue(result, "ImageView failed to launch")
        wait_for_render(10)
        stack = self._stack_names()
        self.assertGreaterEqual(len(stack), 2, "Expected launcher + imageview on stack")
        self.assertEqual(stack[-1], ("ImageView", "com.micropythonos.imageview"))
        self.assertEqual(stack[0], ("Launcher", "com.micropythonos.launcher"))

    def test_picker_is_removed_after_result(self):
        """FileExplorer started for result must be popped after delivering a result."""
        self._start_imageview()

        imageview = mpos.ui.screen_stack[-1][0]
        imageview._open_file_clicked(None)
        wait_for_render(10)

        self.assertEqual(
            self._stack_names(),
            [
                ("Launcher", "com.micropythonos.launcher"),
                ("ImageView", "com.micropythonos.imageview"),
                ("FileExplorerActivity", "com.micropythonos.imageview"),
            ],
        )

        # Find a real file in the picker and confirm the selection.
        file_explorer = mpos.ui.screen_stack[-1][0]
        file_explorer._confirm_pick()
        wait_for_render(10)

        self.assertEqual(
            self._stack_names(),
            [
                ("Launcher", "com.micropythonos.launcher"),
                ("ImageView", "com.micropythonos.imageview"),
            ],
            "FileExplorerActivity was not removed from the stack after result",
        )

    def test_back_from_caller_returns_past_picker(self):
        """After a picker result, back from the caller must skip the picker."""
        self._start_imageview()

        imageview = mpos.ui.screen_stack[-1][0]
        imageview._open_file_clicked(None)
        wait_for_render(10)

        file_explorer = mpos.ui.screen_stack[-1][0]
        file_explorer._confirm_pick()
        wait_for_render(10)

        mpos.ui.back_screen()
        wait_for_render(10)

        self.assertEqual(
            self._stack_names(),
            [("Launcher", "com.micropythonos.launcher")],
            "Back from caller did not return to launcher; picker may still be on stack",
        )

    def test_back_from_picker_delivers_cancel_result(self):
        """Backing out of a picker must deliver a cancel result and pop the picker."""
        self._start_imageview()

        imageview = mpos.ui.screen_stack[-1][0]
        received = []

        def _capture(result):
            received.append(result)
            imageview._on_file_picked(result)

        imageview.startActivityForResult(
            Intent(
                action="pick_file",
                extras={"start_dir": "data/images", "path_pattern": [".jpg"]},
            ),
            _capture,
        )
        wait_for_render(10)

        self.assertEqual(
            self._stack_names()[-1],
            ("FileExplorerActivity", "com.micropythonos.imageview"),
        )

        # Simulate the hardware back gesture from the picker.
        mpos.ui.back_screen()
        wait_for_render(10)

        self.assertEqual(
            self._stack_names(),
            [
                ("Launcher", "com.micropythonos.launcher"),
                ("ImageView", "com.micropythonos.imageview"),
            ],
            "FileExplorerActivity was not popped after back from picker",
        )
        self.assertEqual(len(received), 1)
        self.assertFalse(received[0]["result_code"])

    def test_pick_file_action_defaults_to_picker_mode(self):
        """A pick_file intent without an explicit mode must still open the picker."""
        self._start_imageview()

        imageview = mpos.ui.screen_stack[-1][0]
        imageview.startActivityForResult(
            Intent(action="pick_file", extras={"start_dir": "data/images"}),
            imageview._on_file_picked,
        )
        wait_for_render(10)

        file_explorer = mpos.ui.screen_stack[-1][0]
        self.assertEqual(file_explorer._mode, file_explorer.MODE_PICK)


if __name__ == "__main__":
    unittest.main()
