import sys
import unittest

import lvgl as lv

from mpos import InputManager
from mpos.board import usb_display
from mpos.ui.testing import GraphicalTestCase


class FakeDispMod:
    def __init__(self):
        self.idle_reset = True
        self.addrs = []

    def hid_poll(self):
        return False

    def hid_claimed_addrs(self):
        return list(self.addrs)

    def hid_start(self):
        return True

    def auto_reset_idle(self, *args):
        if not args:
            return self.idle_reset
        self.idle_reset = bool(args[0])


class FakePanel:
    display_width = 320
    display_height = 240


class FakeUSB:
    display_width = 640
    display_height = 480


class TestHIDWatchdogExclusion(unittest.TestCase):
    def setUp(self):
        self.fake = FakeDispMod()
        sys.modules["usb_disp"] = self.fake
        self.prev_idle = usb_display._hid_idle_prev
        usb_display._hid_idle_prev = None

    def tearDown(self):
        sys.modules.pop("usb_disp", None)
        usb_display._hid_idle_prev = self.prev_idle
        try:
            self.fake.auto_reset_idle(True)
        except Exception:
            pass

    def test_claimed_mouse_suppresses_idle_reset(self):
        usb_display._update_hid_watchdog_exclusion([10])
        self.assertFalse(self.fake.idle_reset)

    def test_unplug_restores_idle_reset(self):
        usb_display._update_hid_watchdog_exclusion([10])
        usb_display._update_hid_watchdog_exclusion([])
        self.assertTrue(self.fake.idle_reset)

    def test_manual_disable_is_not_forced_back_on(self):
        self.fake.idle_reset = False
        usb_display._update_hid_watchdog_exclusion([10])
        usb_display._update_hid_watchdog_exclusion([])
        self.assertFalse(self.fake.idle_reset)

    def test_no_claim_no_touch(self):
        usb_display._update_hid_watchdog_exclusion([])
        self.assertTrue(self.fake.idle_reset)
        self.assertIsNone(usb_display._hid_idle_prev)


class TestMouseSkipsTouchWrap(GraphicalTestCase):
    def test_wrap_leaves_absolute_mouse_alone(self):
        from drivers.indev.usb_hid import FakeHIDSource, USBMouse

        mouse = USBMouse(source=FakeHIDSource())
        self.addCleanup(mouse.delete)
        InputManager.register_indev(mouse)
        self.addCleanup(InputManager.unregister_indev, mouse)
        usb_display._wrap_all_touch(FakeUSB(), FakePanel())
        self.addCleanup(usb_display._unwrap_touch)
        self.assertTrue("_calc_coords" not in mouse.__dict__)
        self.assertEqual(mouse._calc_coords(7, 9), (7, 9))
        _ = lv  # silence unused import if helpers change
