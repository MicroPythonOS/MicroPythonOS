"""Tests for the native Breakout activity.

Covers the parts where the app and the C module meet: the RGB565 surface the
renderer draws into, the dirty-band loop that decides what gets flushed, and the
frame clock. None of it depends on how fast the machine is, except the tick
budget test, which is a regression test for a native module that re-imported
`time` on every tick (32ms per frame on the badge).
"""

import sys
import time
import unittest

import lvgl as lv

import mpos.ui
from mpos import AppManager
from mpos.ui.view import remove_and_stop_current_activity, screen_stack


def _wait_ms(ms):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        lv.task_handler()
        time.sleep_ms(5)


def _breakout_module():
    if sys.platform == "esp32":
        import breakout_xtensawin as module
    else:
        import breakout_x64 as module
    return module


class _FakePWM:
    def __init__(self):
        self.frequencies = []
        self.duties = []
        self.deinited = False
        self._freq = 0

    def freq(self, value=None):
        if value is None:
            return self._freq
        self._freq = value
        self.frequencies.append(value)

    def duty_u16(self, value=None):
        if value is None:
            return self.duties[-1] if self.duties else 0
        self.duties.append(value)

    def deinit(self):
        self.deinited = True


class TestBreakoutActivity(unittest.TestCase):

    def setUp(self):
        self.assertTrue(AppManager.start_app("com.micropythonos.breakout"))
        _wait_ms(400)
        self.activity = None
        for entry in screen_stack:
            if hasattr(entry[0], "_display"):
                self.activity = entry[0]
        self.assertIsNotNone(self.activity, "the breakout activity is not on the stack")
        self.pump = self.activity._display
        self.module = _breakout_module()

    def tearDown(self):
        while len(screen_stack) > 1:
            remove_and_stop_current_activity()

    def _render_everything(self):
        self.module.mark_all_dirty()
        self.pump.present(self.activity._dirty_bands(), self.module.render_band, flush=False)

    def _band_rows(self, band):
        start = band * self.pump.rows_per_band
        end = start + self.pump.rows_per_band
        if end > self.pump.height:
            end = self.pump.height
        return range(start, end)

    # -- surface ----------------------------------------------------------

    def test_surface_is_an_rgb565_buffer_of_the_screen(self):
        self.assertEqual(len(self.pump.buffer), self.pump.width * self.pump.height * 2)

    def test_a_band_fits_in_one_draw_buffer(self):
        draw_buffer = mpos.ui.main_display._frame_buffer1
        if draw_buffer is None:
            self.skipTest("display has no draw buffer")
        self.assertLessEqual(len(self._band_rows(0)) * self.pump.width * 2, len(draw_buffer))

    def test_bands_cover_every_row_once(self):
        covered = 0
        for band in range(self.pump.band_count):
            covered += len(self._band_rows(band))
        self.assertEqual(covered, self.pump.height)

    def test_the_surface_is_the_image_source(self):
        self.assertEqual(self.pump.image.get_x(), 0)
        self.assertEqual(self.pump.image.get_y(), 0)
        self.pump.image.get_parent().update_layout()
        self.assertEqual(self.pump.image.get_width(), self.pump.width)
        self.assertEqual(self.pump.image.get_height(), self.pump.height)

    # -- rendering --------------------------------------------------------

    def test_a_frame_draws_pixels(self):
        for i in range(len(self.pump.buffer)):
            self.pump.buffer[i] = 0
        self.module.mark_all_dirty()
        self.module.tick(time.ticks_ms())
        self.pump.present(self.activity._dirty_bands(), self.module.render_band, flush=False)

        lit = 0
        for i in range(0, len(self.pump.buffer), 2):
            if self.pump.buffer[i] or self.pump.buffer[i + 1]:
                lit += 1
        self.assertTrue(lit > 100, "a rendered frame should contain the bricks")

    def test_rendering_clears_the_dirty_flags(self):
        self.module.mark_all_dirty()
        self.pump.present(self.activity._dirty_bands(), self.module.render_band, flush=False)
        self.assertEqual(self.module.next_dirty(), -1)

    def test_an_unchanged_frame_presents_nothing(self):
        self._render_everything()
        self.assertEqual(self._presented_bands(), [])

    def _presented_bands(self):
        rendered = []

        def render(band):
            rendered.append(band)
            self.module.render_band(band)

        self.pump.present(self.activity._dirty_bands(), render, flush=False)
        return rendered

    def test_moving_the_paddle_dirties_only_the_bottom_band(self):
        self._render_everything()
        self.module.move_paddle(10)
        self.assertEqual(self._presented_bands(), [self.pump.band_count - 1])

    def test_each_band_is_drawn_at_its_own_rows(self):
        """A band must land on its own rows of the surface.

        The renderer draws one band at a time into a full-screen buffer, so a
        missing y offset puts every band at the top of the picture: the bricks
        appear but the paddle (last band) ends up at row 7.
        """
        self.module.set_band_rows(45)
        try:
            self.module.mark_all_dirty()
            self.pump.present(self.activity._dirty_bands(), self.module.render_band, flush=False)
            rows = []
            for y in range(self.pump.height):
                base = y * self.pump.width * 2
                if any(self.pump.buffer[base:base + self.pump.width * 2]):
                    rows.append(y)
            self.assertTrue(rows, "nothing was drawn")
            self.assertLessEqual(min(rows), 16, "the bricks belong at the top")
            self.assertGreaterEqual(max(rows), self.pump.height - 10,
                                    "the paddle belongs at the bottom, got row %d" % max(rows))
        finally:
            self.module.set_band_rows(self.pump.rows_per_band)

    def test_moving_the_paddle_redraws_it(self):
        self._render_everything()
        before = bytes(self.pump.buffer)
        self.module.move_paddle(24)
        self.pump.present(self.activity._dirty_bands(), self.module.render_band, flush=False)
        self.assertNotEqual(bytes(self.pump.buffer), before)

    # -- frame clock ------------------------------------------------------

    def test_tick_does_not_reimport_what_it_can_cache(self):
        """A native tick must not pay for an import.

        `mp_import_name("time")` costs about 32ms on the badge because it walks
        the import machinery, and an earlier version called it from inside every
        tick. 100 ticks have to be far below that.
        """
        now = time.ticks_ms()
        self.module.tick(now)
        start = time.ticks_us()
        for _ in range(100):
            self.module.tick(now)
        elapsed_ms = time.ticks_diff(time.ticks_us(), start) // 1000
        self.assertTrue(elapsed_ms < 500, "100 ticks took %dms" % elapsed_ms)

    # -- sound ------------------------------------------------------------

    def _beep(self):
        # The activity owns a Beep, so its class is the app's class even when
        # AppManager has since dropped the app module from sys.modules.
        beep = type(self.activity._beep)()
        beep._pwm = _FakePWM()
        beep._enabled = True
        return beep

    def test_a_tone_drives_the_buzzer_and_turns_itself_off(self):
        beep = self._beep()
        now = time.ticks_ms()
        beep.tone(4400, 20)
        self.assertEqual(beep._pwm.frequencies[-1], 4400)
        self.assertEqual(beep._pwm.duties[-1], 32768)
        self.assertEqual(beep.tones, 1)

        beep.poll(time.ticks_add(now, 10))
        self.assertEqual(beep._pwm.duties[-1], 32768, "still inside the tone")
        beep.poll(time.ticks_add(now, 40))
        self.assertEqual(beep._pwm.duties[-1], 0, "the tone must not ring on forever")

    def test_a_tone_is_polled_off_on_a_frame_with_no_event(self):
        """The frame loop polls the beeper every frame, not on events only."""
        beep = self._beep()
        activity = self.activity
        had_beep = activity._beep
        activity._beep = beep
        try:
            beep.tone(3200, 20)
            beep._off_at = time.ticks_add(time.ticks_ms(), -1)
            activity._next_frame_ms = time.ticks_add(time.ticks_ms(), -1)
            activity.drawframe()
            self.assertEqual(beep._pwm.duties[-1], 0, "a stale tone must stop")
        finally:
            activity._beep = had_beep

    def test_stop_deinitialises_the_pwm(self):
        beep = self._beep()
        beep.tone(3200, 20)
        beep.stop()
        self.assertEqual(beep._pwm, None)
        self.assertTrue(beep.tones == 1)

    def test_gameplay_events_play_a_tone(self):
        activity = self.activity
        beep = self._beep()
        had_beep = activity._beep
        activity._beep = beep
        try:
            activity._play_events(self.module.EVENT_BRICK)
            self.assertEqual(beep.tones, 1, "hitting a brick should beep")
            activity._play_events(self.module.EVENT_PADDLE)
            self.assertEqual(beep.tones, 2, "hitting the paddle should beep")
            activity._play_events(0)
            self.assertEqual(beep.tones, 2, "no event, no tone")
        finally:
            activity._beep = had_beep

    def test_pausing_stops_the_frame_callback(self):
        task_handler = mpos.ui.task_handler

        def drawframe_callbacks():
            return [cb for (cb, evt, data) in task_handler._callbacks
                    if getattr(cb, "__name__", "") == "drawframe"]

        self.activity.onPause(self.activity.screen)
        self.assertEqual(drawframe_callbacks(), [])
        self.activity.onResume(self.activity.screen)
        self.assertEqual(len(drawframe_callbacks()), 1)


if __name__ == "__main__":
    unittest.main()
