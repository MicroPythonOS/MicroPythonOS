import unittest

import display_driver_framework
import lcd_bus
import lvgl as lv
import mpos.ui


class _RecordingBus:
    def __init__(self):
        self.callback = None

    def register_callback(self, callback):
        self.callback = callback


class _Driver(display_driver_framework.DisplayDriver):
    def __init__(self, disp):
        self._data_bus = _RecordingBus()
        self._disp_drv = disp

    def __del__(self):
        pass


class _OverridingDriver(_Driver):
    def _flush_ready_cb(self, *_):
        pass


class TestLcdBusFlushReadyCallback(unittest.TestCase):

    def setUp(self):
        self.disp = lv.display_create(32, 32)
        self.disp.set_color_format(lv.COLOR_FORMAT.RGB565)
        self.buf = bytearray(32 * 8 * 2)
        self.flushes = 0
        self.waits = 0
        self.signal_ready = True
        self.ready = lcd_bus.FlushReadyCallback(self.disp)
        self.disp.set_flush_cb(self._flush_cb)
        self.disp.set_flush_wait_cb(self._wait_cb)
        self.disp.set_buffers(self.buf, None, len(self.buf), lv.DISPLAY_RENDER_MODE.PARTIAL)

    def tearDown(self):
        self.disp.delete()
        self.disp = None
        self.ready = None

    def _flush_cb(self, disp, area, px_map):
        self.flushes += 1
        if self.signal_ready:
            self.ready()

    def _wait_cb(self, disp):
        self.waits += 1

    def _refresh(self):
        self.disp.get_screen_active().invalidate()
        lv.refr_now(self.disp)

    def test_callback_marks_flush_done(self):
        self._refresh()
        self.assertTrue(self.flushes >= 2)
        self.assertEqual(self.waits, 0)

    def test_lvgl_waits_when_flush_is_not_signalled(self):
        self.signal_ready = False
        self._refresh()
        self.assertTrue(self.flushes >= 2)
        self.assertTrue(self.waits >= 1)

    def test_callback_ignores_arguments(self):
        self.assertIsNone(self.ready(1, 2, 3))

    def test_rejects_objects_that_are_not_displays(self):
        with self.assertRaises(TypeError):
            lcd_bus.FlushReadyCallback(object())
        with self.assertRaises(TypeError):
            lcd_bus.FlushReadyCallback(bytearray(8))
        with self.assertRaises(TypeError):
            lcd_bus.FlushReadyCallback()

    def test_driver_registers_c_callback(self):
        drv = _Driver(self.disp)
        drv._register_flush_ready_cb()
        self.assertTrue(isinstance(drv._data_bus.callback, lcd_bus.FlushReadyCallback))
        self.assertTrue(drv._flush_ready_cb is drv._data_bus.callback)

    def test_driver_keeps_overridden_callback(self):
        drv = _OverridingDriver(self.disp)
        drv._register_flush_ready_cb()
        self.assertFalse(isinstance(drv._data_bus.callback, lcd_bus.FlushReadyCallback))

    def test_main_display_uses_c_callback(self):
        self.assertTrue(isinstance(mpos.ui.main_display._flush_ready_cb, lcd_bus.FlushReadyCallback))


if __name__ == "__main__":
    unittest.main()
