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
        self.hid_states = []
        self.parked_entries = []

    def hid_poll(self):
        return False

    def hid_claimed_addrs(self):
        return list(self.addrs)

    def hid_state(self):
        return list(self.hid_states)

    def hid_parked(self):
        return list(self.parked_entries)

    def hid_start(self):
        return True

    def auto_reset_idle(self, *args):
        if not args:
            return self.idle_reset
        self.idle_reset = bool(args[0])


class LegacyFakeDispMod:
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

    def test_parked_entries_read(self):
        self.fake.parked_entries = [(0x046D, 0xC31C, "keyboard", 255)]
        self.assertEqual(
            usb_display._hid_parked_entries(), [(0x046D, 0xC31C, "keyboard", 255)]
        )

    def test_parked_suppresses_idle_reset(self):
        usb_display._update_hid_watchdog_exclusion([(0x046D, 0xC31C, "keyboard", 255)])
        self.assertFalse(self.fake.idle_reset)
        usb_display._update_hid_watchdog_exclusion([])
        self.assertTrue(self.fake.idle_reset)

    def test_poll_hid_wires_parked_to_suppression(self):
        self.fake.addrs = []
        self.fake.hid_states = []
        self.fake.parked_entries = [(0x046D, 0xC31C, "keyboard", 255)]
        usb_display._poll_hid()
        self.assertFalse(self.fake.idle_reset)
        self.fake.parked_entries = []
        usb_display._poll_hid()
        self.assertTrue(self.fake.idle_reset)


class TestSyncUSBHID(GraphicalTestCase):
    def setUp(self):
        super().setUp()
        self.fake = FakeDispMod()
        sys.modules["usb_disp"] = self.fake
        self.prev = (usb_display._usb_mouse, usb_display._usb_keyboard, usb_display._hid_hub)
        usb_display._usb_mouse = None
        usb_display._usb_keyboard = None
        usb_display._hid_hub = None

    def tearDown(self):
        sys.modules.pop("usb_disp", None)
        for dev in (usb_display._usb_mouse, usb_display._usb_keyboard):
            if dev is None:
                continue
            try:
                InputManager.unregister_indev(dev)
            except Exception:
                pass
            try:
                dev.delete()
            except Exception:
                pass
        usb_display._usb_mouse, usb_display._usb_keyboard, usb_display._hid_hub = self.prev

    def _armed_with_recorders(self):
        self.fake.addrs = [5, 6]
        usb_display._sync_usb_hid([5, 6])
        mouse = usb_display._usb_mouse
        kbd = usb_display._usb_keyboard
        self.assertIsNotNone(mouse)
        self.assertIsNotNone(kbd)
        mouse_calls = []
        kbd_calls = []
        orig_mouse_enable = mouse.enable
        orig_kbd_enable = kbd.enable

        def mouse_rec(en):
            mouse_calls.append(bool(en))
            return orig_mouse_enable(en)

        def kbd_rec(en):
            kbd_calls.append(bool(en))
            return orig_kbd_enable(en)

        mouse.enable = mouse_rec
        kbd.enable = kbd_rec
        return mouse, kbd, mouse_calls, kbd_calls

    def test_mouse_only_state(self):
        mouse, kbd, mouse_calls, kbd_calls = self._armed_with_recorders()
        self.fake.hid_states = [(6, "mouse", 0x17EF, 0x608D)]
        usb_display._sync_usb_hid([6])
        self.assertEqual(mouse_calls, [True])
        self.assertEqual(kbd_calls, [False])
        self.assertFalse(mouse._cursor.has_flag(lv.obj.FLAG.HIDDEN))

    def test_keyboard_only_state(self):
        mouse, kbd, mouse_calls, kbd_calls = self._armed_with_recorders()
        self.fake.hid_states = [(5, "keyboard", 0x046D, 0xC31C)]
        usb_display._sync_usb_hid([5])
        self.assertEqual(mouse_calls, [False])
        self.assertEqual(kbd_calls, [True])
        self.assertTrue(mouse._cursor.has_flag(lv.obj.FLAG.HIDDEN))

    def test_empty_state_disables_both(self):
        mouse, kbd, mouse_calls, kbd_calls = self._armed_with_recorders()
        self.fake.hid_states = []
        self.fake.addrs = []
        usb_display._sync_usb_hid([])
        self.assertEqual(mouse_calls, [False])
        self.assertEqual(kbd_calls, [False])
        self.assertTrue(mouse._cursor.has_flag(lv.obj.FLAG.HIDDEN))

    def test_legacy_module_follows_claimed(self):
        sys.modules["usb_disp"] = LegacyFakeDispMod()
        usb_display._usb_mouse = None
        usb_display._usb_keyboard = None
        usb_display._hid_hub = None
        usb_display._sync_usb_hid([6])
        self.assertIsNotNone(usb_display._usb_mouse)
        self.assertIsNotNone(usb_display._usb_keyboard)


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
