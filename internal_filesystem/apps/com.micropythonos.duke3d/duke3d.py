"""Duke Nukem 3D for MicroPythonOS.

The engine is the DukeNano3D port of Chocolate Duke3D (the retro-go flavour,
which carries the performance and memory fixes this board needs). It ships as a
**flash-resident core**: the blob in this package is linked for fixed addresses
and executed from the app partition through the instruction cache, so a
Duke-sized engine needs neither executable RAM nor a copy into the Python heap
(see ``c_mpos/duke3d`` and ``c_mpos/core_abi.h``).

The GRP is the compacted shareware episode (E1L1-4). It ships deflated and is
inflated into a host buffer at launch - never written to storage - and the
engine reads it through the core's file callbacks. The buffer is freed when the
session ends.

Controls - touch. Hold the badge sideways:

    left half        drag to walk and turn
    right, top row   X crouch, Y use/open
    right, middle    A fire, B jump
    right, bottom    START menu, MENU next weapon

In the engine's menus the stick moves the cursor and A or Y confirm; START goes
back.
"""

import os
import sys

import lvgl as lv

from mpos.ui.native_activity import NativeActivity
from duke_controls import DukeTouch
from duke_overlay import TouchOverlay

try:
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

# Where the engine comes from. An installed app carries ``esp32s3.xip`` and the
# loader turns it into a contiguous littlefs2e extent inside the filesystem
# partition. A development badge can instead have the same blob flashed into
# the reserved retro-core partition (the layout has one for a retro engine),
# which costs no filesystem space - the app uses the file when it is there and
# falls back to the partition when it is not.
CORE_PARTITION = "vfs"
RETRO_CORE_PARTITION = "retro-core"
RETRO_CORE_SIZE = 0xF0000

# Duke's logic runs at 30 tics and a 320x200 frame is what limits the picture;
# the engine is ticked once per display frame.
TARGET_FPS = 30

# The name the engine opens. Its GRP loader is patched to ask for exactly this,
# and the core's read callback answers from the inflated buffer.
GRP_NAME = "duke3d.grp"
GRP_ZIP_NAME = "E1L1-4_compromise.grp.zip"

HINT_TEXT = "Hold sideways: left is walk/turn, right is the action pad"
TOUCH_HINT_MS = 8000

PREFS_DIR = "prefs/com.micropythonos.duke3d"


def _app_directory():
    path = globals().get("__file__")
    if path and "/" in path:
        return path.rsplit("/", 1)[0]
    return "apps/com.micropythonos.duke3d"


def _absolute(path):
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


def engine_candidates():
    """The engine file names this host installs (see mpos.platform)."""
    names = []
    if mpos_platform is not None:
        chip = mpos_platform.soc()
        if chip is not None:
            names.append(chip + ".xip")
    return names


def find_engine():
    """(path, file name) of the installed engine, or a RuntimeError saying why."""
    if mpos_platform is None:
        raise RuntimeError(
            "Duke Nukem 3D needs a newer MicroPythonOS (mpos.platform is missing)")
    names = engine_candidates()
    if not names:
        raise RuntimeError("this platform has no Duke3D engine build")
    for name in names:
        path = _absolute(_app_directory() + "/" + name)
        try:
            open(path, "rb").close()
        except OSError:
            continue
        return path, name
    return None, None


def _asset_buffer(size):
    """RAM for the inflated GRP, outside MicroPython's garbage collector.

    A bytearray this large makes the split GC heap add an area that can never
    be returned to the IDF heap, and the core's arena is allocated next to it;
    mpos_core.buffer is ordinary C memory with an explicit free.
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
        print("duke3d: cannot free the GRP buffer: %s" % (error,))


def prepare_grp(loading):
    """The inflated GRP, as (buffer, size); raises when it cannot be read."""
    archive = _absolute(_app_directory() + "/" + GRP_ZIP_NAME)
    try:
        open(archive, "rb").close()
    except OSError:
        raise RuntimeError(
            "Duke3D's data file (%s) is missing; reinstall the app"
            % (GRP_ZIP_NAME,))
    if zipasset is None:
        raise RuntimeError(
            "Duke Nukem 3D needs a newer MicroPythonOS (no zipasset support)")

    size = zipasset.entry_size(archive)
    loading("Unpacking Duke3D data", 0, size)
    buffer = _asset_buffer(size)

    def progress(done, total):
        loading("Unpacking Duke3D data", done, total)

    try:
        buffer, size = zipasset.load(archive, progress=progress, buffer=buffer)
    except Exception:
        _free_asset_buffer(buffer)
        raise
    return buffer, size


class _CoreEngine:
    """The engine as a littlefs2e extent (the badge)."""

    name = "core"
    quit = False
    frame_size = (GAME_WIDTH, GAME_HEIGHT)

    def __init__(self):
        import mpos_core
        self._core = mpos_core
        self._surface = None
        self._grp = None
        self._grp_size = 0
        self._keys = []
        self._io_count = 0
        self._callbacks = None
        self.quit = False
        self._quit_query = getattr(mpos_core, "quit_requested", None)

    def surface_size(self, display):
        # A portrait panel (240x320 logical, the badge held sideways) cannot
        # show the 320x200 frame untransposed, so the core turns it into a
        # 200x320 surface. A landscape panel gets the frame as it is. This is
        # the same rule the Doom core uses, and NativeActivity's touch mapping
        # undoes the rotation for the game's own coordinates.
        width = display.get_horizontal_resolution()
        height = display.get_vertical_resolution()
        if height > width:
            if GAME_HEIGHT <= width and GAME_WIDTH <= height:
                return GAME_HEIGHT, GAME_WIDTH
        elif GAME_WIDTH <= width and GAME_HEIGHT <= height:
            return GAME_WIDTH, GAME_HEIGHT
        raise RuntimeError(
            "Duke Nukem 3D needs a screen of at least 200x320 or 320x200; "
            "this panel is %dx%d" % (width, height))

    def start(self, grp, surface):
        self._surface = surface
        self._grp, self._grp_size = grp
        self.quit = False
        try:
            self._core.stop()
        except Exception:
            pass
        if extent is None or not extent.available():
            raise RuntimeError(
                "Duke Nukem 3D needs a newer MicroPythonOS (no littlefs2e extent support)")
        path, name = find_engine()
        # The collector does not trace the C-side callback pointers.
        self._callbacks = (
            self._present_band, self._palette, self._poll_key,
            self._read_file, self._file_size, self._log)
        if path is not None:
            if not name.endswith(".xip"):
                raise RuntimeError("Duke3D has no XIP core for this SoC")
            partition = CORE_PARTITION
            offset, length, crc = extent.ensure(
                path, align=extent.XIP_ALIGN_BLOCKS, defrag_first=True,
                progress=getattr(self, "progress", None))
        else:
            # A development badge with the blob flashed into its partition.
            partition = RETRO_CORE_PARTITION
            offset, length, crc = 0, RETRO_CORE_SIZE, 0
        config_dir = _absolute(PREFS_DIR)
        _makedirs(config_dir)
        # The engine runs its whole start-up (GRP index, palette, the first
        # level) inside init(); that is one blocking step of a few seconds, and
        # the activity is showing its loading message while it happens.
        self._core.start(
            partition, offset, length,
            *self._callbacks,
            GRP_NAME, surface.width, surface.height,
            surface.buffer, surface.rows_per_band, crc, config_dir)

    def resume(self):
        pass

    def pause(self):
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
        self._grp = None
        self._grp_size = 0
        self._keys = []
        self._io_count = 0
        self._callbacks = None

    # -- ABI callbacks ----------------------------------------------------

    def _present_band(self, y, rows, data):
        if data is not None:
            start = y * self._surface.width * 2
            self._surface.buffer[start:start + len(data)] = data
        if not self._surface._active:
            return
        self._surface.invalidate_band(y // self._surface.rows_per_band)
        try:
            self._surface.flush()
        except Exception as error:
            print("duke3d: present exception type=%s repr=%r"
                  % (type(error), error))
            sys.print_exception(error)
            raise

    def _palette(self, entries):
        return bytes(entries * 2)

    def _poll_key(self):
        if not self._keys:
            return -1
        code, pressed = self._keys.pop(0)
        return (code & 0xFF) | (0x100 if pressed else 0)

    def _read_file(self, path, offset, into):
        # The core yields to the scheduler itself (a sentinel through the log
        # callback, handled in C by the loader); sleeping from here would
        # re-enter MicroPython on a deep engine stack.
        if path == GRP_NAME and self._grp is not None and offset < self._grp_size:
            count = self._grp_size - offset
            if count > len(into):
                count = len(into)
            into[:count] = self._grp[offset:offset + count]
            return count
        return -1

    def _file_size(self, path):
        if path == GRP_NAME:
            return self._grp_size
        return -1

    def _log(self, line):
        # The "\x01yield" sentinel is consumed in C by the core loader before
        # it reaches Python; a line that still arrives starts with that byte.
        if line and line[0] == "\x01":
            return
        try:
            print("duke3d: %s" % line)
        except Exception:
            # The REPL can stop draining while the engine owns the CPU; a
            # failed log line must not become a failed frame.
            pass


class Duke3D(NativeActivity):
    """One activity, one engine: the flash-resident core."""

    target_fps = TARGET_FPS
    hint_text = HINT_TEXT
    hint_ms = TOUCH_HINT_MS
    # The GT911 reports five points, so both thumbs get their own finger.
    touch_fingers = True
    # No audio output on the panels this engine targets; the core's mixer is a
    # silent stub (see c_mpos/duke3d/core/duke_audio.c).
    audio_rate = None
    screen_transition_ms = 0

    def onCreate(self):
        # These are created before the base class can deliver a touch or ask
        # for an engine.
        self._touch = DukeTouch(self.key)
        self._overlay = None
        self._grp = None
        super().onCreate()
        self._loading("Loading Duke Nukem 3D...")

    def _loading(self, text, done=0, total=0):
        if total:
            text = "%s %d%%" % (text, done * 100 // total)
        self.set_message(text)
        try:
            # The binding takes the display explicitly; without it nothing is
            # repainted until the engine's first frame.
            lv.refr_now(None)
        except Exception as error:
            print("duke3d: cannot repaint the launch message: %s" % (error,))

    def _extent_progress(self, phase, percent):
        if phase == extent.PHASE_SPACE or percent <= 0:
            self._loading("Preparing the engine in storage...")
        else:
            self._loading("Preparing the engine in storage... %d%%" % percent)

    def make_engine(self):
        return _CoreEngine()

    def start_engine(self, surface):
        self._loading("Unpacking Duke3D data 0%")
        try:
            self._grp = prepare_grp(self._loading)
        except Exception as error:
            print("duke3d: prepare failed: %s" % (error,))
            sys.print_exception(error)
            self.show_message("Duke Nukem 3D cannot start:\n%s" % (error,))
            return False
        self._loading("Starting the engine")
        self.engine.progress = self._extent_progress
        try:
            self.engine.start(self._grp, surface)
            self._overlay = TouchOverlay(self)
        except Exception as error:
            print("duke3d: engine start failed: %s" % (error,))
            sys.print_exception(error)
            raise
        return True

    def onResumed(self):
        self._touch.release_all()
        if self._overlay is not None:
            self._overlay.set_visible(True)

    def onPaused(self):
        self._touch.release_all()

    def onStop(self, screen):
        super().onStop(screen)
        if self._grp is not None:
            buffer, _size = self._grp
            _free_asset_buffer(buffer)
            self._grp = None

    def on_frame(self, now):
        try:
            self.engine.tick(now)
        except Exception as error:
            print("duke3d: frame exception type=%s repr=%r" % (type(error), error))
            try:
                sys.print_exception(error)
            except Exception:
                pass
            raise

    def on_touch_finger(self, finger, event_code, x, y):
        gx, gy = self.to_game(x, y)
        if event_code == lv.EVENT.PRESSED:
            self._touch.pressed(finger, gx, gy)
            if self._overlay is not None and self._overlay.visible:
                self._overlay.set_visible(False)
        elif event_code == lv.EVENT.PRESSING:
            self._touch.moving(finger, gx, gy)
        else:
            self._touch.released(finger)

    def on_key_event(self, key):
        # A keyboard on a desktop is not a supported engine host (there is no
        # x64 module), but the badge's IO0 back key arrives here and is left to
        # the OS: it closes the activity, which is what "back" should do.
        pass
