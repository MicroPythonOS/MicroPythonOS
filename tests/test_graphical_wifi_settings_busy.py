"""
Graphical tests for the Wi-Fi settings app while another Wi-Fi operation holds
WifiService's busy flag (the boot auto-connect, ConnectivityManager's
reconnect, a scan).

Usage:
"""

import _thread
import unittest

import lvgl as lv
import mpos.ui
from mpos import (
    AppManager,
    WifiService,
    click_button,
    verify_text_present,
    wait_for_render,
    wait_for_widget,
)
from mpos.ui.view import screen_stack


class TestGraphicalWifiSettingsBusy(unittest.TestCase):
    """Connect and Rescan in the Wi-Fi app respect WifiService's busy flag."""

    def setUp(self):
        self.original_scan_networks = WifiService.scan_networks
        self.original_connected_ssid = WifiService._desktop_connected_ssid
        self.assertTrue(
            wait_for_widget(lambda: not WifiService.is_busy(), timeout=10),
            "Another Wi-Fi operation is still running",
        )
        self.assertTrue(AppManager.start_app("com.micropythonos.settings.wifi"))
        self.activity = screen_stack[-1][0]
        self.assertEqual(type(self.activity).__name__, "WiFiSettings")
        # Let the scan started by onResume finish so it cannot race the test.
        self.assertTrue(
            wait_for_widget(
                lambda: not self.activity.busy_scanning and self.activity.scanned_ssids,
                timeout=10,
            ),
            "Initial scan did not finish",
        )
        wait_for_render(10)

    def tearDown(self):
        WifiService.scan_networks = self.original_scan_networks
        WifiService._desktop_connected_ssid = self.original_connected_ssid
        WifiService.wifi_busy = False
        try:
            mpos.ui.back_screen()
        except Exception:
            pass

    def _assert_busy_message_shown(self):
        error_label = self.activity.error_label
        self.assertFalse(error_label.has_flag(lv.obj.FLAG.HIDDEN), "Error label is hidden")
        self.assertIn("busy", error_label.get_text().lower())

    def _assert_scan_button_ready(self):
        self.assertFalse(self.activity.scan_button.has_state(lv.STATE.DISABLED))
        self.assertEqual(
            self.activity.scan_button_label.get_text(), self.activity.scan_button_scan_text
        )

    @unittest.skipIf(
        not WifiService._is_desktop_mode(None),
        "Uses the simulated desktop connect; on a device it would join a real network",
    )
    def test_connect_holds_wifi_busy_while_connecting(self):
        """The app's connect claims the busy flag, so a reconnect tick backs off."""
        done = []

        def connect():
            self.activity.attempt_connecting_thread("Office", "password")
            done.append(True)

        _thread.start_new_thread(connect, ())

        self.assertTrue(
            wait_for_widget(lambda: WifiService.is_busy(), timeout=2),
            "wifi_busy was not set while the app was connecting",
        )
        self.assertTrue(wait_for_widget(lambda: done, timeout=10), "Connect did not finish")
        wait_for_render(10)

        self.assertFalse(WifiService.is_busy())
        self.assertEqual(self.activity.last_tried_ssid, "Office")
        self.assertEqual(self.activity.last_tried_result, "connected")
        self._assert_scan_button_ready()

    def test_connect_while_busy_shows_busy_and_does_not_connect(self):
        """Connect while another operation holds the flag reports busy, not timeout."""
        WifiService.wifi_busy = True

        self.activity.attempt_connecting_thread("Office", "password")
        wait_for_render(10)

        self._assert_busy_message_shown()
        self.assertIsNone(WifiService.get_current_ssid())
        self.assertNotEqual(self.activity.last_tried_ssid, "Office")
        self.assertTrue(WifiService.wifi_busy, "Must not release a flag another operation holds")
        self.assertFalse(self.activity.busy_connecting)
        self._assert_scan_button_ready()

    def test_rescan_while_busy_keeps_list_and_shows_busy(self):
        """Rescan while busy keeps the networks on screen and says why."""
        previous = list(self.activity.scanned_ssids)
        WifiService.scan_networks = lambda network_module=None: None

        self.assertTrue(click_button("Rescan"), "Could not find Rescan button")
        self.assertTrue(
            wait_for_widget(lambda: not self.activity.busy_scanning, timeout=10),
            "Rescan did not finish",
        )
        wait_for_render(10)

        self.assertEqual(self.activity.scanned_ssids, previous)
        for ssid in previous:
            self.assertTrue(
                verify_text_present(lv.screen_active(), ssid),
                "Network '%s' disappeared from the list" % ssid,
            )
        self._assert_busy_message_shown()
        self._assert_scan_button_ready()


if __name__ == "__main__":
    pass
