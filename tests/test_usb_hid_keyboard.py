import unittest

import lvgl as lv

from drivers.indev.usb_hid import FakeHIDSource, HIDHub, USBHIDKeyboard
from mpos import InputManager
from mpos.ui.testing import GraphicalTestCase





class TestHIDHub(unittest.TestCase):
    def test_mouse_and_keyboard_demux(self):
        source = FakeHIDSource()
        hub = HIDHub(source)
        source.inject_mouse(buttons=1, dx=3, dy=-2, addr=5)
        source.inject_keyboard([0x0B], addr=6)
        source.inject(7, 9, 9, bytes([1, 2, 3]))
        hub.pump()
        self.assertEqual(hub.drain_mouse(), [(5, 1, 3, -2, 0)])
        self.assertEqual(hub.key_report, (0, 0, 0x0B, 0, 0, 0, 0, 0))
        self.assertEqual(hub.key_addr, 6)
        self.assertEqual(hub.drain_mouse(), [])

    def test_key_report_keeps_latest(self):
        source = FakeHIDSource()
        hub = HIDHub(source)
        source.inject_keyboard([0x0B], addr=6)
        source.inject_keyboard([0x0C, 0x0D], addr=6)
        hub.pump()
        self.assertEqual(hub.key_report, (0, 0, 0x0C, 0x0D, 0, 0, 0, 0))

    def test_short_keyboard_report_ignored(self):
        source = FakeHIDSource()
        hub = HIDHub(source)
        source.inject(6, 1, 1, bytes([0, 0, 0x0B]))
        hub.pump()
        self.assertIsNone(hub.key_report)

    def test_empty_hub(self):
        hub = HIDHub(FakeHIDSource())
        hub.pump()
        self.assertEqual(hub.drain_mouse(), [])
        self.assertIsNone(hub.key_report)


class TestUSBHIDKeyboard(GraphicalTestCase):
    def setUp(self):
        super().setUp()
        self.source = FakeHIDSource()
        self.hub = HIDHub(self.source)
        self.kbd = USBHIDKeyboard(self.hub)
        self.addCleanup(self._cleanup_kbd)
        group = lv.group_get_default()
        if group is not None:
            self.kbd.set_group(group)
        InputManager.register_indev(self.kbd)
        self.ta = lv.textarea(self.screen)
        self.ta.set_size(200, 40)
        if group is not None:
            group.add_obj(self.ta)
            lv.group_focus_obj(self.ta)
        self.wait_for_render()

    def _cleanup_kbd(self):
        try:
            InputManager.unregister_indev(self.kbd)
        except Exception:
            pass
        try:
            self.kbd.delete()
        except Exception:
            pass

    def _type_key(self, keys, modifiers=0):
        self.source.inject_keyboard(keys, modifiers=modifiers)
        self.kbd.read()
        self.wait_for_render()
        self.source.inject_keyboard([])
        self.kbd.read()
        self.wait_for_render()

    def test_typing_letters(self):
        self._type_key([0x0B])
        self.assertEqual(self.ta.get_text(), "h")
        self._type_key([0x0C])
        self.assertEqual(self.ta.get_text(), "hi")

    def test_shift_gives_uppercase(self):
        self._type_key([0x0B], modifiers=0x02)
        self.assertEqual(self.ta.get_text(), "H")

    def test_key_release_emits_nothing_extra(self):
        self._type_key([0x0B])
        self.kbd.read()
        self.wait_for_render()
        self.assertEqual(self.ta.get_text(), "h")
