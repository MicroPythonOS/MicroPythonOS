import sys
import unittest

import lvgl as lv

from mpos import InputManager
from mpos.usb import USBManager
from mpos.ui.testing import GraphicalTestCase


class FakeDisplayHandle:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def start(self):
        return None

    def poll(self):
        return False

    def ready(self):
        return False


class FakeUSBMod:
    Display = FakeDisplayHandle

    def __init__(self):
        self.idle_reset = True
        self.addrs = []
        self.hid_states = []
        self.parked_entries = []
        self.activated = False
        self.deactivated = False
        self._host_active = False

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

    def activate_host(self):
        self.activated = True
        self._host_active = True
        return True

    def deactivate_host(self):
        self.deactivated = True
        self._host_active = False
        return True

    def host_active(self):
        return self._host_active


class LegacyFakeUSBMod:
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
        self.fake = FakeUSBMod()
        sys.modules["usb"] = self.fake
        self.prev_idle = USBManager._hid_idle_prev
        USBManager._hid_idle_prev = None

    def tearDown(self):
        sys.modules.pop("usb", None)
        USBManager._hid_idle_prev = self.prev_idle
        try:
            self.fake.auto_reset_idle(True)
        except Exception:
            pass

    def test_claimed_only_leaves_idle_reset_alone(self):
        # Port-exact skip (C side) covers claimed devices; global
        # suppression is parked-only now.
        self.fake.addrs = [10]
        self.fake.parked_entries = []
        USBManager._update_hid_watchdog_exclusion()
        self.assertTrue(self.fake.idle_reset)
        self.assertIsNone(USBManager._hid_idle_prev)

    def test_unplug_restores_idle_reset(self):
        self.fake.parked_entries = [(0x046D, 0xC31C, "keyboard", 255)]
        USBManager._update_hid_watchdog_exclusion()
        self.fake.parked_entries = []
        USBManager._update_hid_watchdog_exclusion()
        self.assertTrue(self.fake.idle_reset)

    def test_manual_disable_is_not_forced_back_on(self):
        self.fake.idle_reset = False
        self.fake.parked_entries = [(0x046D, 0xC31C, "keyboard", 255)]
        USBManager._update_hid_watchdog_exclusion()
        self.fake.parked_entries = []
        USBManager._update_hid_watchdog_exclusion()
        self.assertFalse(self.fake.idle_reset)

    def test_no_parked_no_touch(self):
        self.fake.parked_entries = []
        USBManager._update_hid_watchdog_exclusion()
        self.assertTrue(self.fake.idle_reset)
        self.assertIsNone(USBManager._hid_idle_prev)

    def test_parked_entries_read(self):
        self.fake.parked_entries = [(0x046D, 0xC31C, "keyboard", 255)]
        self.assertEqual(
            USBManager._hid_parked_entries(), [(0x046D, 0xC31C, "keyboard", 255)]
        )

    def test_parked_suppresses_idle_reset(self):
        self.fake.parked_entries = [(0x046D, 0xC31C, "keyboard", 255)]
        USBManager._update_hid_watchdog_exclusion()
        self.assertFalse(self.fake.idle_reset)
        self.fake.parked_entries = []
        USBManager._update_hid_watchdog_exclusion()
        self.assertTrue(self.fake.idle_reset)

    def test_poll_hid_wires_parked_to_suppression(self):
        self.fake.addrs = []
        self.fake.hid_states = []
        self.fake.parked_entries = [(0x046D, 0xC31C, "keyboard", 255)]
        USBManager._poll_hid()
        self.assertFalse(self.fake.idle_reset)
        self.fake.parked_entries = []
        USBManager._poll_hid()
        self.assertTrue(self.fake.idle_reset)


class TestSyncUSBHID(GraphicalTestCase):
    def setUp(self):
        super().setUp()
        self.fake = FakeUSBMod()
        sys.modules["usb"] = self.fake
        self.prev = (USBManager._usb_mouse, USBManager._usb_keyboard, USBManager._hid_hub)
        USBManager._usb_mouse = None
        USBManager._usb_keyboard = None
        USBManager._hid_hub = None

    def tearDown(self):
        sys.modules.pop("usb", None)
        for dev in (USBManager._usb_mouse, USBManager._usb_keyboard):
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
        USBManager._usb_mouse, USBManager._usb_keyboard, USBManager._hid_hub = self.prev

    def _armed_with_recorders(self):
        self.fake.addrs = [5, 6]
        USBManager._sync_usb_hid([5, 6])
        mouse = USBManager._usb_mouse
        kbd = USBManager._usb_keyboard
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
        USBManager._sync_usb_hid([6])
        self.assertEqual(mouse_calls, [True])
        self.assertEqual(kbd_calls, [False])
        self.assertFalse(mouse._cursor.has_flag(lv.obj.FLAG.HIDDEN))

    def test_keyboard_only_state(self):
        mouse, kbd, mouse_calls, kbd_calls = self._armed_with_recorders()
        self.fake.hid_states = [(5, "keyboard", 0x046D, 0xC31C)]
        USBManager._sync_usb_hid([5])
        self.assertEqual(mouse_calls, [False])
        self.assertEqual(kbd_calls, [True])
        self.assertTrue(mouse._cursor.has_flag(lv.obj.FLAG.HIDDEN))

    def test_empty_state_disables_both(self):
        mouse, kbd, mouse_calls, kbd_calls = self._armed_with_recorders()
        self.fake.hid_states = []
        self.fake.addrs = []
        USBManager._sync_usb_hid([])
        self.assertEqual(mouse_calls, [False])
        self.assertEqual(kbd_calls, [False])
        self.assertTrue(mouse._cursor.has_flag(lv.obj.FLAG.HIDDEN))

    def test_legacy_module_follows_claimed(self):
        sys.modules["usb"] = LegacyFakeUSBMod()
        USBManager._usb_mouse = None
        USBManager._usb_keyboard = None
        USBManager._hid_hub = None
        USBManager._sync_usb_hid([6])
        self.assertIsNotNone(USBManager._usb_mouse)
        self.assertIsNotNone(USBManager._usb_keyboard)


class TestMouseSkipsTouchWrap(GraphicalTestCase):
    def test_wrap_leaves_absolute_mouse_alone(self):
        from drivers.indev.usb_hid import FakeHIDSource, USBMouse

        mouse = USBMouse(source=FakeHIDSource())
        self.addCleanup(mouse.delete)
        InputManager.register_indev(mouse)
        self.addCleanup(InputManager.unregister_indev, mouse)
        USBManager._wrap_all_touch(FakeUSB(), FakePanel())
        self.addCleanup(USBManager._unwrap_touch)
        self.assertTrue("_calc_coords" not in mouse.__dict__)
        self.assertEqual(mouse._calc_coords(7, 9), (7, 9))
        _ = lv  # silence unused import if helpers change


class TestActivateDeactivate(GraphicalTestCase):
    def setUp(self):
        super().setUp()
        self.fake = FakeUSBMod()
        sys.modules["usb"] = self.fake
        self.prev = (
            USBManager._usb_dev, USBManager._usb_mouse,
            USBManager._usb_keyboard, USBManager._hid_hub,
            USBManager._hid_idle_prev, USBManager._active,
        )
        USBManager._usb_dev = None
        USBManager._usb_mouse = None
        USBManager._usb_keyboard = None
        USBManager._hid_hub = None
        USBManager._hid_idle_prev = None
        USBManager._active = "panel"

    def tearDown(self):
        sys.modules.pop("usb", None)
        for dev in (USBManager._usb_mouse, USBManager._usb_keyboard):
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
        (USBManager._usb_dev, USBManager._usb_mouse,
         USBManager._usb_keyboard, USBManager._hid_hub,
         USBManager._hid_idle_prev, USBManager._active) = self.prev

    def test_activate_arms_display_and_hid(self):
        self.assertTrue(USBManager.activate(persist=False))
        self.assertTrue(self.fake.activated)
        self.assertIsNotNone(USBManager._usb_dev)
        self.assertIsNotNone(USBManager._usb_mouse)
        self.assertIsNotNone(USBManager._usb_keyboard)
        self.assertTrue(USBManager.host_mode_active())

    def test_activate_legacy_module_fails(self):
        sys.modules["usb"] = LegacyFakeUSBMod()
        self.assertFalse(USBManager.activate(persist=False))

    def test_deactivate_tears_everything_down(self):
        self.assertTrue(USBManager.activate(persist=False))
        mouse, kbd = USBManager._usb_mouse, USBManager._usb_keyboard
        self.assertTrue(mouse in InputManager.list_indevs())
        self.assertTrue(USBManager.deactivate(persist=False))
        self.assertTrue(self.fake.deactivated)
        self.assertIsNone(USBManager._usb_dev)
        self.assertIsNone(USBManager._usb_mouse)
        self.assertIsNone(USBManager._usb_keyboard)
        self.assertIsNone(USBManager._hid_hub)
        self.assertTrue(mouse not in InputManager.list_indevs())
        self.assertTrue(kbd not in InputManager.list_indevs())
        self.assertFalse(USBManager.host_mode_active())
        self.assertIsNone(USBManager._hid_idle_prev)

    def test_host_boot_defaults_off(self):
        # No pref file, BOOT pin unreadable-or-high on desktop: off either way.
        self.assertFalse(USBManager.host_boot_requested())
        self.assertFalse(USBManager._bootsel_held()
                         and USBManager._get_host_pref())

    def test_host_pref_round_trip(self):
        # Single source of truth shared with the Settings UI: same
        # namespace, same key the framework persists ("on"/"off" strings).
        self.assertEqual((USBManager._HOST_PREFS, USBManager._HOST_MODE_KEY),
                         ("com.micropythonos.settings", "usb_host_mode"))
        import os
        path = "prefs/com.micropythonos.settings/config.json"
        try:
            with open(path, "rb") as f:
                had = f.read()
        except Exception:
            had = None
        try:
            USBManager._set_host_pref(True)
            self.assertTrue(USBManager._get_host_pref())
            USBManager._set_host_pref(False)
            self.assertFalse(USBManager._get_host_pref())
        finally:
            try:
                if had is None:
                    if os.path.exists(path):
                        os.remove(path)
                else:
                    with open(path, "wb") as f:
                        f.write(had)
            except Exception:
                pass
