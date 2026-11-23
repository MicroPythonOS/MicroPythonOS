"""Doom: one activity, one engine per host.

The engine is doomgeneric, built twice because the two hosts need different
things from it:

* a badge gets the **flash-resident core** (``<soc>.xip``): the engine is
  linked for a fixed address, stored as a littlefs2e extent in the app
  directory and mapped from flash through the cache (``c_mpos/core_abi.h``), so
  a Doom-sized engine never has to fit in executable RAM (~7 KB on an S3);
* a desktop gets the **native module** (``module_<arch>.mpy``), an ordinary
  MicroPython module, because there is no MMU window to map a flash partition
  into and the blob is Xtensa code anyway.

Both adapters below are the same seven-method shape (``surface_size``,
``start``, ``tick``, ``key``, ``resume``, ``pause``, ``stop`` plus a ``quit``
flag), so everything above them is shared: ``mpos.ui.native_activity`` owns the
surface, the pacing, the labels and the frame loop, and this file is the game's
own business - which engine, which WAD, which controls.

The WAD ships deflated (``doom1.wad.zip``) and is inflated into a host buffer at
launch - never written to storage. The core reads it through the host's file
callbacks, the native module reads it from memory, and the buffer is freed
when the session ends so the core's zone gets that heap back.

Controls - touch (any touch panel). Hold the device sideways while playing:
the left thumb gets a joystick and the right thumb three bands.

    left half       joystick: drag left/right to turn, up/down to walk
    right, bottom   fire (hold to keep shooting)
    right, middle   use / open
    right, top      menu / back (hold it for the licenses)

Controls - keyboard, mouse and badge buttons:

    arrows / joystick   turn and walk
    Enter / A           use / open doors, and select in menus
    B or space          fire, and select in menus (the same button does both,
                        as on a console pad)
    Y                   Doom's menu
    Esc                 back to the launcher - the OS takes this one before
                        Doom sees it (on a badge that is the X button)
"""

import os
import sys
import time

import lvgl as lv

from mpos.ui.input_manager import InputManager
from mpos.ui.native_activity import NativeActivity
from mpos.ui.native_input import ThumbZones
from doom_overlay import TouchOverlay

try:
    # The host's platform keys (mpos.platform): which engine file this firmware
    # installs. A firmware before it cannot run a multi-platform package.
    from mpos import platform as mpos_platform
except ImportError:
    mpos_platform = None

try:
    from mpos import extent
except ImportError:
    extent = None

try:
    from mpos import zipasset
except ImportError:
    zipasset = None

GAME_WIDTH = 320
GAME_HEIGHT = 200

# The partition the core loader reads the extent from. The app's extent lives
# in the littlefs partition, not in a dedicated core partition.
CORE_PARTITION = "vfs"

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
# Holding the menu band instead of tapping it opens the licenses screen.
LICENSE_HOLD_MS = 600

WAD_ZIP_NAME = "doom1.wad.zip"
# The engine writes .default.cfg and .savegame/ relative to the working
# directory, so it runs inside the app's prefs.
PREFS_DIR = "prefs/com.micropythonos.doom"


def _app_directory():
    path = globals().get("__file__")
    if path and "/" in path:
        return path.rsplit("/", 1)[0]
    return "apps/com.micropythonos.doom"


def _absolute(path):
    """An absolute VFS path, resolved against the current directory."""
    if path.startswith("/"):
        return path
    cwd = os.getcwd()
    if cwd.endswith("/"):
        return cwd + path
    return cwd + "/" + path


def _makedirs(path):
    parts = path.split("/")
    acc = ""
    for part in parts:
        if not part:
            continue
        acc += "/" + part
        try:
            os.mkdir(acc)
        except OSError:
            pass


WAD_CANDIDATES = (
    "/sdcard/doom1.wad",
    "/sdcard/doom/doom1.wad",
    "/roms/doom/doom1.wad",
    "/doom1.wad",
    "doom1.wad",
    _app_directory() + "/doom1.wad",
)


def engine_candidates():
    """The engine file names this host installs (see mpos.platform)."""
    names = []
    if mpos_platform is not None:
        chip = mpos_platform.soc()
        if chip is not None:
            names.append(chip + ".xip")
        arch = mpos_platform.natmod_arch()
        if arch is not None:
            names.append("module_" + arch + ".mpy")
    return names


def find_engine():
    """(path, file name) of the installed engine, or a RuntimeError saying why."""
    if mpos_platform is None:
        raise RuntimeError(
            "Doom needs a newer MicroPythonOS (mpos.platform is missing)")
    names = engine_candidates()
    if not names:
        raise RuntimeError("Doom has no engine for this platform")
    for name in names:
        path = _absolute(_app_directory() + "/" + name)
        try:
            open(path, "rb").close()
        except OSError:
            continue
        return path, name
    raise RuntimeError(
        "Doom's engine (%s) is not installed; reinstall Doom"
        % (", ".join(names),))


def find_wad(intent=None):
    """First WAD that exists, as an absolute path, or None."""
    if intent is not None:
        try:
            extra = intent.extras.get("wad") if hasattr(intent, "extras") else None
        except Exception:
            extra = None
        if extra:
            return _absolute(extra)
    for path in WAD_CANDIDATES:
        if path.startswith("/sdcard/"):
            try:
                from mpos import SDCardManager
                if not SDCardManager.mounted:
                    continue
            except Exception:
                continue
        try:
            open(_absolute(path), "rb").close()
            return _absolute(path)
        except Exception:
            continue
    return None


class _WadSource:
    """The WAD the engine reads: a real file, or a buffer served by the host.

    The core's file callbacks are answered from ``buffer`` when it is set, so
    the engine reads the WAD from PSRAM; ``name`` is the path it asks for. The
    native module has no callbacks and always needs ``path``.
    """

    def __init__(self, name, size, path=None, buffer=None):
        self.name = name
        self.size = size
        self.path = path
        self.buffer = buffer

    def read_into(self, offset, into):
        """Serve ``into`` from the buffer; returns the byte count."""
        if offset < 0 or offset >= self.size:
            return 0
        count = self.size - offset
        if count > len(into):
            count = len(into)
        into[:count] = self.buffer[offset:offset + count]
        return count


def _wad_source_from_file(path):
    try:
        size = os.stat(path)[6]
    except OSError:
        return None
    return _WadSource(path, size, path=path)


def _wad_zip():
    path = _absolute(_app_directory() + "/" + WAD_ZIP_NAME)
    try:
        open(path, "rb").close()
    except OSError:
        return None
    return path


# The core's engine asks for a 3 MiB zone (`c_mpos/doom/core/doom_core.c`), and
# its libc's exit() only records the request instead of unwinding, so a failed
# allocation makes I_Error recurse until the stack dies and the badge resets.
# Refuse the launch here instead. Below the preferred size the engine can still
# fall back, but a block this small means something else is holding PSRAM.
ZONE_BYTES = 3 * 1024 * 1024


def _largest_free_block():
    """The biggest free block on the C heap (``None`` when unknown)."""
    try:
        import esp32
    except ImportError:
        return None
    try:
        largest = 0
        for entry in esp32.idf_heap_info(esp32.HEAP_DATA):
            # (total, free, largest_free, ...); small entries are internal RAM.
            if entry[0] > 1024 * 1024 and entry[2] > largest:
                largest = entry[2]
        return largest or None
    except Exception:
        return None


def _require_ram(size):
    """Refuse a launch that cannot fit, before the allocator fails mid-way."""
    needed = size + ZONE_BYTES
    largest = _largest_free_block()
    if largest is not None:
        if largest < needed:
            raise RuntimeError(
                "not enough free RAM for Doom's %d KB of engine memory; close "
                "another app or restart the badge (%d KB is free in one block, "
                "%d KB needed)" % (ZONE_BYTES // 1024, largest // 1024,
                                   needed // 1024))
        return
    try:
        import gc
        free = gc.mem_free()
    except Exception:
        return
    if free and free < needed:
        raise RuntimeError(
            "not enough free RAM for the WAD (%d KB free, %d KB needed plus "
            "the engine's zone)" % (free // 1024, size // 1024))


def _asset_buffer(size):
    """RAM for the inflated WAD, outside MicroPython's garbage collector.

    A bytearray that large makes the split GC heap add an area, and once any
    other object lives in that area it can never go back to the IDF heap -
    while the core's zone needs one contiguous 3 MiB block after the WAD is in
    RAM. A host without mpos_core (the desktop) has no such pressure, so a
    plain bytearray is fine there.
    """
    try:
        import mpos_core
    except ImportError:
        return bytearray(size)
    alloc = getattr(mpos_core, "buffer", None)
    if alloc is None:
        return bytearray(size)
    return alloc(size)


def _free_asset_buffer(buffer):
    """Give back a buffer from :func:`_asset_buffer`; a bytearray needs nothing."""
    if buffer is None:
        return
    try:
        import mpos_core
    except ImportError:
        return
    free = getattr(mpos_core, "buffer_free", None)
    if free is None:
        return
    try:
        free(buffer)
    except Exception as error:
        print("doom: cannot free the WAD buffer: %s" % (error,))


def prepare_wad(intent, loading):
    """The WAD source for this launch, or None when there is no WAD at all.

    A plain ``doom1.wad`` next to the app or on the SD card wins (it needs no
    extraction). Otherwise the bundled ``doom1.wad.zip`` is inflated into a
    buffer for this session and never written to storage: the core reads it
    through the host's file callbacks, the native module straight from memory.
    """
    path = find_wad(intent)
    if path is not None:
        return _wad_source_from_file(path)

    archive = _wad_zip()
    if archive is None:
        return None
    if zipasset is None:
        raise RuntimeError(
            "Doom needs a newer MicroPythonOS (no zipasset support)")

    size = zipasset.entry_size(archive)
    # The WAD and the zone have to fit at once, so refuse before the
    # three-second inflate rather than after it.
    _require_ram(size)

    def progress(done, total):
        loading("Unpacking WAD", done, total)

    progress(0, size)
    buffer = _asset_buffer(size)
    try:
        buffer, size = zipasset.load(archive, progress=progress, buffer=buffer)
    except Exception:
        _free_asset_buffer(buffer)
        raise
    return _WadSource(WAD_ZIP_NAME[:-4], size, buffer=buffer)


def prefs_dir():
    """The engine's config/save directory, absolute and created."""
    path = _absolute(PREFS_DIR)
    _makedirs(path)
    return path


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
    frame_size = (GAME_WIDTH, GAME_HEIGHT)

    def __init__(self):
        import mpos_core
        self._core = mpos_core
        self._surface = None
        # The activity's progress hook, set before start().
        self.progress = None
        self._keys = []
        self._files = {}
        self._wad = None
        # ABI 7 added the request; an older core cannot make one.
        self._quit_query = getattr(mpos_core, "quit_requested", None)

    def surface_size(self, display):
        # A portrait panel cannot show Doom's landscape frame, so the core
        # rotates it into a 200x320 surface; a landscape panel takes the frame
        # straight, which also keeps the touches unrotated. A panel too small
        # for either gets the same landscape picture at the largest quarter
        # scale that still fits (a 240x240 panel becomes 240x150): the core
        # samples the frame instead of letterboxing it.
        width = display.get_horizontal_resolution()
        height = display.get_vertical_resolution()
        if height > width:
            if GAME_HEIGHT <= width and GAME_WIDTH <= height:
                return GAME_HEIGHT, GAME_WIDTH
        elif GAME_WIDTH <= width and GAME_HEIGHT <= height:
            return GAME_WIDTH, GAME_HEIGHT
        quarter = min(width * 4 // GAME_WIDTH, height * 4 // GAME_HEIGHT)
        if quarter >= 2:
            return GAME_WIDTH * quarter // 4, GAME_HEIGHT * quarter // 4
        raise RuntimeError(
            "Doom needs a screen of at least 160x100 (or 320x200 unscaled); "
            "this panel is %dx%d" % (width, height))

    def start(self, wad, surface):
        self._surface = surface
        # An earlier session may have left the core mapped (an activity torn
        # down by an exception never reaches onStop).
        try:
            self._core.stop()
        except Exception:
            pass
        if extent is None or not extent.available():
            raise RuntimeError(
                "Doom needs a newer MicroPythonOS (no littlefs2e extent support)")
        # The WAD (if it was inflated) is in RAM by now, so this is the last
        # point at which a hopeless zone allocation can be turned into a
        # message instead of the engine's error path resetting the board.
        _require_ram(0)
        path, name = find_engine()
        if not name.endswith(".xip"):
            raise RuntimeError("Doom has no XIP core for this SoC")
        # MicroPython does not trace C statics, so the callbacks live here for
        # as long as the core does.
        self._callbacks = (
            self._present_band, self._palette, self._poll_key,
            self._read_file, self._file_size, self._log)
        # A sideloaded (or older-installer) engine is a normal file: convert it
        # once. The AppStore writes it as an extent at install time.
        offset, length, crc = extent.ensure(
            path, align=extent.XIP_ALIGN_BLOCKS, defrag_first=True,
            progress=self.progress)
        self._core_file = path
        self._wad = wad
        # The engine writes .default.cfg and .savegame/ here; it is absolute,
        # so the engine never needs the process working directory.
        self._config_dir = prefs_dir()
        self._core.start(
            CORE_PARTITION, offset, length,
            *self._callbacks,
            wad.name, surface.width, surface.height,
            surface.buffer, surface.rows_per_band, crc, self._config_dir)
        if __debug__:
            print("doom: core %s extent at 0x%x, %d bytes (crc %08x), "
                  "mapped 0x%x, %d bytes, wad %s" % (
                      path, offset, length, crc,
                      self._core.mapped(), self._core.mapped_size(), wad.name))

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
        self._wad = None

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
        if self._wad is not None and path == self._wad.name and self._wad.buffer is not None:
            return self._wad.read_into(offset, into)
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

    def _file_size(self, path):
        if self._wad is not None and path == self._wad.name and self._wad.buffer is not None:
            return self._wad.size
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
    frame_size = (GAME_WIDTH, GAME_HEIGHT)

    def __init__(self):
        _path, name = find_engine()
        if not name.startswith("module_") or not name.endswith(".mpy"):
            raise RuntimeError("Doom has no native module for this platform")
        module = name[:-4]
        self._doom = __import__(module)
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
        self._config_dir = prefs_dir()
        if wad.buffer is not None:
            # The WAD was inflated for this session; the module keeps the
            # bytes in memory instead of opening a file.
            self._doom.create_from_memory(wad.buffer, ZONE_MB, self._config_dir)
        elif wad.path is not None:
            self._doom.create(wad.path, ZONE_MB, self._config_dir)
        else:
            raise RuntimeError(
                "the native Doom engine needs the WAD in memory or on disk")
        self._present = self._present_band
        self._doom.surface(surface.buffer, surface.width, surface.height,
                           surface.rows_per_band, self._present)
        if __debug__:
            print("doom: native module, wad %s" % (wad.path,))

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
        try:
            # Drop the engine's pointer before the app frees the buffer.
            self._doom.clear_wad()
        except Exception:
            pass
        self._present = None
        self._surface = None
        self._config_dir = None

    def _present_band(self, y, rows):
        # y is the row offset of the band the module just drew into the buffer.
        self._surface.invalidate_band(y // self._surface.rows_per_band)
        self._surface.flush()


def _make_engine():
    """The engine this host can run, or a RuntimeError saying why not."""
    if mpos_platform is None:
        raise RuntimeError(
            "Doom needs a newer MicroPythonOS (mpos.platform is missing)")
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
    # When the menu band went down, for the licenses long press.
    _menu_since = 0

    # -- engine -----------------------------------------------------------

    def make_engine(self):
        return _make_engine()

    def _loading(self, text, done=0, total=0):
        """Show (and draw) what the launch is waiting for."""
        if total:
            text = "%s %d%%" % (text, (done * 100) // total)
        self.set_message(text)
        try:
            # The binding takes the display explicitly; a no-argument call
            # raises TypeError, and swallowing that silently is what made the
            # whole start-up look frozen (nothing repainted until the engine's
            # first frame).
            lv.refr_now(None)
        except Exception as error:
            print("doom: cannot repaint the launch message: %s" % (error,))

    def _extent_progress(self, phase, percent):
        """Repaint the launch message while an extent is defragmented."""
        if phase == extent.PHASE_SPACE or percent <= 0:
            self._loading("Defragmenting storage...")
        else:
            self._loading("Defragmenting storage... %d%%" % percent)

    def start_engine(self, surface):
        self._loading("Checking the Doom engine")
        try:
            wad = prepare_wad(
                getattr(self, "intent", None), self._loading)
        except Exception as error:
            self.show_message("Doom cannot start:\n%s" % (error,))
            return False
        if wad is None:
            self.show_message(
                "Doom needs a WAD file.\n"
                "Reinstall Doom, or put doom1.wad at /doom1.wad.")
            return False
        self._wad = wad
        self._loading("Starting the engine")
        self.engine.progress = self._extent_progress
        try:
            self.engine.start(wad, surface)
        except Exception:
            # Nothing will read the WAD again, and the message the base class
            # puts up can stay: give the RAM back before the player reads it.
            self._wad = None
            try:
                self.engine.stop()
            except Exception:
                pass
            _free_asset_buffer(wad.buffer)
            raise
        if self.hint is not None:
            self._clear_hint()
            self.show_hint(self.hint_text)
        if InputManager.has_pointer():
            self.overlay = TouchOverlay(
                self, self.zones, GAME_WIDTH, GAME_HEIGHT)
            self._show_touch_hints()
        return True

    # -- input ------------------------------------------------------------

    def on_screen(self, screen):
        # A firmware before the framework owns a black native screen still
        # hands the activity the theme's white, scrollable one: paint it here
        # so the letterbox is black and a drag the game ignores cannot scroll
        # the picture out of place. (Harmless where NativeActivity already
        # did the same thing.)
        screen.set_style_bg_color(lv.color_hex(0x000000), lv.PART.MAIN)
        screen.set_style_bg_opa(lv.OPA.COVER, lv.PART.MAIN)
        screen.remove_flag(lv.obj.FLAG.SCROLLABLE)
        screen.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
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

    def onStop(self, screen):
        # The engine drops its own WAD reference first, then the buffer goes
        # back to the heap the core's zone has to come from.
        super().onStop(screen)
        if self._wad is not None:
            _free_asset_buffer(self._wad.buffer)
            self._wad = None

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
            # Fire also confirms: Doom's menus and the save-name prompt only
            # take Enter, and a gamepad player has one "action" button. Enter
            # is harmless while playing; a key repeat must not repeat it, or a
            # held button would step through a whole menu.
            if not self.holds.is_held(KEY_FIRE):
                self.holds.tap(KEY_ENTER)
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
                self._menu_since = time.ticks_ms()
                self._show_touch_hints()
            if zone == "fire":
                # Every touch control that means "act" also means Enter, so a
                # save name can be confirmed without a keyboard.
                self.holds.tap(KEY_ENTER)
        elif event_code == lv.EVENT.PRESSING:
            self.zones.moving(sx, sy, finger)
        elif event_code == lv.EVENT.RELEASED:
            zone = self.zones.released(sx, sy, finger)
            self._last_touch = (finger, "r", zone, x, y, sx, sy)
            if (zone == "menu" and self._menu_since
                    and time.ticks_diff(time.ticks_ms(), self._menu_since)
                    >= LICENSE_HOLD_MS):
                self._menu_since = 0
                self._show_licenses()
            if zone == "menu":
                self._menu_since = 0

    def _show_licenses(self):
        try:
            import doom_legal
            doom_legal.start(self)
        except Exception as error:
            self.show_message("Cannot show the licenses: %s" % (error,))

    # -- measurements -----------------------------------------------------

    def get_stats(self):
        stats = self.native_stats()
        stats["engine"] = self.engine.name if self.engine else None
        stats["wad"] = self._wad.name if self._wad else None
        stats["touch"] = self._last_touch
        return stats
