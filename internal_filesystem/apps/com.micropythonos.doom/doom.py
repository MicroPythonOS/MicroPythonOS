"""Doom: one activity, one engine per host.

The engine is doomgeneric, built twice because the two hosts need different
things from it:

* a badge gets the **flash-resident core**: the engine is linked for a fixed
  address, lives in the ``retro-core`` partition and runs from flash through the
  cache (``c_mpos/core_abi.h``), so a Doom-sized engine never has to fit in
  executable RAM (~7 KB on an S3);
* a desktop gets the **native module** (``doom_x64.mpy``), an ordinary
  MicroPython module, because there is no MMU window to map a flash partition
  into and the blob is Xtensa code anyway.

Everything above the engine is shared, because MPOS already unifies the two
hosts: an SDL keyboard/mouse, a touch panel and a badge keypad all arrive as
the same LVGL events, and ``NativeDisplay`` is the only way either engine
reaches the panel. What differs lives behind ``_CoreEngine`` and
``_NatmodEngine``: how the engine starts, how a frame is drawn and where its
sound comes from.

Controls - touch (any touch panel). Hold the device sideways while playing:
the left thumb gets a joystick and the right thumb three bands.

    left half       joystick: drag left/right to turn, up/down to walk
    right, bottom   fire (hold to keep shooting)
    right, middle   use / open
    right, top      menu / back

Controls - keyboard, mouse and badge buttons:

    arrows / joystick   turn and walk
    Enter / A           use / open, and select in menus
    B or space          fire
    Y                   Doom's menu (Esc is the OS "back" key)
"""

import sys
import time

import lvgl as lv

import mpos.ui
from mpos import Activity, AudioManager, InputManager

from mpos.ui.native_display import NativeDisplay

GAME_WIDTH = 320
GAME_HEIGHT = 200

CORE_PARTITION = "retro-core"
CORE_PARTITION_SIZE = 0xF0000

# Doom's own tic rate is 35, and the present is what limits a full-screen frame
# to ~30fps on the badge.
TARGET_FPS = 35
FRAME_SLACK_MS = 5

# A keypad reports presses (and repeats) but no releases, so a direction is a
# timed hold. A pointer reports both edges and is held until it is let go.
HOLD_MS = 180
HINT_MS = 6000

# The native module wants a zone heap; the badge has ~7 MB free after the core
# is loaded, the desktop plenty.
ZONE_MB = 4

# The core's mixer rate (core_sound.c), which is Doom's own 11025 Hz.
SAMPLE_RATE = 11025

# Touch layout in Doom's own frame (320x200): the left thumb gets a joystick and
# the right thumb three bands.
STICK_WIDTH = 160
MENU_BOTTOM = 60
USE_BOTTOM = 120
STICK_DEADZONE = 16

# Doom's own key codes (doomkeys.h), not ASCII. Both engines take these.
KEY_LEFT = 0xAC
KEY_RIGHT = 0xAE
KEY_UP = 0xAD
KEY_DOWN = 0xAF
KEY_USE = 0xA2
KEY_FIRE = 0xA3
KEY_ENTER = 13
KEY_ESCAPE = 27


def _app_directory():
    path = globals().get("__file__")
    if path and "/" in path:
        return path.rsplit("/", 1)[0]
    return "apps/com.micropythonos.doom"


WAD_CANDIDATES = (
    "/sdcard/doom1.wad",
    "/sdcard/doom/doom1.wad",
    "/roms/doom/doom1.wad",
    "/doom1.wad",
    "doom1.wad",
    _app_directory() + "/doom1.wad",
)


def find_wad(intent=None):
    """First WAD that exists, or None."""
    if intent is not None:
        try:
            extra = intent.extras.get("wad") if hasattr(intent, "extras") else None
        except Exception:
            extra = None
        if extra:
            return extra
    for path in WAD_CANDIDATES:
        if path.startswith("/sdcard/"):
            try:
                from mpos import SDCardManager
                if not SDCardManager.mounted:
                    continue
            except Exception:
                continue
        try:
            open(path, "rb").close()
            return path
        except Exception:
            continue
    return None


class _CoreEngine:
    """The engine as a blob in the ``retro-core`` partition (badge).

    The core draws straight into the surface buffer one display band at a time
    and calls back for the panel transfer, so the previous band's SPI transfer
    runs while the next one is being converted. It reads the WAD through
    MicroPython file objects and mixes its own sound, which the host pulls.
    """

    name = "core"
    # The core reports quit itself (it returns to its title screen): the ABI
    # cannot ask the host to close the activity yet.
    quit = False

    def __init__(self):
        import mpos_core
        self._core = mpos_core
        self._surface = None
        self._keys = []
        self._files = {}
        self._sink = None
        self._audio_buffer = None
        self._audio_ms = 0

    def surface_size(self, display):
        # A portrait panel cannot show Doom's landscape frame, so the core
        # rotates it into a 200x320 surface; a landscape panel takes the frame
        # straight, which also keeps the touches unrotated.
        if display.get_vertical_resolution() > display.get_horizontal_resolution():
            return GAME_HEIGHT, GAME_WIDTH
        return GAME_WIDTH, GAME_HEIGHT

    def start(self, wad, surface):
        self._surface = surface
        # An earlier session may have left the core mapped (an activity torn
        # down by an exception never reaches onStop).
        try:
            self._core.stop()
        except Exception:
            pass
        # MicroPython does not trace C statics, so the callbacks live here for
        # as long as the core does.
        self._callbacks = (
            self._present_band, self._palette, self._poll_key,
            self._read_file, self._file_size, self._log)
        self._core.start(
            CORE_PARTITION, 0, CORE_PARTITION_SIZE,
            *self._callbacks,
            wad, surface.width, surface.height,
            surface.buffer, surface.rows_per_band)
        if __debug__:
            print("doom: core at 0x%x, %d bytes of text, wad %s" % (
                self._core.mapped(), self._core.mapped_size(), wad))
        self._open_audio()

    def resume(self):
        self._open_audio()

    def pause(self):
        self._close_audio()
        # A core is not ticked while the activity is paused, so anything still
        # queued here would be replayed on resume.
        self._keys = []

    def tick(self, now):
        self._core.tick(now)
        self._pump_audio(now)

    def key(self, code, pressed):
        self._keys.append((code, pressed))

    def stop(self):
        try:
            self._core.stop()
        except Exception:
            pass
        for file in self._files.values():
            try:
                file.close()
            except Exception:
                pass
        self._files = {}
        self._keys = []
        self._close_audio()

    # -- audio ------------------------------------------------------------

    def _open_audio(self):
        """Ask the OS for a speaker to put the core's mixed samples on.

        The user's choice in Settings -> Audio decides, with one exception this
        app makes for itself: Doom's effects are 11 kHz broadband PCM, and a
        piezo resonator with no output below 2 kHz turns that into a screech
        (and its 11 kHz timer interrupt costs frame time). So a buzzer is not
        offered this audio - a board with only a piezo stays silent, which is
        the better of the two. The sink takes int16 mono samples at SAMPLE_RATE.
        """
        if self._sink is not None:
            return
        output = AudioManager.get_default_output()
        if output is None or output.kind != "i2s":
            output = AudioManager.find_output_by_kind("i2s")
        if output is None:
            return
        try:
            # Firmware older than the PCM sink API has no open_pcm: the game
            # still runs, silently, which is better than refusing to start.
            self._sink = AudioManager.open_pcm(SAMPLE_RATE, output=output)
        except AttributeError:
            self._sink = None
            return
        except Exception as error:
            print("doom: audio init failed: %s" % (error,))
            self._sink = None
            return
        if self._sink is None or not self._sink.active:
            self._sink = None
            return
        self._audio_buffer = bytearray(2048 * 2)
        self._audio_ms = time.ticks_ms()

    def _close_audio(self):
        if self._sink is not None:
            try:
                self._sink.close()
            except Exception:
                pass
            self._sink = None
        self._audio_buffer = None

    def _pump_audio(self, now):
        """Give the sink the samples the frame loop's elapsed time needs."""
        if self._sink is None:
            return
        elapsed = time.ticks_diff(now, self._audio_ms)
        if elapsed <= 0:
            return
        samples = (elapsed * SAMPLE_RATE) // 1000
        if samples > 2048:
            samples = 2048
        elif samples < 64:
            return
        self._audio_ms = now
        view = memoryview(self._audio_buffer)[:samples * 2]
        self._core.audio_mix(view)
        try:
            self._sink.write(view)
        except Exception:
            # A short write means the ring is full; the next frame catches up.
            pass

    # -- ABI callbacks ----------------------------------------------------

    def _present_band(self, y, rows, data):
        """A band is ready: copy it (if the core sent pixels) and flush it.

        The core draws straight into ``surface.buffer`` and only announces the
        band, so this is where the panel transfer is started - before the core
        converts the next band.
        """
        if data is not None:
            start = y * self._surface.width * 2
            self._surface.buffer[start:start + len(data)] = data
        if not self._surface._active:
            return
        self._surface.invalidate_band(y // self._surface.rows_per_band)
        self._surface.flush()

    def _palette(self, entries):
        # The core converts its own palette; this is here for completeness.
        return bytes(entries * 2)

    def _poll_key(self):
        if not self._keys:
            return -1
        code, pressed = self._keys.pop(0)
        return (code & 0xFF) | (0x100 if pressed else 0)

    def _read_file(self, path, offset, into):
        file = self._files.get(path)
        if file is None:
            try:
                file = open(path, "rb")
            except Exception:
                return -1
            self._files[path] = file
        try:
            file.seek(offset)
            return file.readinto(into)
        except Exception:
            return -1

    @staticmethod
    def _file_size(path):
        import os
        try:
            return os.stat(path)[6]
        except Exception:
            return -1

    @staticmethod
    def _log(line):
        if __debug__:
            print("doom: %s" % line)


class _NatmodEngine:
    """The engine as a MicroPython native module (desktop).

    It keeps an 8-bit paletted 320x200 framebuffer and converts it to RGB565 one
    band at a time through ``blit_band``, which is the same panel loop the core
    does in C. It has no mixer, so there is no sound on this host.
    """

    name = "natmod"

    def __init__(self):
        import doom_x64
        self._doom = doom_x64
        self._surface = None
        self.quit = False

    def surface_size(self, display):
        # The module only ever presents Doom's landscape frame; it cannot
        # transpose it for a portrait panel.
        return GAME_WIDTH, GAME_HEIGHT

    def start(self, wad, surface):
        self._surface = surface
        self._doom.create(wad, ZONE_MB)
        if __debug__:
            print("doom: native module, wad %s" % (wad,))

    def resume(self):
        pass

    def pause(self):
        pass

    def tick(self, now):
        self._doom.tick(now)
        if self._doom.quit_requested():
            self.quit = True
            return
        self._surface.present_all(self._blit_band)

    def key(self, code, pressed):
        self._doom.key(code, pressed)

    def stop(self):
        pass

    def _blit_band(self, band):
        # One band: the panel transfer of the previous band overlaps this
        # conversion.
        self._doom.blit_band(
            self._surface.buffer, band, self._surface.rows_per_band)


def _make_engine():
    """The engine this host can run, or a RuntimeError saying why not."""
    if sys.platform == "esp32":
        try:
            return _CoreEngine()
        except Exception as error:
            raise RuntimeError(
                "no Doom engine in this firmware (%s); update MicroPythonOS"
                % (error,))
    try:
        return _NatmodEngine()
    except Exception as error:
        raise RuntimeError("cannot load the Doom engine (%s)" % (error,))


class Doom(Activity):

    screen = None
    hint = None
    _surface = None
    _engine = None
    _started = False
    _paused = True
    _next_frame_ms = 0
    _frame_interval_ms = 1000 // TARGET_FPS
    _frames = 0
    _fps = 0.0
    _fps_since = 0
    _fps_frames = 0
    _wad = None
    _error = None
    _keys_sent = 0
    _zone = None
    _stick = None
    _stick_h = 0
    _stick_v = 0
    _last_touch = None
    _hint_until = 0
    _rotated = False
    _leaving = False

    def onCreate(self):
        self.screen = lv.obj()
        self.screen.add_flag(lv.obj.FLAG.CLICKABLE)
        self.screen.add_event_cb(self._on_touch, lv.EVENT.ALL, None)
        self.screen.add_event_cb(self._on_key, lv.EVENT.KEY, None)
        # Without this the keyboard has nowhere to send its keys: the SDL
        # keypad driver delivers to the focused object of the default group.
        lv.group_get_default().add_obj(self.screen)

        self._held = {}
        self._keys_sent = 0
        self.setContentView(self.screen)

    def onResume(self, screen):
        self._paused = False
        if not self._started:
            self._started = True
            self._start()
        if self._error is not None or self._surface is None:
            return
        self._engine.resume()
        self._surface.begin()
        self._next_frame_ms = time.ticks_ms()
        self._fps_since = self._next_frame_ms
        self._fps_frames = 0
        mpos.ui.task_handler.add_event_cb(
            self._drawframe, mpos.ui.task_handler.TASK_HANDLER_FINISHED)

    def _start(self):
        try:
            engine = _make_engine()
            display = mpos.ui.main_display
            width, height = engine.surface_size(display)
            self._surface = NativeDisplay(
                self.screen, width=width, height=height)
            self._rotated = height > width
            self._engine = engine
            self._wad = find_wad(getattr(self, "intent", None))
            if self._wad is None:
                self._show_message(
                    "Doom needs a WAD file.\n"
                    "Put doom1.wad next to the app, or at /doom1.wad.")
                return
            engine.start(self._wad, self._surface)
        except Exception as error:
            # The engine is the one part of this app that can be missing: a
            # firmware without mpos_core, a board without the partition, a
            # desktop without the .mpy. Say so instead of a black screen.
            self._error = error
            print("doom: %s" % (error,))
            self._show_message(str(error))
            return
        self._show_hint()

    def onPause(self, screen):
        self._paused = True
        mpos.ui.task_handler.remove_event_cb(self._drawframe)
        # Nothing ticks the engine while paused, so a half-pressed direction is
        # released now instead of being replayed on resume.
        for code in list(self._held):
            self.key(code, False)
        self._held = {}
        self._zone = None
        self._stick = None
        # After the releases: the core drops whatever it was still holding, so
        # an event queued just before the pause is not replayed later.
        if self._engine is not None:
            self._engine.pause()
        if self._surface is not None:
            self._surface.end()

    def onStop(self, screen):
        # Leave the shared focus group clean: the framework also does this, but
        # an activity that is torn down without it leaves a widget behind.
        try:
            lv.group_get_default().remove_obj(self.screen)
        except Exception:
            pass
        if self._engine is not None:
            self._engine.stop()
        self._engine = None
        self._started = False
        self._wad = None

    def _drawframe(self, arg1=None, arg2=None):
        if self._paused or self._wad is None or self._error is not None:
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, self._next_frame_ms) < -FRAME_SLACK_MS:
            return
        self._next_frame_ms = time.ticks_add(now, self._frame_interval_ms)

        self._release_held(now)
        self._expire_hint(now)
        try:
            self._engine.tick(now)
        except Exception as error:
            # One traceback instead of one per frame, and stop drawing the stale
            # surface: an engine that faults must not take the UI down with it.
            self._error = error
            print("doom: tick failed: %s" % (error,))
            return

        if self._engine.quit:
            self._leave()
            return

        self._frames += 1
        self._fps_frames += 1
        elapsed = time.ticks_diff(now, self._fps_since)
        if elapsed >= 1000:
            frames = self._fps_frames
            self._fps = frames * 1000.0 / elapsed
            self._fps_frames = 0
            self._fps_since = now
            if __debug__ and frames:
                print("doom: %.1f fps" % (self._fps,))

    def _leave(self):
        """Close the activity because the engine asked for it (Doom's menu)."""
        if self._leaving:
            return
        self._leaving = True
        self._paused = True
        mpos.ui.task_handler.remove_event_cb(self._drawframe)
        self.finish()

    # -- input ------------------------------------------------------------

    def key(self, code, pressed=True):
        """Send one engine key event (see Doom's doomkeys.h)."""
        if self._engine is None:
            return
        self._keys_sent += 1
        self._engine.key(code, pressed)

    def tap(self, code):
        self.key(code, True)
        self.key(code, False)

    def _hold(self, code):
        """Press for HOLD_MS unless refreshed: a keypad reports presses only."""
        if code not in self._held:
            self.key(code, True)
        self._held[code] = time.ticks_add(time.ticks_ms(), HOLD_MS)

    def _press(self, code):
        """Press and keep down until _release: a pointer reports both edges."""
        if code not in self._held:
            self.key(code, True)
        self._held[code] = None

    def _release(self, code):
        if code in self._held:
            self.key(code, False)
            del self._held[code]

    def _release_held(self, now):
        for code, deadline in list(self._held.items()):
            if deadline is not None and time.ticks_diff(now, deadline) >= 0:
                self.key(code, False)
                del self._held[code]

    def _on_key(self, event):
        key = event.get_key()
        if key == lv.KEY.LEFT:
            self._hold(KEY_LEFT)
        elif key == lv.KEY.RIGHT:
            self._hold(KEY_RIGHT)
        elif key == lv.KEY.UP:
            self._hold(KEY_UP)
        elif key == lv.KEY.DOWN:
            self._hold(KEY_DOWN)
        elif key == lv.KEY.NEXT:
            self._hold(KEY_RIGHT)
        elif key == lv.KEY.PREV:
            self._hold(KEY_LEFT)
        elif key == lv.KEY.ENTER:
            # Enter selects in a menu (the engine acts on the event itself) and
            # opens doors in game, where the key has to stay down for at least
            # one tic: a press and a release drained in the same frame cancel
            # out before the tic is built.
            self.tap(KEY_ENTER)
            self._hold(KEY_USE)
        elif key == ord("B") or key == ord("b") or key == 0x20:
            self._hold(KEY_FIRE)
        elif key in (lv.KEY.ESC, ord("Y"), ord("y"), lv.KEY.END):
            # Esc would be the natural Doom menu key, but the OS claims it as
            # "back" on the desktop (board/linux.py) and on the 2026 badge, so
            # it never arrives here. Y is the menu, as on the badge.
            self.tap(KEY_ESCAPE)

    def _to_game(self, x, y):
        """Panel point -> Doom's own frame.

        The core turns Doom's 320x200 landscape frame into a portrait surface: a
        source pixel (sx, sy) lands at surface (199 - sy, sx), so the game's
        left-to-right axis runs down the panel and its forward axis runs across
        it. Touch coordinates arrive in panel space; until they are turned back,
        a thumb at the panel's left edge means Doom's *top*.
        """
        surface = self._surface
        dx = x - surface._image_x
        dy = y - surface._image_y
        if not self._rotated:
            return dx, dy
        return dy, (GAME_HEIGHT - 1) - dx

    def _stick_direction(self, sx, sy):
        """Turn/walk keys for a drag away from where the thumb landed."""
        horizontal = 0
        if sx < self._stick[0] - STICK_DEADZONE:
            horizontal = KEY_LEFT
        elif sx > self._stick[0] + STICK_DEADZONE:
            horizontal = KEY_RIGHT
        vertical = 0
        if sy < self._stick[1] - STICK_DEADZONE:
            vertical = KEY_UP         # drag towards Doom's top: forward
        elif sy > self._stick[1] + STICK_DEADZONE:
            vertical = KEY_DOWN
        return horizontal, vertical

    def _stick_apply(self, horizontal, vertical):
        """Hold the selected directions, drop the ones that left the zone."""
        for code in (self._stick_h, self._stick_v):
            if code and code != horizontal and code != vertical:
                self._release(code)
        if horizontal and horizontal != self._stick_h:
            self._press(horizontal)
        if vertical and vertical != self._stick_v:
            self._press(vertical)
        self._stick_h = horizontal
        self._stick_v = vertical

    def _on_touch(self, event):
        # LVGL also sends PRESSED/RELEASED to the focused object when ENTER is
        # pressed on a keypad, so only a pointer may drive the touch zones.
        indev = lv.indev_active()
        if indev is not None and indev.get_type() != lv.INDEV_TYPE.POINTER:
            return
        code = event.get_code()
        if code == lv.EVENT.PRESSED:
            x, y = InputManager.pointer_xy()
            self._expire_hint(time.ticks_ms())
            sx, sy = self._to_game(x, y)
            self._last_touch = ("p", x, y, sx, sy)
            if sx < STICK_WIDTH:
                # A joystick anchored where the thumb lands, so it does not
                # have to be hit: any touch on the left half starts a turn.
                self._zone = "stick"
                self._stick = (sx, sy)
                self._stick_apply(0, 0)
            elif sy < MENU_BOTTOM:
                self._zone = "menu"
                self.tap(KEY_ESCAPE)
            elif sy < USE_BOTTOM:
                self._zone = "use"
                self._press(KEY_USE)
            else:
                self._zone = "fire"
                self._press(KEY_FIRE)
        elif code == lv.EVENT.PRESSING:
            if self._zone == "stick" and self._stick is not None:
                x, y = InputManager.pointer_xy()
                sx, sy = self._to_game(x, y)
                horizontal, vertical = self._stick_direction(sx, sy)
                self._stick_apply(horizontal, vertical)
        elif code == lv.EVENT.RELEASED:
            x, y = InputManager.pointer_xy()
            sx, sy = self._to_game(x, y)
            if self._zone == "stick":
                self._stick_apply(0, 0)
                self._stick = None
            elif self._zone == "use":
                self._release(KEY_USE)
            elif self._zone == "fire":
                self._release(KEY_FIRE)
            self._last_touch = ("r", self._zone, x, y, sx, sy)
            self._zone = None

    # -- hint -------------------------------------------------------------

    def _add_label(self, text):
        label = lv.label(self.screen)
        label.set_text(text)
        label.set_style_bg_color(lv.color_hex(0x000000), lv.PART.MAIN)
        label.set_style_bg_opa(lv.OPA._70, lv.PART.MAIN)
        label.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        label.set_style_pad_all(6, lv.PART.MAIN)
        label.set_style_radius(6, lv.PART.MAIN)
        if self._rotated:
            # The core rotates the picture for a portrait panel, so an overlay
            # has to be rotated too: drawn as-is it would read sideways.
            label.set_style_transform_rotation(900, lv.PART.MAIN)
        label.align(lv.ALIGN.CENTER, 0, 0)
        label.remove_flag(lv.obj.FLAG.CLICKABLE)
        return label

    def _clear_hint(self):
        if self.hint is not None:
            self.hint.delete()
            self.hint = None

    def _show_hint(self):
        text = ("left thumb: turn / walk\n"
                "right thumb, bottom: fire\n"
                "right thumb, middle: use\n"
                "right thumb, top: menu")
        self._clear_hint()
        self.hint = self._add_label(text)
        self._hint_until = time.ticks_add(time.ticks_ms(), HINT_MS)

    def _show_message(self, text):
        # Not the hint: a missing engine or WAD stays on screen.
        self._clear_hint()
        self.hint = self._add_label(text)
        self._hint_until = 0

    def _expire_hint(self, now):
        if (self.hint is not None and self._hint_until
                and time.ticks_diff(now, self._hint_until) >= 0):
            self._clear_hint()

    # -- measurements -----------------------------------------------------

    def get_stats(self):
        return {
            "engine": self._engine.name if self._engine else None,
            "fps": self._fps,
            "frames": self._frames,
            "wad": self._wad,
            "error": self._error,
            "keys": self._keys_sent,
            "touch": self._last_touch,
            "bands": self._surface.band_count if self._surface else 0,
            "rows_per_band": self._surface.rows_per_band if self._surface else 0,
        }
