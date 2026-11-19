"""Doom: one activity, one engine per host.

The engine is doomgeneric, built twice because the two hosts need different
things from it:

* a badge gets the **flash-resident core**: the engine is linked for a fixed
  address, stored as a littlefs2e extent in the app directory and mapped from
  flash through the cache (``c_mpos/core_abi.h``), so a Doom-sized engine never
  has to fit in executable RAM (~7 KB on an S3);
* a desktop gets the **native module** (``doom_x64.mpy``), an ordinary
  MicroPython module, because there is no MMU window to map a flash partition
  into and the blob is Xtensa code anyway.

Both adapters below are the same seven-method shape (``surface_size``,
``start``, ``tick``, ``key``, ``resume``, ``pause``, ``stop`` plus a ``quit``
flag), so everything above them is shared: ``mpos.ui.native_activity`` owns the
surface, the pacing, the labels and the frame loop, and this file is the game's
own business - which engine, which WAD, which controls.

Controls - touch (any touch panel). Hold the device sideways while playing:
the left thumb gets a joystick and the right thumb three bands.

    left half       joystick: drag left/right to turn, up/down to walk
    right, bottom   fire (hold to keep shooting)
    right, middle   use / open
    right, top      menu / back

Controls - keyboard, mouse and badge buttons:

    arrows / joystick   turn and walk
    Enter / A           use / open doors, and select in menus
    B or space          fire, and select in menus (the same button does both,
                        as on a console pad)
    Y                   Doom's menu
    Esc                 back to the launcher - the OS takes this one before
                        Doom sees it (on a badge that is the X button)
"""

import sys
import time

import lvgl as lv

from mpos import extent
from mpos.ui.input_manager import InputManager
from mpos.ui.native_activity import NativeActivity
from mpos.ui.native_input import ThumbZones
from doom_overlay import TouchOverlay

GAME_WIDTH = 320
GAME_HEIGHT = 200

# The engine blob is stored as a littlefs2e extent in the app directory and
# mapped from there; it is not read through the filesystem at run time.
CORE_ALIGN_BLOCKS = 16  # 64 KiB with 4 KiB blocks: the ESP32 MMU page

# Doom's own tic rate is 35, and the present is what limits a full-screen frame
# to ~30fps on the badge.
TARGET_FPS = 35

# The native module wants a zone heap; the badge has ~7 MB free after the core
# is loaded, the desktop plenty.
ZONE_MB = 4

# The core's mixer rate (core_sound.c), which is Doom's own 11025 Hz.
SAMPLE_RATE = 11025

# Doom's own key codes (doomkeys.h), not ASCII. Both engines take these.
KEY_LEFT = 0xAC
KEY_RIGHT = 0xAE
KEY_UP = 0xAD
KEY_DOWN = 0xAF
KEY_USE = 0xA2
KEY_FIRE = 0xA3
KEY_ENTER = 13
KEY_ESCAPE = 27

HINT_TEXT = "Hold sideways: the outlined areas are touch controls"
# The zone map is a hint, not chrome: it is shown at start and whenever the
# menu opens, then hidden so a heavy frame keeps its whole refresh slot.
TOUCH_HINT_MS = 6000


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


def find_core():
    """Path of the core blob, or None. The app directory is authoritative."""
    candidates = (
        _app_directory() + "/core.bin",
        "apps/com.micropythonos.doom/core.bin",
        "/apps/com.micropythonos.doom/core.bin",
        "core.bin",
    )
    for path in candidates:
        try:
            open(path, "rb").close()
            return path
        except Exception:
            continue
    return None


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
    """The engine as a littlefs2e extent (badge).

    The blob is a contiguous extent in the app directory; mpos_core maps the
    run at the address it was linked for, so it executes from flash with no
    copy and no executable RAM. The core draws straight into the surface
    buffer one display band at a time and calls back for the panel transfer,
    so the previous band's SPI transfer runs while the next one is being
    converted. It reads the WAD through MicroPython file objects and mixes its
    own sound, which the host pulls.
    """

    name = "core"
    quit = False

    def __init__(self):
        import mpos_core
        self._core = mpos_core
        self._surface = None
        self._keys = []
        self._files = {}
        # ABI 7 added the request; an older core cannot make one.
        self._quit_query = getattr(mpos_core, "quit_requested", None)

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
        core = find_core()
        if core is None:
            raise OSError("doom: core.bin is missing")
        offset, length, crc = extent.ensure(
            core, align=CORE_ALIGN_BLOCKS, defrag_first=True)
        self._core_file = core
        self._core.start(
            "vfs", offset, length,
            *self._callbacks,
            wad, surface.width, surface.height,
            surface.buffer, surface.rows_per_band)
        if __debug__:
            print("doom: core %s extent at 0x%x, %d bytes (crc %08x), "
                  "mapped 0x%x, %d bytes, wad %s" % (
                      core, offset, length, crc,
                      self._core.mapped(), self._core.mapped_size(), wad))

    def resume(self):
        pass

    def pause(self):
        # A core is not ticked while the activity is paused, so anything still
        # queued here would be replayed on resume.
        self._keys = []

    def tick(self, now):
        self._core.tick(now)
        if self._quit_query is not None and self._quit_query():
            self.quit = True

    def audio_mix(self, buffer):
        self._core.audio_mix(buffer)

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

    # -- audio ------------------------------------------------------------

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

    Same shape as the core: the module keeps an 8-bit paletted framebuffer,
    converts each display band to RGB565 in C and calls back so the host can
    flush that band before the next one is converted. Nothing about the frame
    path is Python's business any more.
    """

    name = "natmod"

    def __init__(self):
        import doom_x64
        self._doom = doom_x64
        self._surface = None
        # The module holds the callback in C, which the collector does not
        # trace: keep the bound method alive here for as long as it is set.
        self._present = None
        self.quit = False

    def surface_size(self, display):
        # The module only ever presents Doom's landscape frame; it cannot
        # transpose it for a portrait panel.
        return GAME_WIDTH, GAME_HEIGHT

    def start(self, wad, surface):
        self._surface = surface
        self._doom.create(wad, ZONE_MB)
        self._present = self._present_band
        self._doom.surface(surface.buffer, surface.width, surface.height,
                           surface.rows_per_band, self._present)
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

    def audio_mix(self, buffer):
        self._doom.audio_mix(buffer)

    def key(self, code, pressed):
        self._doom.key(code, pressed)

    def stop(self):
        try:
            self._doom.surface(None, 0, 0, 0, None)
        except Exception:
            pass
        self._present = None
        self._surface = None

    def _present_band(self, y, rows):
        # y is the row offset of the band the module just drew into the buffer.
        self._surface.invalidate_band(y // self._surface.rows_per_band)
        self._surface.flush()


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


class Doom(NativeActivity):

    target_fps = TARGET_FPS
    hint_text = HINT_TEXT
    # The game covers the screen and owns the edges: the OS's top/left swipes
    # would otherwise steal the menu band and the joystick's outer edge.
    system_gestures_enabled = False
    # Both thumbs at once: walk with the left one and fire with the right one.
    touch_fingers = True
    # A keypad press is only a press (LVGL has no key release), so without this
    # holding the joystick turns for 180 ms and then waits for the keypad's
    # first repeat at 400 ms. The drivers that can report their real state make
    # it a continuous hold with no repeat delay.
    key_state = True
    # Both engines export the same 11025 Hz mixer; a piezo is refused because
    # Doom's broadband effects become a screech on one.
    audio_rate = SAMPLE_RATE
    audio_output_kind = "i2s"

    _wad = None
    _last_touch = None
    overlay = None
    _overlay_until = 0
    # The letter a button sent, when the board sends both the letter and the
    # NEXT/PREV it rides on (see on_key_event).
    _letter_key = None

    # -- engine -----------------------------------------------------------

    def make_engine(self):
        return _make_engine()

    def start_engine(self, surface):
        wad = find_wad(getattr(self, "intent", None))
        if wad is None:
            self.show_message(
                "Doom needs a WAD file.\n"
                "Put doom1.wad next to the app, or at /doom1.wad.")
            return False
        self._wad = wad
        self.engine.start(wad, surface)
        if InputManager.has_pointer():
            self.overlay = TouchOverlay(
                self, self.zones, GAME_WIDTH, GAME_HEIGHT)
            self._show_touch_hints()
        return True

    # -- input ------------------------------------------------------------

    def on_screen(self, screen):
        self.zones = ThumbZones({
            "left": KEY_LEFT, "right": KEY_RIGHT,
            "up": KEY_UP, "down": KEY_DOWN,
            "menu": KEY_ESCAPE, "use": KEY_USE, "fire": KEY_FIRE,
        }, self.holds)

    def _show_touch_hints(self, ms=TOUCH_HINT_MS):
        if self.overlay is not None:
            self.overlay.set_visible(True)
            self._overlay_until = time.ticks_add(time.ticks_ms(), ms)

    def on_resumed(self):
        # Returning from a dialog or the launcher is a good moment for the map.
        self._show_touch_hints()

    def on_paused(self):
        # No frame loop runs while paused, so no finger is down when the game
        # comes back: a hold that straddles the pause must not continue.
        self.zones.reset()

    def on_frame(self, now):
        # A letter and the NEXT/PREV it rides on arrive in one input read, so
        # the flag only has to survive until the frame that read belongs to.
        self._letter_key = None
        if (self.overlay is not None and self._overlay_until
                and time.ticks_diff(now, self._overlay_until) >= 0):
            self.overlay.set_visible(False)
            self._overlay_until = 0
        self.engine.tick(now)

    def on_key_event(self, key):
        if key == lv.KEY.LEFT:
            self.holds.hold(KEY_LEFT, key)
        elif key == lv.KEY.RIGHT:
            self.holds.hold(KEY_RIGHT, key)
        elif key == lv.KEY.UP:
            self.holds.hold(KEY_UP, key)
        elif key == lv.KEY.DOWN:
            self.holds.hold(KEY_DOWN, key)
        elif key == lv.KEY.NEXT:
            # The fri3d 2026 expander reports B as NEXT *and* as the letter
            # "B", because LVGL takes NEXT for focus tabbing and the app would
            # otherwise never hear it. The letter arrives first, in the same
            # input read: when it did, this is the B button, not a bare NEXT.
            # Firing is already handled there, and turning as well would make
            # one button do two things (in a menu, NEXT also means "down", so
            # B would move and select at once - this is why confirm felt
            # different from fire).
            if self._letter_key is None:
                self.holds.hold(KEY_RIGHT, key)
        elif key == lv.KEY.PREV:
            # Same for Y: the letter opens the menu, PREV would also turn left.
            if self._letter_key is None:
                self.holds.hold(KEY_LEFT, key)
        elif key in (lv.KEY.ENTER, ord("A"), ord("a")):
            # Enter selects in a menu (the engine acts on the event itself) and
            # opens doors in game, where the key has to stay down for at least
            # one tic: a press and a release drained in the same frame cancel
            # out before the tic is built. A keyboard gets the same action on
            # "A", which is the badge's use button.
            self.holds.tap(KEY_ENTER)
            self.holds.hold(KEY_USE, key)
        elif key == ord("B") or key == ord("b") or key == 0x20:
            self._letter_key = key
            self.holds.hold(KEY_FIRE, key)
        elif key in (lv.KEY.ESC, ord("Y"), ord("y"), lv.KEY.END):
            if key in (ord("Y"), ord("y")):
                self._letter_key = key
            # Esc would be the natural Doom menu key, but the OS claims it as
            # "back" on the desktop (board/linux.py) and on the 2026 badge, so
            # it never arrives here. Y is the menu, as on the badge.
            self._show_touch_hints()
            self.holds.tap(KEY_ESCAPE)

    def on_pointer(self, event_code, x, y):
        # A single-point panel (or the desktop mouse): one finger, number 0.
        self._touch(0, event_code, x, y)

    def on_touch_finger(self, finger, event_code, x, y):
        # A multi-point panel: the left thumb keeps its own direction while the
        # right one fires, because every finger has its own zone state.
        self._touch(finger, event_code, x, y)

    def _touch(self, finger, event_code, x, y):
        sx, sy = self.to_game(x, y)
        if event_code == lv.EVENT.PRESSED:
            zone = self.zones.pressed(sx, sy, finger)
            self._last_touch = (finger, "p", x, y, sx, sy)
            if zone == "menu":
                self._show_touch_hints()
        elif event_code == lv.EVENT.PRESSING:
            self.zones.moving(sx, sy, finger)
        elif event_code == lv.EVENT.RELEASED:
            zone = self.zones.released(sx, sy, finger)
            self._last_touch = (finger, "r", zone, x, y, sx, sy)

    # -- measurements -----------------------------------------------------

    def get_stats(self):
        stats = self.native_stats()
        stats["engine"] = self.engine.name if self.engine else None
        stats["wad"] = self._wad
        stats["touch"] = self._last_touch
        return stats
