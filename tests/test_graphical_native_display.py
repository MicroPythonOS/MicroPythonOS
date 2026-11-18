"""Tests for mpos.ui.native_display.NativeDisplay.

The point of the class is to keep LVGL the only writer of the panel: a native
renderer draws into an ordinary RGB565 buffer, and only the bands of rows it
reports as changed are invalidated, so LVGL blits and flushes just those.

These tests pin down the band geometry, the invalidation areas and the flushing
contract, none of which needs real hardware.
"""

import unittest

import lvgl as lv

import mpos.ui
from mpos.ui import native_display
from mpos.ui.native_display import NativeDisplay


class _FakeDisplay:
    """A display with a partial draw buffer of a known size.

    Small on purpose: the class under test allocates a surface of
    width*height*2 bytes, and a device run has to keep a dozen of those out of
    PSRAM. The band arithmetic is the same at any size.
    """

    def __init__(self, width, height, draw_buffer_bytes):
        self._width = width
        self._height = height
        self._frame_buffer1 = bytearray(draw_buffer_bytes)
        self._frame_buffer2 = None
        self._rotation = 0
        self.windows = []
        self.transfers = []
        self._data_bus = self

    # the two driver calls the direct path makes
    def _set_memory_location(self, x1, y1, x2, y2):
        self.windows.append((x1, y1, x2, y2))
        return 0x2C

    def tx_color(self, cmd, view, x1, y1, x2, y2, rotation, last):
        self.transfers.append(len(view))

    def get_horizontal_resolution(self):
        return self._width

    def get_vertical_resolution(self):
        return self._height


SMALL_W = 32
SMALL_H = 24


class _InvalidationRecorder:
    """Stands in for the image widget and records invalidated areas."""

    def __init__(self, image):
        self._image = image
        self.areas = []
        self.whole = 0

    def invalidate_area(self, area):
        self.areas.append((area.x1, area.y1, area.x2, area.y2))

    def invalidate(self):
        self.whole += 1


class TestNativeDisplay(unittest.TestCase):

    def setUp(self):
        self.screen = lv.obj()
        lv.screen_load(self.screen)
        self.created = []
        # 32x24 with a 4-row draw buffer: six bands, like a 320x240 screen with
        # the 45-row buffers the display driver allocates there.
        self.display = _FakeDisplay(SMALL_W, SMALL_H, SMALL_W * 4 * 2)
        self.pump = self._make(self.display)
        self.pump.begin()

    def tearDown(self):
        # Never delete the screen that is still loaded: load a fresh one first,
        # which is what the other graphical tests do.
        lv.screen_load(lv.obj())

    def _make(self, display):
        pump = NativeDisplay(self.screen, display=display)
        self.created.append(pump)
        return pump

    # -- geometry ---------------------------------------------------------

    def test_band_rows_come_from_the_draw_buffer(self):
        self.assertEqual(self.pump.rows_per_band, 4)
        self.assertEqual(self.pump.band_count, 6)
        self.assertEqual(len(self.pump.buffer), SMALL_W * SMALL_H * 2)

    def test_a_full_screen_buffer_makes_one_band(self):
        pump = self._make(_FakeDisplay(SMALL_W, SMALL_H, SMALL_W * SMALL_H * 2))
        self.assertEqual(pump.rows_per_band, SMALL_H)
        self.assertEqual(pump.band_count, 1)

    def test_a_tiny_buffer_still_makes_at_least_one_row_bands(self):
        pump = self._make(_FakeDisplay(SMALL_W, SMALL_H, 1))
        self.assertEqual(pump.rows_per_band, 1)
        self.assertEqual(pump.band_count, SMALL_H)

    def test_last_band_stops_at_the_screen_edge(self):
        # 24 rows in bands of 4 leave a last band that ends exactly at the edge.
        areas = self._record_invalidations(self.pump)
        self.pump.invalidate_band(5)
        self.assertEqual(areas, [(0, 20, SMALL_W - 1, SMALL_H - 1)])

    def test_invalidate_band_covers_its_rows(self):
        areas = self._record_invalidations(self.pump)
        self.pump.invalidate_band(1)
        self.assertEqual(areas, [(0, 4, SMALL_W - 1, 7)])

    def test_band_invalidation_follows_a_centred_surface(self):
        # The image sits at y=4 on this 24-row screen, so band 1 (surface rows
        # 4..7) is screen rows 8..11: invalidating without the offset would
        # redraw the letterbox above the game instead of the game.
        pump = self._make_area(SMALL_W, SMALL_H - 8)
        areas = self._record_area_invalidations(pump)
        pump.invalidate_band(1)
        self.assertEqual(areas, [(0, 8, SMALL_W - 1, 11)])

    def test_area_present_follows_a_centred_surface(self):
        pump = self._make_area(SMALL_W, SMALL_H - 8)
        areas = self._record_area_invalidations(pump)
        pump.present_area(0, 0, SMALL_W - 1, 2, lambda band: None, flush=False)
        self.assertEqual(areas, [(0, 4, SMALL_W - 1, 6)])

    def _record_invalidations(self, pump):
        areas = []

        def invalidate_band(band):
            y1 = band * pump.rows_per_band
            y2 = min(y1 + pump.rows_per_band - 1, pump.height - 1)
            areas.append((0, y1, pump.width - 1, y2))

        pump.invalidate_band = invalidate_band
        return areas

    # -- presenting -------------------------------------------------------

    def test_present_renders_every_band_it_is_given(self):
        rendered = []
        self.pump.present([0, 3, 5], rendered.append, flush=False)
        self.assertEqual(rendered, [0, 3, 5])
        self.assertEqual(self.pump.bands, 3)
        self.assertEqual(self.pump.frames, 1)

    def test_present_accepts_a_generator_of_dirty_bands(self):
        rendered = []
        pending = [2, 4]

        def dirty():
            while pending:
                yield pending.pop(0)

        self.pump.present(dirty(), rendered.append, flush=False)
        self.assertEqual(rendered, [2, 4])

    def test_present_flushes_once_per_frame(self):
        flushes = []
        self.pump.flush = lambda: flushes.append(1)
        self.pump.present([0, 1, 2], lambda band: None)
        self.assertEqual(len(flushes), 1)

    def test_a_paused_surface_draws_nothing(self):
        rendered = []
        self.pump.end()
        self.pump.present([0, 1], rendered.append)
        self.assertEqual(rendered, [])
        self.assertEqual(self.pump.bands, 0)

    def test_present_does_not_flush_a_frame_with_nothing_dirty(self):
        flushes = []
        self.pump.flush = lambda: flushes.append(1)
        self.pump.present([], lambda band: None)
        self.assertEqual(flushes, [])

    def test_present_all_covers_the_screen(self):
        rendered = []
        self.pump.present_all(rendered.append, flush=False)
        self.assertEqual(rendered, [0, 1, 2, 3, 4, 5])

    # -- the widget -------------------------------------------------------

    def test_image_shows_the_buffer_at_full_size(self):
        self.assertEqual(self.pump.image.get_x(), 0)
        self.assertEqual(self.pump.image.get_y(), 0)
        self.screen.update_layout()
        self.assertEqual(self.pump.image.get_width(), SMALL_W)
        self.assertEqual(self.pump.image.get_height(), SMALL_H)

    # -- geometry a native renderer computes from -------------------------

    def test_pixel_layout_is_exposed_for_native_callers(self):
        self.assertEqual(self.pump.bytes_per_pixel, 2)
        self.assertEqual(self.pump.stride, SMALL_W * 2)
        self.assertEqual(len(self.pump.buffer), self.pump.stride * SMALL_H)

    # -- a buffer the caller owns -----------------------------------------

    def test_an_external_buffer_is_used_and_not_copied(self):
        buffer = bytearray(SMALL_W * SMALL_H * 2)
        pump = NativeDisplay(self.screen, display=self.display, buffer=buffer)
        self.created.append(pump)
        self.assertTrue(pump.buffer is buffer)
        self.assertEqual(pump._descriptor.data_size, len(buffer))

    def test_writing_to_the_external_buffer_writes_the_image(self):
        buffer = bytearray(SMALL_W * SMALL_H * 2)
        pump = NativeDisplay(self.screen, display=self.display, buffer=buffer)
        self.created.append(pump)
        pump.begin()
        buffer[0] = 0x12
        buffer[1] = 0x34
        self.assertEqual(pump.buffer[0], 0x12)
        self.assertEqual(pump.buffer[1], 0x34)

    def test_a_buffer_that_is_too_small_is_rejected(self):
        with self.assertRaises(ValueError):
            NativeDisplay(self.screen, display=self.display,
                          buffer=bytearray(SMALL_W * SMALL_H))

    def test_a_buffer_may_be_larger_than_the_surface(self):
        buffer = bytearray(SMALL_W * SMALL_H * 2 + 16)
        pump = NativeDisplay(self.screen, display=self.display, buffer=buffer)
        self.created.append(pump)
        self.assertTrue(pump.buffer is buffer)
        self.assertEqual(pump._descriptor.data_size, SMALL_W * SMALL_H * 2)

    # -- a surface smaller than the display -------------------------------

    def test_a_smaller_surface_is_centred(self):
        # 320x200 on 320x240 is the Doom case: 20 rows of letterbox each side.
        pump = self._make_area(SMALL_W, SMALL_H - 8)
        self.screen.update_layout()
        self.assertEqual(pump.width, SMALL_W)
        self.assertEqual(pump.height, SMALL_H - 8)
        self.assertEqual(pump.image.get_x(), 0)
        self.assertEqual(pump.image.get_y(), 4)
        self.assertEqual(len(pump.buffer), SMALL_W * (SMALL_H - 8) * 2)

    def test_bands_are_computed_for_the_surface_not_the_screen(self):
        pump = self._make_area(SMALL_W, SMALL_H - 8)
        self.assertEqual(pump.rows_per_band, 4)
        self.assertEqual(pump.band_count, 4)

    def test_a_surface_larger_than_the_display_is_rejected(self):
        with self.assertRaises(ValueError):
            NativeDisplay(self.screen, display=self.display,
                          width=SMALL_W, height=SMALL_H + 1)

    def _make_area(self, width, height, buffer=None):
        pump = NativeDisplay(self.screen, display=self.display,
                             buffer=buffer, width=width, height=height)
        self.created.append(pump)
        pump.begin()
        return pump

    # -- presenting an area -----------------------------------------------

    def test_present_area_renders_only_the_bands_it_touches(self):
        rendered = []
        self.pump.present_area(0, 5, SMALL_W - 1, 9, rendered.append, flush=False)
        self.assertEqual(rendered, [1, 2])
        self.assertEqual(self.pump.bands, 2)

    def test_present_area_invalidates_exactly_the_rectangle(self):
        areas = self._record_area_invalidations(self.pump)
        self.pump.present_area(2, 5, 20, 9, lambda band: None, flush=False)
        self.assertEqual(areas, [(2, 5, 20, 9)])

    def test_present_area_clips_to_the_surface(self):
        areas = self._record_area_invalidations(self.pump)
        self.pump.present_area(-3, -4, SMALL_W + 5, SMALL_H + 5,
                              lambda band: None, flush=False)
        self.assertEqual(areas, [(0, 0, SMALL_W - 1, SMALL_H - 1)])

    def test_present_area_of_nothing_does_nothing(self):
        areas = self._record_area_invalidations(self.pump)
        rendered = []
        self.pump.present_area(5, 5, 4, 4, rendered.append)
        self.assertEqual(rendered, [])
        self.assertEqual(areas, [])

    def test_present_area_flushes_once(self):
        flushes = []
        self.pump.flush = lambda: flushes.append(1)
        self.pump.present_area(0, 0, SMALL_W - 1, SMALL_H - 1, lambda band: None)
        self.assertEqual(len(flushes), 1)

    def test_a_paused_surface_presents_no_area(self):
        areas = self._record_area_invalidations(self.pump)
        rendered = []
        self.pump.end()
        self.pump.present_area(0, 0, SMALL_W - 1, SMALL_H - 1, rendered.append)
        self.assertEqual(rendered, [])
        self.assertEqual(areas, [])

    def _record_area_invalidations(self, pump):
        # An LVGL object cannot hold Python attributes, so the widget is wrapped
        # in a proxy that records the exact area it is asked to invalidate.
        recorder = _InvalidationRecorder(pump.image)
        pump.image = recorder
        return recorder.areas


class TestNoPrivateCopy(unittest.TestCase):
    """This is firmware infrastructure: apps import mpos.ui.native_display."""

    def test_no_app_ships_its_own_copy(self):
        import os
        shipped = []
        for name in os.listdir("apps"):
            path = "apps/%s/native_display.py" % name
            try:
                os.stat(path)
            except OSError:
                continue
            shipped.append(path)
        self.assertEqual(shipped, [],
                         "apps must import mpos.ui.native_display, not copy it")


class TestNativeDisplayOnTheRealDisplay(unittest.TestCase):
    """The band size must match what the real display driver allocated."""

    def test_bands_fit_the_real_draw_buffer(self):
        if mpos.ui.main_display is None or mpos.ui.main_display._frame_buffer1 is None:
            self.skipTest("no display")
        screen = lv.obj()
        lv.screen_load(screen)
        try:
            pump = NativeDisplay(screen)
            lv.screen_load(lv.obj())
        except Exception:
            lv.screen_load(lv.obj())
            raise
        buffer_bytes = len(mpos.ui.main_display._frame_buffer1)
        width = mpos.ui.main_display.get_horizontal_resolution()
        if buffer_bytes < width * 2:
            self.skipTest("draw buffer smaller than one row")
        self.assertLessEqual(
            pump.rows_per_band * width * 2,
            buffer_bytes,
            "a band must fit in one draw buffer",
        )
        self.assertEqual(
            pump.band_count,
            (pump.height + pump.rows_per_band - 1) // pump.rows_per_band,
        )
