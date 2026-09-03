"""
Graphical test for the Camera activity's "open app link" QR chip.

The chip appears when a decoded QR (in free-scan mode) is an official store
link or matches a registered urlPattern handler, and dispatches through
mpos.content.deeplink when tapped.

CameraActivity.onCreate builds the whole UI without touching camera
hardware (that happens in onResume), so these tests exercise the chip flow
headlessly by driving the decode-result path directly.
"""

import unittest

import lvgl as lv

from mpos import AppManager, Intent
from mpos.content import deeplink
from mpos.ui.camera_activity import CameraActivity
from mpos.ui.testing import wait_for_render

STORE_LINK = "https://badgehub.eu/page/project/com.micropythonos.helloworld"


class TestGraphicalCameraQRChip(unittest.TestCase):

    def setUp(self):
        self.activity = CameraActivity()
        self.activity.intent = Intent(activity_class=CameraActivity)
        self.activity.appFullName = "com.micropythonos.camera"
        self.activity.onCreate()
        wait_for_render(iterations=10)

    def tearDown(self):
        try:
            from mpos.ui import back_screen
            back_screen()
            wait_for_render(iterations=5)
        except Exception:
            pass

    def test_chip_hidden_initially(self):
        self.assertTrue(self.activity.open_link_button.has_flag(lv.obj.FLAG.HIDDEN))

    def test_store_link_shows_appstore_chip(self):
        self.activity._maybe_offer_open_link(STORE_LINK)
        wait_for_render(iterations=5)
        self.assertFalse(self.activity.open_link_button.has_flag(lv.obj.FLAG.HIDDEN))
        self.assertEqual(self.activity.open_link_label.get_text(), "Open in App Store")

    def test_garbage_keeps_chip_hidden(self):
        self.activity._maybe_offer_open_link(STORE_LINK)
        self.activity._maybe_offer_open_link("WIFI:T:WPA;S:x;P:y;;")
        wait_for_render(iterations=5)
        self.assertTrue(self.activity.open_link_button.has_flag(lv.obj.FLAG.HIDDEN))

    def test_rescan_hides_chip(self):
        self.activity._maybe_offer_open_link(STORE_LINK)
        # Starting a new QR scan must clear the stale chip. start_qr_decoding
        # also restarts the camera, which doesn't exist headless — the chip
        # reset happens before any camera access.
        try:
            self.activity.start_qr_decoding()
        except Exception:
            pass
        self.assertTrue(self.activity.open_link_button.has_flag(lv.obj.FLAG.HIDDEN))
        self.assertIsNone(self.activity._last_qr_text)

    def test_chip_click_dispatches_open_url(self):
        opened = []
        saved = deeplink.open_url
        deeplink.open_url = lambda text: opened.append(text) or True
        try:
            self.activity._maybe_offer_open_link(STORE_LINK)
            self.activity._open_link_click(None)
        finally:
            deeplink.open_url = saved
        self.assertEqual(opened, [STORE_LINK])

    def test_appstore_receives_deeplink_from_chip(self):
        """End-to-end: chip click starts the AppStore with the right extras."""
        started = []
        saved = AppManager.start_app

        def fake_start_app(fullname, intent=None, result_callback=None):
            started.append((fullname, intent))
            return True
        AppManager.start_app = fake_start_app
        try:
            self.activity._maybe_offer_open_link(STORE_LINK)
            self.activity._open_link_click(None)
        finally:
            AppManager.start_app = saved
        self.assertEqual(len(started), 1)
        fullname, intent = started[0]
        self.assertEqual(fullname, deeplink.APPSTORE_FULLNAME)
        self.assertEqual(intent.extras.get("deeplink_fullname"), "com.micropythonos.helloworld")


if __name__ == "__main__":
    unittest.main()
