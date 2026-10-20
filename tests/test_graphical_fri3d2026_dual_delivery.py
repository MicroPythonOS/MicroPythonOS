import unittest

import lvgl as lv

import mpos.ui
from drivers.indev.fri3d_2026_expander import Fri3d2026Expander


class _StubExpander:
    pass


class TestGraphicalFri3d2026DualDelivery(unittest.TestCase):
    def setUp(self):
        self.keys = []
        self.obj = lv.obj()
        self.obj.add_event_cb(self._on_key, lv.EVENT.KEY, None)
        group = lv.group_get_default()
        group.add_obj(self.obj)
        lv.group_focus_obj(self.obj)
        self.drv = Fri3d2026Expander(_StubExpander())

    def tearDown(self):
        try:
            group = lv.group_get_default()
            group.remove_obj(self.obj)
        except Exception:
            pass
        try:
            self.obj.delete()
        except Exception:
            pass
        try:
            mpos.ui.back_screen()
        except Exception:
            pass

    def _on_key(self, event):
        self.keys.append(event.get_key())

    def test_b_delivers_ord_letter(self):
        self.drv._fire_nav_hook(self.drv.PRESSED, lv.KEY.NEXT)
        self.assertEqual(self.keys, [ord("B")])

    def test_y_delivers_ord_letter(self):
        self.drv._fire_nav_hook(self.drv.PRESSED, lv.KEY.PREV)
        self.assertEqual(self.keys, [ord("Y")])

    def test_release_delivers_nothing(self):
        self.drv._fire_nav_hook(self.drv.RELEASED, lv.KEY.NEXT)
        self.drv._fire_nav_hook(self.drv.RELEASED, lv.KEY.PREV)
        self.assertEqual(self.keys, [])

    def test_other_keys_deliver_nothing(self):
        self.drv._fire_nav_hook(self.drv.PRESSED, lv.KEY.ENTER)
        self.drv._fire_nav_hook(self.drv.PRESSED, lv.KEY.UP)
        self.drv._fire_nav_hook(self.drv.PRESSED, lv.KEY.DOWN)
        self.assertEqual(self.keys, [])


if __name__ == "__main__":
    unittest.main()
