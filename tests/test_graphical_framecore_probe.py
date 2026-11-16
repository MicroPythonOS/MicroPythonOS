"""Tests for the native framecore probe (c_mpos/framecore_probe/).

The probe stands in for a legacy framebuffer engine, so these tests pin the
things a port depends on and that a missing libc would break silently: the
full-frame draw and its row offset, text formatted through the shim's
vsnprintf, the palette/32-bit conversions, the key queue, the engine-owned
framebuffer and the Python file shim.
"""

import sys
import unittest

# The module ships in the app folder, so the app's directory is on sys.path
# while it runs; a test run from the filesystem root needs it there too.
_APP_DIR = "apps/com.micropythonos.framecoreprobe"
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

if sys.platform == "esp32":
    import framecore_probe_xtensawin as probe
else:
    import framecore_probe_x64 as probe

# The real engine frame: the test pattern and the counter box only make sense
# at the size the probe actually runs.
WIDTH = 320
HEIGHT = 200
BAR_COLORS = (0xF800, 0xFC00, 0xFFE0, 0x07E0, 0x07FF, 0x001F, 0xF81F, 0xFFFF)


def _rgb888_to_rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


class ProbeTest(unittest.TestCase):

    def setUp(self):
        self.buffer = bytearray(WIDTH * HEIGHT * 2)
        probe.init(self.buffer, WIDTH, HEIGHT, 0)
        probe.free_framebuffer()

    def _rgb(self, index):
        return self.buffer[index * 2] | (self.buffer[index * 2 + 1] << 8)

    def _pixel(self, x, y):
        return self._rgb(y * WIDTH + x)

    # -- the frame ---------------------------------------------------------

    def test_a_frame_fills_the_whole_surface(self):
        probe.draw(0)
        # 320 pixels over 8 bars is 40 pixels each.
        self.assertEqual(self._pixel(0, 0), BAR_COLORS[0])
        self.assertEqual(self._pixel(40, 0), BAR_COLORS[1])
        self.assertEqual(self._pixel(WIDTH - 1, 0), BAR_COLORS[7])
        # The lower half is the dark slab, so no row is left stale.
        self.assertEqual(self._pixel(0, HEIGHT - 2), 0x2104)

    def test_the_frame_counter_is_drawn_and_changes(self):
        probe.draw(0)
        first = bytes(self.buffer)
        probe.draw(0)
        second = bytes(self.buffer)
        self.assertNotEqual(first, second,
                            "the frame counter did not change between frames")
        self.assertTrue(first.count(b"\xff\xff") > 0,
                        "no glyph pixels: vsnprintf or the font is broken")
        self.assertEqual(probe.get_frames(), 2)

    def test_the_frame_is_drawn_at_the_requested_row_offset(self):
        surface = bytearray(WIDTH * (HEIGHT + 8) * 2)
        probe.init(surface, WIDTH, HEIGHT, 4)
        probe.draw(0)
        self.assertEqual(surface[0:WIDTH * 2 * 4], bytearray(WIDTH * 8),
                         "rows above the engine frame were written")
        row4 = surface[WIDTH * 2 * 4:WIDTH * 2 * 5]
        self.assertEqual(row4[0] | (row4[1] << 8), BAR_COLORS[0])

    def test_a_buffer_too_small_is_rejected(self):
        with self.assertRaises(ValueError):
            probe.init(bytearray(WIDTH * HEIGHT * 2 - 4), WIDTH, HEIGHT, 0)

    def test_a_bad_offset_is_rejected(self):
        with self.assertRaises(ValueError):
            probe.init(bytearray(WIDTH * HEIGHT * 2), WIDTH, HEIGHT, -1)

    # -- input -------------------------------------------------------------

    def test_keys_come_back_in_order_with_the_pressed_bit(self):
        self.assertEqual(probe.poll_key(), -1)
        probe.key(probe.KEY_LEFT, True)
        probe.key(probe.KEY_RIGHT, False)
        self.assertEqual(probe.poll_key(), 0x100 | probe.KEY_LEFT)
        self.assertEqual(probe.poll_key(), probe.KEY_RIGHT)
        self.assertEqual(probe.poll_key(), -1)

    def test_a_pressed_key_moves_the_box(self):
        probe.draw(0)
        start = probe.get_box_x()
        probe.key(probe.KEY_LEFT, True)
        self.assertTrue(probe.get_box_x() < start,
                        "a pressed key did not move the box")
        moved = probe.get_box_x()
        probe.key(probe.KEY_LEFT, False)
        self.assertEqual(probe.get_box_x(), moved,
                         "a released key must not move the box")

    def test_the_box_stops_at_the_edge(self):
        for _ in range(200):
            probe.key(probe.KEY_LEFT, True)
        self.assertEqual(probe.get_box_x(), 0)
        for _ in range(200):
            probe.key(probe.KEY_RIGHT, True)
        self.assertEqual(probe.get_box_x(), WIDTH - 16)

    # -- conversions -------------------------------------------------------

    def _palette(self):
        palette = bytearray(768)
        for i in range(256):
            palette[i * 3] = i
            palette[i * 3 + 1] = 255 - i
            palette[i * 3 + 2] = (i * 5) & 0xFF
        return palette

    def test_expand8_matches_the_palette(self):
        palette = self._palette()
        src = bytearray([0, 1, 127, 255])
        dst = bytearray(len(src) * 2)
        probe.expand8(src, palette, dst)
        for index, value in enumerate(src):
            expected = _rgb888_to_rgb565(
                palette[value * 3], palette[value * 3 + 1], palette[value * 3 + 2])
            self.assertEqual(dst[index * 2] | (dst[index * 2 + 1] << 8), expected)

    def test_the_lut_path_matches_the_per_pixel_path(self):
        palette = self._palette()
        src = bytearray(range(256))
        direct = bytearray(len(src) * 2)
        via_lut = bytearray(len(src) * 2)
        probe.expand8(src, palette, direct)
        probe.set_palette(palette)
        probe.expand8_lut(src, via_lut)
        self.assertEqual(bytes(direct), bytes(via_lut))

    def test_expand8_needs_a_palette(self):
        src = bytearray(4)
        dst = bytearray(8)
        with self.assertRaises(ValueError):
            probe.expand8(src, bytearray(2), dst)
        with self.assertRaises(ValueError):
            probe.expand8_lut(src, dst)

    def test_expand32_converts_rgba(self):
        src = bytearray([10, 20, 30, 255, 248, 254, 248, 0])
        dst = bytearray(len(src) // 2)
        probe.expand32(src, dst)
        self.assertEqual(dst[0] | (dst[1] << 8), _rgb888_to_rgb565(10, 20, 30))
        self.assertEqual(dst[2] | (dst[3] << 8), 0xFFFF)

    def test_a_too_small_conversion_destination_is_rejected(self):
        with self.assertRaises(ValueError):
            probe.expand32(bytearray(16), bytearray(2))
        with self.assertRaises(ValueError):
            probe.expand8(bytearray(16), self._palette(), bytearray(2))

    def test_banded_expansion_matches_the_whole_frame(self):
        palette = self._palette()
        probe.set_palette(palette)
        width = 8
        height = 6
        src = bytearray(range(width * height))
        whole = bytearray(width * height * 2)
        banded = bytearray(width * height * 2)
        probe.expand8_lut(src, whole)
        for band in range(3):
            probe.expand8_band(src, banded, band, 16)
        self.assertEqual(bytes(whole), bytes(banded))

    def test_banded_expansion_stops_at_the_end(self):
        probe.set_palette(self._palette())
        src = bytearray(10)
        dst = bytearray(20)
        probe.expand8_band(src, dst, 2, 4)   # rows 8..9 only
        probe.expand8_band(src, dst, 9, 4)   # past the end: no-op
        self.assertNotEqual(bytes(dst), bytes(20))

    # -- the engine's own framebuffer --------------------------------------

    def test_the_module_can_own_the_framebuffer(self):
        buffer = probe.alloc_framebuffer(WIDTH, HEIGHT)
        try:
            self.assertEqual(len(buffer), WIDTH * HEIGHT * 2)
            probe.init(buffer, WIDTH, HEIGHT, 0)
            probe.draw(0)
            self.assertEqual(
                buffer[0] | (buffer[1] << 8), BAR_COLORS[0],
                "the module did not draw into the bytearray it handed out")
        finally:
            probe.free_framebuffer()

    def test_a_second_allocation_is_refused(self):
        probe.alloc_framebuffer(WIDTH, HEIGHT)
        try:
            with self.assertRaises(ValueError):
                probe.alloc_framebuffer(WIDTH, HEIGHT)
        finally:
            probe.free_framebuffer()

    def test_freeing_allows_a_new_allocation(self):
        probe.alloc_framebuffer(WIDTH, HEIGHT)
        probe.free_framebuffer()
        buffer = probe.alloc_framebuffer(WIDTH, HEIGHT)
        try:
            self.assertEqual(len(buffer), WIDTH * HEIGHT * 2)
        finally:
            probe.free_framebuffer()

    # -- the file shim -----------------------------------------------------

    def test_read_file_calls_the_python_reader(self):
        calls = []

        def reader(path, offset, into):
            calls.append((path, offset, len(into)))
            into[0] = 0x5A
            return 1

        probe.set_file_reader(reader)
        into = bytearray(8)
        self.assertEqual(probe.read_file("lump", 1234, into), 1)
        self.assertEqual(calls, [("lump", 1234, 8)])
        self.assertEqual(into[0], 0x5A)

    def test_read_file_without_a_reader_is_an_error(self):
        with self.assertRaises(ValueError):
            probe.read_file("lump", 0, bytearray(4))
