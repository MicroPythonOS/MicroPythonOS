"""Reproduce the MeshCore font crash on the emulator (manual test).

Needs the real MeshCore app installed in apps/org.fri3d.meshcore
(download from BadgeHub). Launches the app, opens the Public channel,
goes back, and opens it again — the exact flow that crashed on the
badge with #248. With the #248 behavior the second open draws with a
destroyed font: the process crashes, or the final cache assert fails.
With the fix the flow completes.

Usage:
    uv run scripts/test_runner.py tests/manual_test_meshcore_font_reentry.py
"""

import unittest

import mpos.ui
from mpos import AppManager, FontManager, wait_for_render


class TestMeshCoreChannelReentry(unittest.TestCase):

    def tearDown(self):
        for _ in range(10):
            if len(mpos.ui.screen_stack) <= 1:
                break
            mpos.ui.back_screen()
            wait_for_render(5)

    def test_channel_reenter_does_not_crash(self):
        self.assertTrue(AppManager.start_app("org.fri3d.meshcore"),
                        "MeshCore failed to launch — is it installed in apps/?")
        wait_for_render(10)
        home = mpos.ui.screen_stack[-1][0]
        self.assertEqual(type(home).__name__, "MeshCoreHome")

        # Open the Public channel, like a tap on its row.
        home._open_channel("Public")
        wait_for_render(10)
        self.assertEqual(
            type(mpos.ui.screen_stack[-1][0]).__name__, "ChannelChatActivity")
        # The chat screen must use the real TTF, not the Montserrat fallback.
        self.assertEqual(len(FontManager._ttf_font_cache), 1,
                         "Archivo Narrow did not load; test proves nothing")

        # Back to the home screen. MeshCore still runs.
        mpos.ui.back_screen()
        wait_for_render(10)

        # Open the channel again. MeshCore applies the font it kept in its
        # module global. With #248 that font was destroyed on the back
        # navigation, and this render reads freed memory.
        home._open_channel("Public")
        wait_for_render(30)
        self.assertEqual(
            type(mpos.ui.screen_stack[-1][0]).__name__, "ChannelChatActivity")

        # The held font must stay cached while the app runs.
        self.assertEqual(len(FontManager._ttf_font_cache), 1)


if __name__ == "__main__":
    unittest.main()
