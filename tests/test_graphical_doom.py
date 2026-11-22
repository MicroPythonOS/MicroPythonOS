"""Tests for the Doom app: one activity, one engine per host.

The engine exists twice - a flash-resident core on a badge and a MicroPython
native module on a desktop - so these tests pin down the seam the app owns and
run both paths through it:

* ``_CoreEngine`` against a fake ``mpos_core``: the surface and band handshake,
  the key queue, the file callbacks and the audio sink;
* ``_NatmodEngine`` against the real module where there is one;
* ``Doom`` itself against a fake engine: the key/touch mapping, the held-key
  rules (a keypad reports presses, a pointer reports both edges), pause/resume
  and the messages for a host that cannot run Doom.

Booting the real engine needs a WAD, which is not part of the repository, so
those tests skip when none is installed. Put one at ``internal_filesystem/doom1.wad``
(or /doom1.wad on the device) to run them.
"""

import os
import sys
import time
import unittest

import lvgl as lv

import mpos.ui
from mpos import AppManager, InputManager
from mpos.ui.view import remove_and_stop_current_activity, screen_stack

APP_DIR = "apps/com.micropythonos.doom"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import mpos.ui.native_activity as native_activity  # noqa: E402
import doom  # noqa: E402

try:
    import module_x64 as natmod
except Exception:  # noqa: BLE001 - no native module for this host
    natmod = None

SURFACE_WIDTH = 200
SURFACE_HEIGHT = 320
DRAW_BUFFER_BYTES = 28800

WAD_PATHS = ("doom1.wad", "/doom1.wad", "/sdcard/doom1.wad")


def _find_wad():
    for path in WAD_PATHS:
        try:
            open(path, "rb").close()
            return path
        except Exception:
            continue
    return None


def _wait_ms(ms):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        lv.task_handler()
        time.sleep_ms(5)


class _Event:
    def __init__(self, code=None, key=None):
        self._code = code
        self._key = key

    def get_code(self):
        return self._code

    def get_key(self):
        return self._key


class _FakeDisplay:
    """Just the two calls an engine makes when it picks a surface."""

    def __init__(self, width, height):
        self._w = width
        self._h = height

    def get_horizontal_resolution(self):
        return self._w

    def get_vertical_resolution(self):
        return self._h


class _FakeSurface:
    """A display surface that records invalidations instead of drawing."""

    panel_width = 240
    panel_height = 320

    def __init__(self, screen=None, width=None, height=None, buffer=None):
        self.width = width or SURFACE_WIDTH
        self.height = height or SURFACE_HEIGHT
        # Same rule as NativeDisplay: a band is one draw buffer of rows.
        self.rows_per_band = DRAW_BUFFER_BYTES // (self.width * 2)
        self.band_count = ((self.height + self.rows_per_band - 1)
                           // self.rows_per_band)
        self.stride = self.width * 2
        self.buffer = bytearray(self.width * self.height * 2)
        self._image_x = (self.panel_width - self.width) // 2
        self._image_y = (self.panel_height - self.height) // 2
        self._active = True
        self.invalidated = []
        self.flushed = 0
        self.bands = 0
        self.frames = 0

    def begin(self):
        self._active = True

    def end(self):
        self._active = False

    def invalidate_band(self, band):
        self.invalidated.append(band)

    def invalidate_all(self):
        pass

    def flush(self):
        self.flushed += 1

    def present_all(self, render, flush=True):
        for band in range(self.band_count):
            render(band)
        self.frames += 1


class _FakeEngine:
    """Records what the activity asks of an engine."""

    name = "fake"

    def __init__(self, size=(SURFACE_WIDTH, SURFACE_HEIGHT)):
        self.size = size
        self.started = []
        self.ticks = 0
        self.keys = []
        self.resumes = 0
        self.pauses = 0
        self.stops = 0
        self.quit = False

    def surface_size(self, display):
        return self.size

    def start(self, wad, surface):
        self.started.append((wad, surface))

    def resume(self):
        self.resumes += 1

    def pause(self):
        self.pauses += 1

    def tick(self, now):
        self.ticks += 1

    def key(self, code, pressed):
        self.keys.append((code, pressed))

    def stop(self):
        self.stops += 1


class _FakeExtent:
    """The two calls the app makes on the way to a mapped core."""

    XIP_ALIGN_BLOCKS = 16

    def available(self):
        return True

    def ensure(self, path, align=1, defrag_first=True, progress=None):
        return (0x1000, 0x2000, 0xDEADBEEF)


def _fake_wad(name="doom1.wad"):
    return doom._WadSource(name, 1805391, path=name)


class _FakeCore:
    """Records what the core engine asks of mpos_core."""

    def __init__(self):
        self.started = None
        self.ticks = 0
        self.stops = 0
        self.quit = False

    def start(self, *args):
        self.started = args

    def tick(self, now):
        self.ticks += 1

    def stop(self):
        self.stops += 1

    def mapped(self):
        return 0x43000000

    def mapped_size(self):
        return 0x20000

    def abi_version(self):
        return 6

    def audio_mix(self, buffer):
        for index in range(len(buffer)):
            buffer[index] = 1

    def quit_requested(self):
        return self.quit



class TestTheEngineSpeaksDoomsProtocol(unittest.TestCase):

    def test_the_native_module_exposes_the_engine_api(self):
        if natmod is None:
            self.skipTest("no native module for this host")
        for name in ("create", "tick", "frame", "palette", "blit_band",
                     "key", "width", "height"):
            self.assertTrue(hasattr(natmod, name), "missing %s" % name)

    def test_the_native_module_frame_is_paletted_320x200(self):
        if natmod is None:
            self.skipTest("no native module for this host")
        self.assertEqual(natmod.width(), doom.GAME_WIDTH)
        self.assertEqual(natmod.height(), doom.GAME_HEIGHT)

    def test_both_engines_take_dooms_own_key_codes(self):
        # The app sends one set of codes; a module that renumbered them would
        # silently misbind every control.
        if natmod is None:
            self.skipTest("no native module for this host")
        for attribute, code in (
                ("KEY_LEFT", doom.KEY_LEFT), ("KEY_RIGHT", doom.KEY_RIGHT),
                ("KEY_UP", doom.KEY_UP), ("KEY_DOWN", doom.KEY_DOWN),
                ("KEY_USE", doom.KEY_USE), ("KEY_FIRE", doom.KEY_FIRE),
                ("KEY_ENTER", doom.KEY_ENTER),
                ("KEY_ESCAPE", doom.KEY_ESCAPE)):
            self.assertEqual(getattr(natmod, attribute), code, attribute)


class TestCoreEngine(unittest.TestCase):
    """The badge path, against a fake mpos_core."""

    def setUp(self):
        self.core = _FakeCore()
        self._real_core = sys.modules.get("mpos_core")
        sys.modules["mpos_core"] = self.core
        self._real = {
            "find_engine": doom.find_engine,
            "extent": doom.extent,
            "prefs_dir": doom.prefs_dir,
        }
        doom.find_engine = lambda: ("/apps/com.micropythonos.doom/esp32s3.xip",
                                    "esp32s3.xip")
        doom.extent = _FakeExtent()
        doom.prefs_dir = lambda: "/prefs/com.micropythonos.doom"
        self.engine = doom._CoreEngine()
        self.surface = _FakeSurface()
        self._real_pointer_xy = InputManager.pointer_xy

    def tearDown(self):
        doom.find_engine = self._real["find_engine"]
        doom.extent = self._real["extent"]
        doom.prefs_dir = self._real["prefs_dir"]
        if self._real_core is not None:
            sys.modules["mpos_core"] = self._real_core
        else:
            sys.modules.pop("mpos_core", None)

    def test_start_passes_the_surface_and_the_band_height(self):
        self.engine.start(_fake_wad(), self.surface)

        self.assertIsNotNone(self.core.started, "the core was not started")
        args = self.core.started
        self.assertEqual(args[0], doom.CORE_PARTITION)
        self.assertEqual(args[9], "doom1.wad")
        self.assertEqual(args[10], SURFACE_WIDTH)
        self.assertEqual(args[11], SURFACE_HEIGHT)
        # The core draws straight into the surface buffer, one display band at a
        # time: that is what overlaps the transfer with the next conversion.
        self.assertIs(args[12], self.surface.buffer)
        self.assertEqual(args[13], self.surface.rows_per_band)
        # The extent's CRC is checked before the blob is mapped executable, and
        # the engine writes its config next to the app, not in the cwd.
        self.assertEqual(args[14], 0xDEADBEEF)
        self.assertEqual(args[15], "/prefs/com.micropythonos.doom")

    def test_a_portrait_panel_gets_the_frame_rotated(self):
        width, height = self.engine.surface_size(_FakeDisplay(240, 320))
        self.assertEqual((width, height), (doom.GAME_HEIGHT, doom.GAME_WIDTH))

    def test_a_landscape_panel_gets_the_frame_unrotated(self):
        # The fri3d 2026 ends up 320x240 after its rotation, so the core must
        # not transpose: a 320x200 surface is the request.
        width, height = self.engine.surface_size(_FakeDisplay(320, 240))
        self.assertEqual((width, height), (doom.GAME_WIDTH, doom.GAME_HEIGHT))

    def test_a_square_panel_gets_the_frame_scaled_to_three_quarters(self):
        # Neither orientation fits 240x240, so the core samples Doom's own
        # 320x200 into 240x150: same 4:3 picture, 45 px of panel left over.
        width, height = self.engine.surface_size(_FakeDisplay(240, 240))
        self.assertEqual((width, height), (240, 150))

    def test_a_panel_too_small_to_scale_says_so(self):
        # Below half scale the text is unreadable, so refuse instead of drawing
        # something nobody can use.
        with self.assertRaises(RuntimeError) as ctx:
            self.engine.surface_size(_FakeDisplay(120, 120))
        self.assertIn("320x200", str(ctx.exception))
        self.assertIn("120x120", str(ctx.exception))

    def test_a_band_with_pixels_is_copied_and_flushed(self):
        self.engine.start(_fake_wad(), self.surface)
        self.engine._present_band(72, 2, b"\x01\x02\x03\x04")

        start = 72 * SURFACE_WIDTH * 2
        self.assertEqual(bytes(self.surface.buffer[start:start + 4]),
                         b"\x01\x02\x03\x04")
        self.assertEqual(self.surface.invalidated, [1])  # row 72 is in band 1
        self.assertEqual(self.surface.flushed, 1)

    def test_a_band_without_pixels_is_only_flushed(self):
        self.engine.start(_fake_wad(), self.surface)
        before = bytes(self.surface.buffer[0:4])
        self.engine._present_band(0, 72, None)

        self.assertEqual(bytes(self.surface.buffer[0:4]), before)
        self.assertEqual(self.surface.invalidated, [0])
        self.assertEqual(self.surface.flushed, 1)

    def test_a_paused_surface_is_not_flushed(self):
        self.engine.start(_fake_wad(), self.surface)
        self.surface.end()
        self.engine._present_band(0, 72, None)
        self.assertEqual(self.surface.invalidated, [])
        self.assertEqual(self.surface.flushed, 0)

    def test_the_key_queue_encodes_the_press_bit(self):
        self.engine.key(doom.KEY_ESCAPE, True)
        self.engine.key(doom.KEY_ESCAPE, False)
        self.assertEqual(self.engine._poll_key(), doom.KEY_ESCAPE | 0x100)
        self.assertEqual(self.engine._poll_key(), doom.KEY_ESCAPE)
        self.assertEqual(self.engine._poll_key(), -1)

    def test_the_wad_is_read_through_micropython_files(self):
        import os
        path = "doom1.wad"
        if not os.path.exists(path):
            self.skipTest("no WAD installed")
        buffer = bytearray(16)
        read = self.engine._read_file(path, 0, buffer)
        self.assertEqual(read, 16)
        self.assertEqual(self.engine._file_size(path), os.stat(path)[6])
        self.assertEqual(self.engine._file_size("not-a-wad"), -1)
        self.assertEqual(self.engine._read_file("not-a-wad", 0, buffer), -1)

    def test_stop_releases_the_core_and_the_files(self):
        self.engine.start(_fake_wad(), self.surface)
        self.engine.stop()
        self.assertTrue(self.core.stops > 0)
        self.assertEqual(self.engine._files, {})
        self.assertEqual(self.engine._keys, [])

    def test_the_core_can_ask_the_app_to_close(self):
        # ABI 7: the engine cannot close the activity itself, so it asks.
        self.engine.start(_fake_wad(), self.surface)
        self.core.quit = True
        self.engine.tick(1234)
        self.assertTrue(self.engine.quit)

    def test_pausing_drops_the_events_that_were_still_queued(self):
        # Nothing ticks a core while the activity is paused: an event left in
        # the queue would be replayed, a minute later, on resume.
        self.engine.start(_fake_wad(), self.surface)
        self.engine.key(doom.KEY_LEFT, True)
        self.engine.pause()
        self.assertEqual(self.engine._keys, [])

    # -- audio ------------------------------------------------------------

    def test_the_core_mixes_into_the_hosts_buffer(self):
        # The sink itself belongs to NativeActivity; the engine only fills the
        # buffer with its mixer (core_sound.c through the ABI).
        self.engine.start(_fake_wad(), self.surface)
        buffer = bytearray(2048)
        self.engine.audio_mix(buffer)
        self.assertTrue(any(buffer), "the mixer returned silence")


class TestNatmodEngine(unittest.TestCase):
    """The desktop path: the real module's frame, and the band loop."""

    def setUp(self):
        self._real_prefs_dir = doom.prefs_dir
        doom.prefs_dir = lambda: "/prefs/com.micropythonos.doom"
        if natmod is None:
            self.skipTest("no native module for this host")

    def tearDown(self):
        doom.prefs_dir = self._real_prefs_dir

    def test_the_surface_is_dooms_own_frame(self):
        if natmod is None:
            self.skipTest("no native module for this host")
        engine = doom._NatmodEngine()
        self.assertEqual(engine.surface_size(_FakeDisplay(240, 320)),
                         (doom.GAME_WIDTH, doom.GAME_HEIGHT))

    def test_the_module_can_ask_to_close_the_app(self):
        if natmod is None:
            self.skipTest("no native module for this host")

        class _Engine:
            def __init__(self):
                self.ticks = 0

            def tick(self, now):
                self.ticks += 1

            def quit_requested(self):
                return True

        presented = []

        class _Surface:
            rows_per_band = 10

            def present_all(self, render):
                presented.append(True)

        engine = doom._NatmodEngine()
        engine._doom = _Engine()
        engine._surface = _Surface()
        engine.tick(time.ticks_ms())

        self.assertTrue(engine.quit)
        # Nothing is drawn once the engine has asked to close.
        self.assertEqual(presented, [])

    def test_start_hands_the_surface_to_the_module(self):
        if natmod is None:
            self.skipTest("no native module for this host")

        class _Engine:
            def __init__(self):
                self.created = None
                self.surface_args = None

            def create(self, wad, mb, config_dir=None):
                self.created = (wad, mb, config_dir)

            def surface(self, *args):
                self.surface_args = args

        engine = doom._NatmodEngine()
        module = _Engine()
        engine._doom = module
        surface = _FakeSurface(width=doom.GAME_WIDTH, height=doom.GAME_HEIGHT)
        engine.start(doom._WadSource("doom1.wad", 10, path="doom1.wad"), surface)

        self.assertEqual(module.created, ("doom1.wad", doom.ZONE_MB,
                                          "/prefs/com.micropythonos.doom"))
        # The module converts and flushes band by band, exactly like the core:
        # it gets the buffer, its shape, the band height and one callback.
        self.assertEqual(
            module.surface_args,
            (surface.buffer, doom.GAME_WIDTH, doom.GAME_HEIGHT,
             surface.rows_per_band, engine._present))
        self.assertTrue(callable(module.surface_args[4]))

    def test_the_module_mixes_into_the_hosts_buffer(self):
        if natmod is None:
            self.skipTest("no native module for this host")

        class _Engine:
            def __init__(self):
                self.mixed = 0

            def audio_mix(self, buffer):
                self.mixed += 1
                for index in range(len(buffer)):
                    buffer[index] = 7
                return len(buffer) // 2

        engine = doom._NatmodEngine()
        engine._doom = _Engine()
        buffer = bytearray(64)
        engine.audio_mix(buffer)
        self.assertEqual(engine._doom.mixed, 1)
        self.assertTrue(all(value == 7 for value in buffer))

    def test_a_presented_band_is_invalidated_and_flushed(self):
        engine = doom._NatmodEngine()
        surface = _FakeSurface(width=doom.GAME_WIDTH, height=doom.GAME_HEIGHT)
        surface.panel_width = 320
        surface.panel_height = 240
        engine._surface = surface

        engine._present_band(surface.rows_per_band, surface.rows_per_band)
        self.assertEqual(surface.invalidated, [1])
        self.assertEqual(surface.flushed, 1)

    def test_stopping_clears_the_surface_and_the_callback(self):
        if natmod is None:
            self.skipTest("no native module for this host")

        class _Engine:
            def surface(self, *args):
                self.cleared = args[0] is None

        engine = doom._NatmodEngine()
        module = _Engine()
        engine._doom = module
        engine._present = lambda y, rows: None
        engine.stop()
        self.assertTrue(module.cleared)
        self.assertIsNone(engine._present)


class TestDoomOnAHostWithoutAnEngine(unittest.TestCase):

    def setUp(self):
        self._real_display = mpos.ui.main_display
        self._real_make = doom._make_engine
        self._real_native_display = native_activity.NativeDisplay
        self._real_prefs_dir = doom.prefs_dir
        doom.prefs_dir = lambda: "/prefs/com.micropythonos.doom"
        mpos.ui.main_display = _FakeDisplay(240, 320)
        native_activity.NativeDisplay = _FakeSurface
        self.activity = doom.Doom()
        # setContentView resumes the activity, which would boot the real engine;
        # these tests decide when the engine is picked.
        self.activity._started = True
        self.activity.onCreate()

    def tearDown(self):
        doom._make_engine = self._real_make
        doom.prefs_dir = self._real_prefs_dir
        native_activity.NativeDisplay = self._real_native_display
        mpos.ui.main_display = self._real_display
        self.activity._clear_hint()

    def _start_with(self):
        self.activity._started = False

    def test_the_engine_is_chosen_per_host(self):
        # A WAD that exists on any checkout: the unpacked doom1.wad is a
        # developer artefact (gitignored), so give the launch one of our own.
        path = "test-engine-choice.wad"
        with open(path, "wb") as f:
            f.write(b"IWAD")
        fake = _FakeEngine()
        doom._make_engine = lambda: fake
        real_find_wad = doom.find_wad
        doom.find_wad = lambda intent=None: path
        self._start_with()
        try:
            self.activity.onResume(None)
        finally:
            doom.find_wad = real_find_wad
            os.remove(path)
        self.assertIs(self.activity.get_stats()["engine"], "fake")
        self.assertEqual(fake.started[0][0].name, path)
        self.activity.onPause(None)

    def test_a_firmware_without_the_core_says_so(self):
        def unavailable():
            raise RuntimeError("no Doom engine in this firmware (no mpos_core)")

        doom._make_engine = unavailable
        self._start_with()
        self.activity.onResume(None)
        self.assertIsNotNone(self.activity.error)
        self.assertIn("no Doom engine", self.activity.hint.get_text())
        # A message stays on screen; it is not the six-second hint.
        self.assertEqual(self.activity._hint_until, 0)
        self.activity._expire_hint(time.ticks_add(time.ticks_ms(), 60000))
        self.assertIsNotNone(self.activity.hint)

    def test_a_missing_wad_says_so(self):
        doom._make_engine = lambda: _FakeEngine()
        self._real_find_wad = doom.find_wad
        self._real_wad_zip = doom._wad_zip
        doom.find_wad = lambda intent=None: None
        doom._wad_zip = lambda: None
        self._start_with()
        try:
            self.activity.onResume(None)
        finally:
            doom.find_wad = self._real_find_wad
            doom._wad_zip = self._real_wad_zip
        self.assertIsNone(self.activity.error)
        self.assertIn("WAD", self.activity.hint.get_text())
        # Nothing to tick: the frame loop must not touch a missing engine.
        self.activity._drawframe()


class TestDoomActivity(unittest.TestCase):
    """The shared half: keys, touch, pause/resume. The engine is faked."""

    def setUp(self):
        self._real_display = mpos.ui.main_display
        self._real_native_display = native_activity.NativeDisplay
        self._real_pointer_xy = InputManager.pointer_xy
        mpos.ui.main_display = _FakeDisplay(240, 320)
        native_activity.NativeDisplay = _FakeSurface
        self.activity = doom.Doom()
        # onCreate ends in setContentView, which resumes the activity; these
        # tests supply an engine of their own instead of booting one.
        self.activity._started = True
        self.activity.onCreate()
        self.engine = _FakeEngine()
        self.activity.engine = self.engine
        self.activity._surface = _FakeSurface()
        self.activity._rotated = True
        self.activity._started = True
        self.activity._paused = False
        self.activity._wad = doom._WadSource("doom1.wad", 10, path="doom1.wad")

    def tearDown(self):
        mpos.ui.task_handler.remove_event_cb(self.activity._drawframe)
        self.activity._clear_hint()
        native_activity.NativeDisplay = self._real_native_display
        mpos.ui.main_display = self._real_display
        InputManager.pointer_xy = self._real_pointer_xy

    # -- the screen belongs to the game ---------------------------------

    def test_the_game_is_immersive_and_its_hint_fits_on_one_line(self):
        self.assertFalse(doom.Doom.system_gestures_enabled)
        self.assertTrue("\n" not in doom.HINT_TEXT)

    def test_the_touch_map_is_a_hint_and_goes_away(self):
        class _Overlay:
            def __init__(self):
                self.visible = True
                self.calls = []

            def set_visible(self, visible):
                self.visible = visible
                self.calls.append(visible)

        overlay = _Overlay()
        self.activity.overlay = overlay
        self.activity._overlay_until = time.ticks_add(time.ticks_ms(), 1)
        self.activity.on_frame(time.ticks_add(time.ticks_ms(), 50))
        self.assertFalse(overlay.visible, "the map did not hide")
        self.assertEqual(self.activity._overlay_until, 0)

        # Opening the menu brings it back for another few seconds.
        self.activity.on_key_event(ord("y"))
        self.assertTrue(overlay.visible)
        self.assertTrue(self.activity._overlay_until > 0)

    # -- buttons ----------------------------------------------------------

    def test_enter_selects_and_uses(self):
        self.activity.on_key_event(lv.KEY.ENTER)
        # ENTER is event-driven (a menu acts on the keydown), so it taps. USE is
        # state-driven and stays held: the engine drains its whole queue in one
        # frame, so a release straight after the press would cancel it before
        # the tic is built and the door would never open.
        self.assertEqual(self.engine.keys, [
            (doom.KEY_ENTER, True), (doom.KEY_ENTER, False),
            (doom.KEY_USE, True),
        ])
        self.assertIn(doom.KEY_USE, self.activity.holds.held())

    def test_the_a_letter_uses_like_enter(self):
        # A keyboard's "A" is the badge's use button; both open doors and both
        # select in a menu.
        self.activity.on_key_event(ord("a"))
        self.assertEqual(self.engine.keys, [
            (doom.KEY_ENTER, True), (doom.KEY_ENTER, False),
            (doom.KEY_USE, True),
        ])
        self.assertTrue(self.activity.holds.is_held(doom.KEY_USE))

    def test_fire_button_is_held_and_then_released(self):
        self.activity.on_key_event(ord("B"))
        # Fire also confirms: Doom's menus and its save-name prompt only take
        # Enter, and a gamepad has one action button.
        self.assertEqual(self.engine.keys, [
            (doom.KEY_ENTER, True), (doom.KEY_ENTER, False),
            (doom.KEY_FIRE, True),
        ])
        self.assertIn(doom.KEY_FIRE, self.activity.holds.held())

        # A repeat within the hold window must not send a second press.
        self.activity.on_key_event(ord("B"))
        self.assertEqual(self.engine.keys, [
            (doom.KEY_ENTER, True), (doom.KEY_ENTER, False),
            (doom.KEY_FIRE, True),
        ])

    def test_arrow_keys_turn_into_doom_arrows(self):
        self.activity.on_key_event(lv.KEY.LEFT)
        self.activity.on_key_event(lv.KEY.RIGHT)
        self.assertEqual(self.engine.keys, [
            (doom.KEY_LEFT, True), (doom.KEY_RIGHT, True),
        ])

    def test_the_badges_fire_letter_does_not_also_turn(self):
        # The fri3d 2026 expander reports B as NEXT *and* as the letter "B",
        # the letter first and in the same input read (LVGL takes NEXT for
        # focus tabbing, so the letter is how the app hears it). One button,
        # one action: firing must not turn as well.
        self.activity.on_key_event(ord("B"))
        self.activity.on_key_event(lv.KEY.NEXT)
        self.assertEqual(self.engine.keys, [
            (doom.KEY_ENTER, True), (doom.KEY_ENTER, False),
            (doom.KEY_FIRE, True),
        ])
        self.assertFalse(self.activity.holds.is_held(doom.KEY_RIGHT))

    def test_the_badges_menu_letter_does_not_also_turn(self):
        # Same for Y, which is PREV plus the letter and would otherwise step
        # the menu cursor as well as open it.
        self.activity.on_key_event(ord("Y"))
        self.activity.on_key_event(lv.KEY.PREV)
        self.assertEqual(self.engine.keys, [
            (doom.KEY_ESCAPE, True), (doom.KEY_ESCAPE, False),
        ])
        self.assertFalse(self.activity.holds.is_held(doom.KEY_LEFT))

    def test_a_bare_next_still_turns(self):
        # Keypads whose buttons only send NEXT/PREV keep turning with them.
        self.activity.on_key_event(lv.KEY.NEXT)
        self.assertEqual(self.engine.keys, [(doom.KEY_RIGHT, True)])

    def test_a_letter_only_suppresses_the_read_it_came_in(self):
        # The flag lives for one frame: a later, unrelated NEXT must still turn.
        self.activity.on_key_event(ord("B"))
        self.activity.on_frame(time.ticks_ms())
        self.activity.on_key_event(lv.KEY.NEXT)
        self.assertTrue(self.activity.holds.is_held(doom.KEY_RIGHT))

    def test_escape_opens_the_menu(self):
        self.activity.on_key_event(lv.KEY.ESC)
        self.assertEqual(self.engine.keys, [
            (doom.KEY_ESCAPE, True), (doom.KEY_ESCAPE, False),
        ])

    def test_y_opens_the_doom_menu(self):
        # Esc is the OS "back" key on the desktop and on the 2026 badge, so Y is
        # Doom's own menu.
        self.activity.on_key_event(ord("y"))
        self.assertEqual(self.engine.keys, [
            (doom.KEY_ESCAPE, True), (doom.KEY_ESCAPE, False),
        ])

    def test_a_keypad_press_is_released_on_the_next_frame(self):
        # A keypad reports presses and no releases, so the frame loop lets a
        # direction go when nobody refreshed it.
        self.activity.on_key_event(lv.KEY.LEFT)
        # Pretend the keypad reports the key up: the frame loop then lets go
        # once the press has outlived its one-tic minimum.
        self.activity.holds.source = lambda: ()
        self.activity.holds.held()[doom.KEY_LEFT][2] = time.ticks_add(
            time.ticks_ms(), -1000)
        self.activity._next_frame_ms = 0
        self.activity._drawframe()

        self.assertIn((doom.KEY_LEFT, False), self.engine.keys)
        self.assertEqual(doom.KEY_LEFT in self.activity.holds.held(), False)

    def test_a_pointer_holds_a_key_until_it_is_released(self):
        # A finger or mouse button that does not move sends no PRESSING, so a
        # held direction must not expire while the pointer is still down.
        x, y = self._panel(240, 180)
        self._touch(lv.EVENT.PRESSED, x, y)          # fire band
        self.activity.holds.tick(time.ticks_add(time.ticks_ms(), 10000))
        self.assertIn(doom.KEY_FIRE, self.activity.holds.held())
        self.assertEqual(self.engine.keys, [
            (doom.KEY_FIRE, True), (doom.KEY_ENTER, True),
            (doom.KEY_ENTER, False),
        ])

        self._touch(lv.EVENT.RELEASED, x, y)
        self.assertEqual(self.engine.keys, [
            (doom.KEY_FIRE, True), (doom.KEY_ENTER, True),
            (doom.KEY_ENTER, False), (doom.KEY_FIRE, False)])

    # -- touch ------------------------------------------------------------

    def test_the_game_asks_for_every_finger_the_panel_reports(self):
        # A multi-point panel would otherwise hand Doom one finger at a time.
        self.assertTrue(doom.Doom.touch_fingers)

    def _touch(self, code, x, y):
        InputManager.pointer_xy = staticmethod(lambda: (x, y))
        self.activity.on_pointer(code, x, y)

    def _panel(self, sx, sy):
        """Game point -> panel point: the inverse of the core's rotation."""
        return (self.activity._surface._image_x + (SURFACE_WIDTH - 1 - sy),
                self.activity._surface._image_y + sx)

    def _touch_game(self, code, sx, sy):
        x, y = self._panel(sx, sy)
        self._touch(code, x, y)

    def test_the_joystick_turns_and_walks_with_the_drag(self):
        self._touch_game(lv.EVENT.PRESSED, 80, 100)
        # Anchored, not a fixed pad: the press alone asks for no direction.
        self.assertEqual(self.engine.keys, [])

        self._touch_game(lv.EVENT.PRESSING, 40, 100)
        self.assertEqual(self.engine.keys, [(doom.KEY_LEFT, True)])

        # Dragging towards Doom's top walks forward and drops the turn.
        self._touch_game(lv.EVENT.PRESSING, 80, 40)
        self.assertEqual(self.engine.keys, [
            (doom.KEY_LEFT, True), (doom.KEY_LEFT, False),
            (doom.KEY_UP, True),
        ])

        self._touch_game(lv.EVENT.RELEASED, 80, 40)
        self.assertEqual(self.engine.keys[-1], (doom.KEY_UP, False))
        self.assertEqual(self.activity.holds.held(), {})

    def test_the_joystick_ignores_a_drag_inside_the_deadzone(self):
        self._touch_game(lv.EVENT.PRESSED, 80, 100)
        self._touch_game(lv.EVENT.PRESSING, 90, 108)
        self.assertEqual(self.engine.keys, [])
        self.assertEqual(self.activity.holds.held(), {})

    def test_the_fire_band_holds_fire_while_pressed(self):
        self._touch_game(lv.EVENT.PRESSED, 240, 180)
        # The same press confirms, so a save name can be accepted without a
        # keyboard.
        self.assertEqual(self.engine.keys, [
            (doom.KEY_FIRE, True), (doom.KEY_ENTER, True),
            (doom.KEY_ENTER, False),
        ])
        self.assertIn(doom.KEY_FIRE, self.activity.holds.held())

        self._touch_game(lv.EVENT.RELEASED, 240, 180)
        self.assertEqual(self.engine.keys[-1], (doom.KEY_FIRE, False))
        self.assertEqual(self.activity.holds.held(), {})

    def test_two_thumbs_walk_and_fire_at_once(self):
        # The left thumb owns the joystick, the right one the fire band: both
        # keys are held, and lifting one does not let go of the other.
        self.activity.on_touch_finger(
            0, lv.EVENT.PRESSED, *self._panel(80, 100))
        self.activity.on_touch_finger(
            1, lv.EVENT.PRESSED, *self._panel(240, 180))

        self.activity.on_touch_finger(
            0, lv.EVENT.PRESSING, *self._panel(40, 100))
        self.assertTrue(self.activity.holds.is_held(doom.KEY_LEFT))
        self.assertTrue(self.activity.holds.is_held(doom.KEY_FIRE))

        self.activity.on_touch_finger(
            0, lv.EVENT.RELEASED, *self._panel(40, 100))
        self.assertFalse(self.activity.holds.is_held(doom.KEY_LEFT))
        self.assertTrue(self.activity.holds.is_held(doom.KEY_FIRE))

        self.activity.on_touch_finger(
            1, lv.EVENT.RELEASED, *self._panel(240, 180))
        self.assertEqual(self.activity.holds.held(), {})

    def test_the_use_band_holds_use(self):
        self._touch_game(lv.EVENT.PRESSED, 240, 90)
        self.assertEqual(self.engine.keys, [(doom.KEY_USE, True)])
        self.assertIn(doom.KEY_USE, self.activity.holds.held())

    def test_the_menu_band_taps_escape(self):
        self._touch_game(lv.EVENT.PRESSED, 240, 20)
        self.assertEqual(self.engine.keys, [
            (doom.KEY_ESCAPE, True), (doom.KEY_ESCAPE, False),
        ])

    def test_a_thumb_at_the_panel_bottom_is_the_button_side(self):
        # The rotation guard: the panel's bottom edge is Doom's *right*, so it
        # must land in a button band, not on the joystick.
        x = self.activity._surface._image_x + 100
        self._touch(lv.EVENT.PRESSED, x, SURFACE_HEIGHT - 10)
        self.assertEqual(self.activity.zones.zone(), "use")

    def test_a_thumb_at_the_panel_top_is_the_joystick(self):
        x = self.activity._surface._image_x + 100
        self._touch(lv.EVENT.PRESSED, x, 10)
        self.assertEqual(self.activity.zones.zone(), "stick")
        self.assertEqual(self.engine.keys, [])

    # -- lifecycle --------------------------------------------------------

    def test_pausing_releases_held_keys_and_ends_the_surface(self):
        self._on_key_press()
        self.activity.onPause(None)

        self.assertEqual(self.engine.keys[-1], (doom.KEY_RIGHT, False))
        self.assertEqual(self.activity.holds.held(), {})
        self.assertEqual(self.engine.pauses, 1)
        self.assertFalse(self.activity._surface._active)

    def test_resuming_starts_the_engine_again_but_not_the_core(self):
        self.activity.onPause(None)
        self.activity.onResume(None)
        self.assertEqual(self.engine.resumes, 1)
        self.assertEqual(len(self.engine.started), 0, "the engine restarted")
        self.assertTrue(self.activity._surface._active)

    def test_the_engine_can_ask_the_app_to_close(self):
        closed = []
        self.activity.finish = lambda: closed.append(True)
        self.engine.quit = True
        self.activity._next_frame_ms = 0
        self.activity._drawframe()

        self.assertEqual(closed, [True], "the activity did not finish")
        self.assertTrue(self.activity._paused)
        # Idempotent: a second frame cannot finish it twice.
        self.activity._drawframe()
        self.assertEqual(closed, [True])

    def test_stopping_hands_the_engine_back(self):
        self.activity.onStop(None)
        self.assertEqual(self.engine.stops, 1)
        self.assertIsNone(self.activity.engine)
        self.assertFalse(self.activity._started)

    def _on_key_press(self):
        self.activity.on_key_event(lv.KEY.RIGHT)
        self.assertIn(doom.KEY_RIGHT, self.activity.holds.held())

    # -- stats ------------------------------------------------------------

    def test_stats_count_the_keys_the_engine_took(self):
        self.activity.holds.tap(doom.KEY_ESCAPE)
        self.assertEqual(self.engine.keys, [
            (doom.KEY_ESCAPE, True), (doom.KEY_ESCAPE, False)])
        self.assertEqual(self.activity.get_stats()["keys"], 2)
        self.assertEqual(self.activity.get_stats()["engine"], "fake")


class TestDoomOnTheRealApp(unittest.TestCase):

    def setUp(self):
        if natmod is None:
            # These drive the native module itself (its key constants and
            # blit_band); on a badge the app runs the flash-resident core.
            self.skipTest("no native module for this host")
        self.wad = _find_wad()
        if self.wad is None:
            self.skipTest("no WAD installed (put one at doom1.wad)")
        self.assertTrue(AppManager.start_app("com.micropythonos.doom"))
        _wait_ms(1500)
        self.activity = None
        for entry in screen_stack:
            if type(entry[0]).__name__ == "Doom":
                self.activity = entry[0]
        self.assertIsNotNone(self.activity, "the Doom activity is not on the stack")

    def tearDown(self):
        while len(screen_stack) > 1:
            remove_and_stop_current_activity()

    def test_the_demo_renders_into_the_surface(self):
        stats = self.activity.get_stats()
        self.assertEqual(stats["wad"], doom._absolute(self.wad))
        self.assertEqual(stats["engine"], "natmod")
        self.assertTrue(stats["frames"] > 0, "no frames were presented")
        surface = self.activity._surface
        # Doom's demo draws a level: the surface must not be one flat colour.
        colours = set()
        for i in range(0, len(surface.buffer), 997):
            colours.add(surface.buffer[i])
            if len(colours) > 4:
                break
        self.assertTrue(len(colours) > 4, "the surface looks blank")

    def test_pausing_stops_the_frame_loop(self):
        self.activity.onPause(None)
        frames = self.activity.get_stats()["frames"]
        _wait_ms(300)
        self.assertEqual(self.activity.get_stats()["frames"], frames)
        self.activity.onResume(None)
        _wait_ms(300)
        self.assertTrue(self.activity.get_stats()["frames"] > frames,
                        "resuming did not restart the loop")

    def test_quitting_from_dooms_menu_leaves_the_app(self):
        # Doom's quit used to free its framebuffer under the running frame
        # loop; the engine asks the host to close the activity instead.
        for code in (natmod.KEY_ESCAPE, natmod.KEY_DOWN, natmod.KEY_DOWN,
                     natmod.KEY_DOWN, natmod.KEY_DOWN, natmod.KEY_DOWN):
            self.activity.holds.tap(code)
            _wait_ms(350)
        self.activity.holds.tap(natmod.KEY_ENTER)
        _wait_ms(1500)
        names = [type(entry[0]).__name__ for entry in screen_stack]
        self.assertEqual("Doom" in names, False,
                         "the app is still on the stack after quitting")

    def test_a_band_blit_writes_that_band_only(self):
        surface = self.activity._surface
        surface.buffer[:] = bytes(len(surface.buffer))
        natmod.blit_band(surface.buffer, 1, surface.rows_per_band)
        rows = surface.rows_per_band
        band_start = rows * surface.width * 2
        band_end = band_start + rows * surface.width * 2
        self.assertEqual(surface.buffer[:band_start], bytes(band_start),
                         "rows above the band were written")
        self.assertNotEqual(surface.buffer[band_start:band_end],
                            bytes(band_end - band_start),
                            "the band was not drawn")


class TestDoomOnTheRealDisplay(unittest.TestCase):

    def test_the_surface_is_letterboxed_on_the_panel(self):
        if mpos.ui.main_display is None:
            self.skipTest("no display")
        display = mpos.ui.main_display
        if (display.get_horizontal_resolution() < doom.GAME_WIDTH
                or display.get_vertical_resolution() < doom.GAME_HEIGHT):
            # A portrait badge is narrower than Doom's landscape frame; the app
            # rotates it into a 200x320 surface instead (see surface_size).
            self.skipTest("panel is smaller than Doom's landscape frame")
        screen = lv.obj()
        lv.screen_load(screen)
        try:
            from mpos.ui.native_display import NativeDisplay
            surface = NativeDisplay(screen, width=doom.GAME_WIDTH,
                                    height=doom.GAME_HEIGHT)
        finally:
            lv.screen_load(lv.obj())
        self.assertEqual(surface.width, doom.GAME_WIDTH)
        self.assertEqual(surface.height, doom.GAME_HEIGHT)
        if surface.display.get_vertical_resolution() > doom.GAME_HEIGHT:
            self.assertTrue(surface._image_y > 0, "the surface is not centred")


if __name__ == "__main__":
    unittest.main()
