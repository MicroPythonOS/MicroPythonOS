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

Controls - badge joystick and buttons. The labels are the action pad's, so the
two maps are the same one:

    joystick         walk and turn
    A                fire (hold)
    B                jump (hold)
    X                crouch (hold)
    Y                use/open (hold)
    START            menu
    MENU             next weapon

In the engine's menus the stick moves the cursor and A or Y confirm; START goes
back.
"""

import os
import sys
import time

import lvgl as lv

from mpos.ui.input_manager import InputManager
from mpos.ui.native_activity import NativeActivity
from duke_controls import (
    DukeTouch, KEY_CROUCH, KEY_DOWN, KEY_FIRE, KEY_JUMP,
    KEY_LEFT, KEY_MENU, KEY_RIGHT, KEY_UP, KEY_USE, KEY_WEAPON)
from duke_overlay import ControlsOverlay, TouchOverlay

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

SELFTEST_PATH = "/duke3d_selftest"
# Run the engine on the MicroPython task instead of its own, for measuring the
# difference on a badge without rebuilding anything.
ON_TASK_PATH = "/duke3d_on_task"
# A run's log, on the device's filesystem. The console is a serial port that
# nobody is reading while the badge is held in a hand, so the one place a
# post-mortem can be found is here. The previous run's log is kept as
# ``DEBUG_LOG_PREV_PATH``: a crash cannot close this one, and launching the app
# again must not erase the evidence.
DEBUG_LOG_PATH = "/duke3d.log"
DEBUG_LOG_PREV_PATH = "/duke3d.prev.log"

_DEBUG_LOG = None


def _debug(text):
    """Append a line to the run's log (no-op when it is not open)."""
    if _DEBUG_LOG is None:
        return
    try:
        _DEBUG_LOG.write("%s\n" % (text,))
        # A buffered write survives an exception in RAM but not a reset: the
        # point of this file is the run that ended in one, so it has to be on
        # the filesystem before the next line is produced.
        _DEBUG_LOG.flush()
    except Exception:
        pass


def _open_debug_log():
    """Open a fresh run log, keeping the previous one for a post-mortem."""
    try:
        os.remove(DEBUG_LOG_PREV_PATH)
    except OSError:
        pass
    try:
        os.rename(DEBUG_LOG_PATH, DEBUG_LOG_PREV_PATH)
    except OSError:
        pass
    for kwargs in ({"buffering": 0}, {}):
        try:
            return open(DEBUG_LOG_PATH, "w", **kwargs)
        except Exception:
            continue
    return None


def _log_run_start():
    """What the previous boot ended in, and how much memory this one has."""
    try:
        import machine
        _debug("run: reset cause %s" % (machine.reset_cause(),))
    except Exception:
        pass
    try:
        import esp32
        heaps = esp32.idf_heap_info(esp32.HEAP_DATA)
        biggest = max(heaps, key=lambda heap: heap[0])
        _debug("run: free %d, largest block %d" % (biggest[1], biggest[2]))
    except Exception:
        pass

GAME_WIDTH = 320
GAME_HEIGHT = 200


def _surface_for_display(display):
    """(width, height, frame_window) for a display.

    A portrait panel gets the frame turned a quarter turn (200x320); a
    landscape panel gets it as it is. A panel that cannot hold it either way
    (the fri3d 2024 is 296x240) gets the middle of the picture: the engine
    drops the outer columns and `frame_window` tells the touch map which part
    is shown. Cropping keeps every remaining pixel sharp; a resample would blur
    the whole picture to save those 12 pixels.
    """
    width = display.get_horizontal_resolution()
    height = display.get_vertical_resolution()
    if height > width:
        if GAME_HEIGHT <= width and GAME_WIDTH <= height:
            return GAME_HEIGHT, GAME_WIDTH, None
    elif GAME_WIDTH <= width and GAME_HEIGHT <= height:
        return GAME_WIDTH, GAME_HEIGHT, None
    if width >= 160 and height >= 100:
        width = min(width, GAME_WIDTH)
        height = min(height, GAME_HEIGHT)
        return (width, height,
                ((GAME_WIDTH - width) // 2, (GAME_HEIGHT - height) // 2,
                 width, height))
    raise RuntimeError(
        "Duke Nukem 3D needs a screen of at least 160x100; "
        "this panel is %dx%d" % (width, height))

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
# the engine is ticked once per display frame. On its own task it renders as
# fast as the panel can take frames, so the loop polls for a published one at
# twice that rate (the poll is a couple of instructions when nothing is ready).
TARGET_FPS = 30
WORKER_TARGET_FPS = 60

# The name the engine opens. Its GRP loader is patched to ask for exactly this,
# and the core's read callback answers from the inflated buffer.
GRP_NAME = "duke3d.grp"
GRP_ZIP_NAME = "E1L1-4_compromise.grp.zip"

# A real GRP wins over the bundled compacted episode. A badge can hold a full
# one on its SD card (the compacted shareware episode is the default), and a
# desktop can point at one with the intent's "grp" extra so a large Atomic GRP
# is tested without copying it into the package.
GRP_FILE_CANDIDATES = (
    "/sdcard/duke3d.grp",
    "/sdcard/duke3d/duke3d.grp",
    "/duke3d.grp",
    "duke3d.grp",
)

HINT_TEXT = "Hold sideways: left is walk/turn, right is the action pad"
TOUCH_HINT_MS = 8000
# The keyboard's list stays up long enough to read, and F1 brings it back.
CONTROLS_HINT_MS = 12000

# SDL F1: the driver hands F-keys through as their own codes (282 is F1 in
# drivers/indev/sdl_keyboard.py). LVGL has no F1 of its own.
HELP_KEY = 282

# What an LVGL key means to the engine. A badge's X reports ESC and is
# labelled crouch on the action pad; a keyboard has no pad and Esc is the
# menu every player reaches for, so the map depends on the host.
KEY_ACTION_HOLD = "hold"
KEY_ACTION_TAP = "tap"


def key_action(key, touch_pad):
    """(engine key, hold or tap) for an LVGL key, or None.

    A tap is a menu action the engine samples once a tic; everything else is a
    hold that lasts as long as the hardware says the key is down.
    """
    if key == lv.KEY.LEFT:
        return (KEY_LEFT, KEY_ACTION_HOLD)
    if key == lv.KEY.RIGHT:
        return (KEY_RIGHT, KEY_ACTION_HOLD)
    if key == lv.KEY.UP:
        return (KEY_UP, KEY_ACTION_HOLD)
    if key == lv.KEY.DOWN:
        return (KEY_DOWN, KEY_ACTION_HOLD)
    if key in (lv.KEY.ENTER, ord("A"), ord("a")):
        return (KEY_FIRE, KEY_ACTION_HOLD)
    if key in (ord("B"), ord("b")):
        return (KEY_JUMP, KEY_ACTION_HOLD)
    if key in (ord("X"), ord("x"), ord("Z"), ord("z")):
        return (KEY_CROUCH, KEY_ACTION_HOLD)
    if key in (ord("Y"), ord("y"), ord(" ")):
        return (KEY_USE, KEY_ACTION_HOLD)
    if key == lv.KEY.ESC:
        if touch_pad:
            return (KEY_CROUCH, KEY_ACTION_HOLD)
        return (KEY_MENU, KEY_ACTION_TAP)
    if key == lv.KEY.END:
        return (KEY_MENU, KEY_ACTION_TAP)
    if key == lv.KEY.HOME:
        return (KEY_WEAPON, KEY_ACTION_TAP)
    return None

# A menu key is sampled by the engine once a tic. A busy frame can stretch the
# presenter's frame past the default one-tic hold, so keep the key down long
# enough for the next tic to see it; the engine clears ESC after it acts, and a
# weapon switch keeps weapon_pos away from 0, so neither repeats.
MENU_TAP_MS = 150

# The engine's task. Core 0 is the one the MicroPython task (core 1) leaves
# alone; see c_mpos/duke3d/PERFORMANCE.md for what the two cores cost each
# other.
WORKER_AFFINITY = 0

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
        arch_query = getattr(mpos_platform, "natmod_arch", None)
        arch = arch_query() if arch_query is not None else None
        if arch is not None:
            names.append("module_" + arch + ".mpy")
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
    """Release the GRP, whether it is one buffer or a list of chunks."""
    if buffer is None:
        return
    try:
        import mpos_core
    except ImportError:
        return
    free = getattr(mpos_core, "buffer_free", None)
    if free is None:
        return
    parts = buffer if isinstance(buffer, (list, tuple)) else (buffer,)
    for part in parts:
        try:
            free(part)
        except Exception as error:
            print("duke3d: cannot free the GRP buffer: %s" % (error,))


# 512 KiB chunks: a fragmented heap can find five of those where it cannot find
# one 2.4 MiB block, which is what made a launch fail after the OS had grown.
GRP_CHUNK = 512 * 1024


def _asset_read(asset, offset, count):
    """``count`` bytes of the asset at ``offset``, one buffer or many."""
    if not isinstance(asset, (list, tuple)):
        return asset[offset:offset + count]
    out = bytearray()
    for chunk in asset:
        if offset >= len(chunk):
            offset -= len(chunk)
            continue
        take = len(chunk) - offset
        if take > count - len(out):
            take = count - len(out)
        out += chunk[offset:offset + take]
        offset = 0
        if len(out) >= count:
            break
    return out


def find_grp(intent=None):
    """A real GRP path, or None. An intent's "grp" extra wins."""
    if sys.platform == "esp32":
        # A worker core serves its asset from a C-side buffer and cannot call
        # back into Python for a file during its start-up. The on-task test
        # switch (/duke3d_on_task) is the only mode that can read one.
        try:
            os.stat(ON_TASK_PATH)
        except OSError:
            return None
    if intent is not None:
        try:
            extra = intent.extras.get("grp") if hasattr(intent, "extras") else None
        except Exception:
            extra = None
        if extra:
            path = _absolute(extra)
            try:
                open(path, "rb").close()
                return path
            except OSError:
                pass
    for path in GRP_FILE_CANDIDATES:
        if path.startswith("/sdcard/"):
            try:
                from mpos import SDCardManager
                if not SDCardManager.mounted:
                    continue
            except Exception:
                continue
        try:
            path = _absolute(path)
            open(path, "rb").close()
            return path
        except OSError:
            continue
    path = _absolute(_app_directory() + "/" + GRP_NAME)
    try:
        open(path, "rb").close()
        return path
    except OSError:
        return None


def prepare_grp(loading, intent=None):
    """The GRP as (buffer, size) or (path, size); raises when it is missing."""
    path = find_grp(intent)
    if path is not None:
        size = os.stat(path)[6]
        loading("Loading %s" % (path.rsplit("/", 1)[-1],), 1, 1)
        if sys.platform != "esp32":
            # A desktop has the RAM and no SD-card read path of its own: read
            # the file once so the engine's thousands of lump reads never
            # cross back into Python. A badge serves it from the file.
            try:
                buffer = bytearray(size)
            except MemoryError:
                # A 44 MB Atomic GRP needs a larger desktop heap
                # (MPOSController(heapsize="128M")); the file path still works,
                # just with a Python call per lump read.
                return path, size
            with open(path, "rb") as handle:
                done = 0
                while done < size:
                    got = handle.readinto(memoryview(buffer)[done:])
                    if not got:
                        break
                    done += got
                    loading("Loading %s" % (path.rsplit("/", 1)[-1],),
                            done, size)
            return buffer, done
        return path, size
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
        # One contiguous block is the fast path; when it does not fit, take the
        # same asset in chunks rather than failing the launch.
        try:
            return zipasset.load_chunks(
                archive, progress=progress, chunk_size=GRP_CHUNK,
                alloc=_asset_buffer)
        except Exception:
            raise
    return buffer, size


class _CoreEngine:
    """The engine as a littlefs2e extent (the badge).

    Two ways to run it, chosen by what the firmware offers. On its own task
    (``start_task``) the engine renders into one of two buffers while this
    activity presents the other; the engine's stack is the worker's, so the
    OS keeps its own small one, and the render and the panel transfer run at
    the same time. Without that API the engine ticks on the MicroPython task
    and presents each band as it finishes.
    """

    name = "core"
    quit = False
    frame_size = (GAME_WIDTH, GAME_HEIGHT)
    # (x, y, width, height) of the frame the surface shows, when the panel is
    # too narrow for all of it. None means the whole frame is on screen.
    frame_window = None

    def __init__(self):
        import mpos_core
        self._core = mpos_core
        self._surface = None
        self._grp = None
        self._grp_path = None
        self._grp_size = 0
        self._keys = []
        self._io_count = 0
        self._callbacks = None
        self.quit = False
        self._quit_query = getattr(mpos_core, "quit_requested", None)
        # A firmware with ABI 9 can run the engine on a task of its own.
        self._worker = getattr(mpos_core, "start_task", None) is not None
        try:
            os.stat(ON_TASK_PATH)
            self._worker = False
        except OSError:
            pass
        self._worker_surfaces = []
        self._surface_index = None
        stack_query = getattr(mpos_core, "task_stack" if self._worker
                              else "stack_high_water", None)
        self._stack_query = stack_query

    def surface_size(self, display):
        # A portrait panel (240x320 logical, the badge held sideways) cannot
        # show the 320x200 frame untransposed, so the engine turns it into a
        # 200x320 surface. A landscape panel gets the frame as it is. This is
        # the same rule the Doom core uses, and NativeActivity's touch mapping
        # undoes the rotation for the game's own coordinates.
        width, height, self.frame_window = _surface_for_display(display)
        return width, height

    def start(self, grp, surface):
        self._surface = surface
        self._grp, self._grp_size = grp
        self._grp_path = None
        if isinstance(self._grp, str):
            # A real GRP on storage: the engine reads it through this side's
            # file callback, so keep the buffer path empty.
            self._grp_path = self._grp
            self._grp = None
            # The worker loader serves its own asset buffer from C and cannot
            # call back into Python for a file, so this asset forces the
            # on-task engine (which is also the only one that can read it).
            if self._worker:
                print("duke3d: external GRP, running the engine on the MicroPython task")
                self._worker = False
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
        # The engine's own save directory, one level under the app's prefs.
        _makedirs(config_dir + "/duke3d")
        self._config_dir = config_dir
        if self._worker:
            self._start_worker(partition, offset, length, crc, surface,
                               config_dir)
            return
        # The engine runs its whole start-up (GRP index, palette, the first
        # level) inside init(); that is one blocking step of a few seconds, and
        # the activity is showing its loading message while it happens.
        self._core.start(
            partition, offset, length,
            *self._callbacks,
            GRP_NAME, surface.width, surface.height,
            surface.buffer, surface.rows_per_band, crc, config_dir)

    def _start_worker(self, partition, offset, length, crc, surface,
                      config_dir):
        """Run the engine on its own task, presenting its frames here.

        The engine's surface is the one LVGL shows, so it is buffer 0 and the
        loader allocates only the second; the app keeps the pixels of both,
        because a published frame stays valid until it says otherwise.
        """
        self._worker_surfaces = [surface.buffer]
        self._core.start_task(
            partition, offset, length,
            width=surface.width,
            height=surface.height,
            band_rows=surface.rows_per_band,
            asset=self._grp,
            asset_name=GRP_NAME,
            wad_path=GRP_NAME,
            config_dir=config_dir,
            expected_crc=crc,
            # The deepest engine path needs ~38 KiB (canary: 16/20/24/31 all
            # die in play, 48 has 11 KiB to spare), which is more than the
            # largest internal block a fragmented board can give, so the
            # loader falls back to PSRAM.
            stack_bytes=48 * 1024,
            affinity=WORKER_AFFINITY,
            surface=surface.buffer)
        buffer = self._core.task_surface(1)
        self._worker_surfaces.append(buffer)
        self._surface_index = [0, surface.add_buffer(buffer)]

    def resume(self):
        pass

    def pause(self):
        self._keys = []

    def tick(self, now):
        if self._worker:
            self._present()
        else:
            self._core.tick(now)
        if self._quit_query is not None and self._quit_query():
            self.quit = True
            _debug("engine asked to quit")

    def audio_mix(self, buffer):
        self._core.audio_mix(buffer)

    def key(self, code, pressed):
        if self._worker:
            try:
                self._core.post_key(code, pressed)
                return
            except Exception:
                pass
        self._keys.append((code, pressed))

    def stop(self):
        try:
            self._core.stop()
        except Exception:
            pass
        self._grp = None
        self._grp_path = None
        self._grp_size = 0
        self._keys = []
        self._io_count = 0
        self._callbacks = None
        self._worker_surfaces = []
        self._surface_index = None

    # -- worker mode ------------------------------------------------------

    def _present(self):
        """Show the frame the engine published, then give the buffer back."""
        frame = self._core.task_frame()
        if frame is None:
            self._drain_log()
            return
        index, _seq = frame
        surface = self._surface
        # A frame published before the activity is on screen is dropped, not
        # queued: an idle surface must not hold a buffer the engine needs.
        shown = False
        if surface is not None and surface._active:
            surface.select_buffer(self._surface_index[index])
            shown = surface.flush()
            if shown:
                self._core.task_presented()
        else:
            self._core.task_presented()
        self._present_count = getattr(self, "_present_count", 0) + 1
        if self._present_count <= 8:
            _debug("present %d: index %d shown %r active %r"
                   % (self._present_count, index, shown,
                      surface is not None and surface._active))
        self._drain_log()

    def _drain_log(self):
        # The worker cannot print: it has no interpreter and no console. Its
        # lines are queued in C and printed here, on the task that owns both.
        drain = getattr(self._core, "task_log", None)
        if drain is None:
            return
        while True:
            line = drain()
            if line is None:
                break
            self._log(line)

    # -- ABI callbacks ----------------------------------------------------

    def _present_band(self, y, rows, data):
        if data is not None:
            start = y * self._surface.width * 2
            self._surface.buffer[start:start + len(data)] = data
        if not self._surface._active:
            return
        self._surface.invalidate_band(y // self._surface.rows_per_band)
        # Invalidate every band first and run one LVGL pass for the whole
        # frame. Flushing per band is correct but costs a full layout/draw
        # cycle five times a frame, which is most of the present time.
        if y + rows < self._surface.height:
            return
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
        if path == GRP_NAME:
            if self._grp_path is not None:
                try:
                    with open(self._grp_path, "rb") as handle:
                        handle.seek(offset)
                        got = handle.readinto(into)
                    return 0 if got is None else got
                except Exception:
                    return -1
            if self._grp is not None and offset < self._grp_size:
                count = self._grp_size - offset
                if count > len(into):
                    count = len(into)
                into[:count] = _asset_read(self._grp, offset, count)
                return count
        return -1

    def _file_size(self, path):
        if path == GRP_NAME:
            if self._grp_path is not None:
                try:
                    return os.stat(self._grp_path)[6]
                except OSError:
                    return -1
            return self._grp_size
        return -1

    def _host_path(self, path):
        """The engine's virtual path -> a file under the app's prefs dir.

        The engine writes `/config/duke3d.cfg` and
        `/saves/duke3d/game0.sav` (rg_system's layout). Both live under the
        app's own directory so an uninstall takes them with it.
        """
        if path.startswith("/config/"):
            return self._config_dir + path[len("/config"):]
        if path.startswith("/saves/"):
            return self._config_dir + path[len("/saves"):]
        return self._config_dir + "/" + path

    def serve_files(self):
        """Answer the core's file request, if it has one.

        The engine runs on its own task and never enters MicroPython, so it
        hands a file operation over (ABI 10) and blocks; this runs once a
        frame and is one C call when nothing is pending. Saves are a menu
        action, so the blocks are large and rare.
        """
        core = self._core
        poll = getattr(core, "file_poll", None)
        reply = getattr(core, "file_reply", None)
        if poll is None or reply is None:
            return
        request = poll()
        if request is None:
            return
        # `buffer` is the core's own memory, wrapped without a copy: a save
        # moves blocks of 100 KB and more, and copying them here would grow the
        # GC heap by an area that is never handed back (1 MB of PSRAM per save
        # on a board where the next engine needs every block).
        op, path, offset, length, buffer = request
        count = -1
        try:
            real = self._host_path(path)
            if op == 0:
                with open(real, "rb") as handle:
                    handle.seek(offset)
                    got = handle.readinto(buffer)
                count = 0 if got is None else got
            elif op == 1:
                # offset 0 is a new file; later offsets append into the one the
                # engine just created.
                if buffer is None:
                    count = 0
                else:
                    with open(real, "wb" if offset == 0 else "r+b") as handle:
                        handle.seek(offset)
                        count = handle.write(buffer)
            else:
                count = os.stat(real)[6]
        except Exception as error:
            # Whatever goes wrong here must still answer the core: it is
            # blocked until this returns, and a request that is never answered
            # costs the engine its 10 s timeout and a corrupt save.
            _debug("file %s failed: %r" % (path, error))
            count = -1
        reply(count)

    def _log(self, line):
        # The "\x01yield" sentinel is consumed in C by the core loader before
        # it reaches Python; a line that still arrives starts with that byte.
        if line and line[0] == "\x01":
            return
        _debug("log: %s" % (line,))
        if line.startswith("duke: "):
            query = self._stack_query
            if query is not None:
                try:
                    line = "%s, stack free %d" % (line, query())
                except Exception:
                    pass
        try:
            print("duke3d: %s" % line)
        except Exception:
            # The REPL can stop draining while the engine owns the CPU; a
            # failed log line must not become a failed frame.
            pass
        # The console is a serial port nobody is holding a reader to while the
        # badge is in a hand. Keep the last lines where a probe (or the file on
        # stop) can find them.
        tail = getattr(self, "_log_tail", None)
        if tail is None:
            tail = self._log_tail = []
        tail.append(line)
        if len(tail) > 20:
            del tail[0]


class _NatmodEngine:
    """The engine as a MicroPython native module (desktop).

    Same engine, same platform shims, no MMU window: the module is ordinary C
    linked against MicroPython, so a desktop gets the same game with no
    bootloader and no flash partition. Everything above the adapter is shared
    with the core: the activity owns the surface, the pacing and the controls.
    """

    name = "natmod"
    frame_size = (GAME_WIDTH, GAME_HEIGHT)
    frame_window = None
    # The core can run on a task of its own; a plain module runs on the
    # MicroPython task.
    _worker = False

    def __init__(self):
        _path, name = find_engine()
        if name is None:
            raise RuntimeError(
                "Duke3D's engine is not installed; reinstall Duke Nukem 3D")
        if not name.startswith("module_") or not name.endswith(".mpy"):
            raise RuntimeError("Duke3D has no native module for this platform")
        self._duke = __import__(name[:-4])
        self._surface = None
        # The module holds the callback in C, which the collector does not
        # trace: keep the bound method alive here for as long as it is set.
        self._present = None
        self._config_dir = None
        self._grp = None
        self.quit = False

    def surface_size(self, display):
        width, height, self.frame_window = _surface_for_display(display)
        return width, height

    def start(self, grp, surface, now_ms=None):
        buffer, size = grp
        if isinstance(buffer, (list, tuple)):
            # The chunked inflate is for a fragmented badge heap; a desktop has
            # one block, but accept both rather than failing the launch.
            joined = bytearray()
            for chunk in buffer:
                joined.extend(chunk)
            buffer = joined
            size = len(joined)
        self._surface = surface
        self._grp = (buffer, size)
        self._config_dir = _absolute(PREFS_DIR)
        _makedirs(self._config_dir)
        # The engine's save directory, one level under the app's prefs.
        _makedirs(self._config_dir + "/duke3d")
        self.quit = False
        self._present = self._present_band
        self._duke.surface(surface.buffer, surface.width, surface.height,
                          surface.rows_per_band, self._present)
        try:
            # The clock the first tick continues from: the engine installs its
            # timer while this call is running, and a zero there would make the
            # first tick look like the host's whole uptime had elapsed.
            if now_ms is None:
                now_ms = time.ticks_ms()
            self._duke.start(buffer, GRP_NAME, self._config_dir, now_ms)
        except SystemExit:
            # Error()/exit() during the engine's start-up: it is not going to
            # run, and the app has to say so rather than show a black screen.
            raise RuntimeError(
                "the Duke3D engine stopped during start-up (see the console)")

    def resume(self):
        pass

    def pause(self):
        pass

    def tick(self, now):
        try:
            self._duke.tick(now)
        except SystemExit:
            # The engine's quit menu (or a fatal error) ended the frame. The
            # host owns the activity, so this is how it asks to be closed.
            self.quit = True
        if self._duke.quit_requested():
            self.quit = True

    def audio_mix(self, buffer):
        pass

    def key(self, code, pressed):
        self._duke.key(code, pressed)

    def stop(self):
        try:
            self._duke.surface(None, 0, 0, 0, None)
        except Exception:
            pass
        try:
            self._duke.stop()
        except Exception:
            pass
        self._present = None
        self._surface = None
        self._grp = None
        self._config_dir = None

    def _present_band(self, y, rows):
        """A display band is ready in the surface the engine drew into."""
        if self._surface is None or not self._surface._active:
            return
        self._surface.invalidate_band(y // self._surface.rows_per_band)
        # One LVGL pass for the whole frame, not one per band: a pass is a full
        # layout/draw cycle and five of them is most of the present time.
        if y + rows < self._surface.height:
            return
        self._surface.flush()


def _make_engine():
    """The engine this host can run, or a RuntimeError saying why not."""
    if mpos_platform is None:
        raise RuntimeError(
            "Duke Nukem 3D needs a newer MicroPythonOS (mpos.platform is missing)")
    if sys.platform == "esp32":
        return _CoreEngine()
    return _NatmodEngine()


class Duke3D(NativeActivity):
    """One activity, one engine: the core on a badge, the module on a desktop."""

    target_fps = TARGET_FPS
    # A badge has the action pad its labels belong to; a desktop has a
    # keyboard, whose keys follow the map in the controls overlay.
    touch_pad = sys.platform == "esp32"
    # The sideways hint is a pad instruction; a keyboard gets the list instead.
    hint_text = HINT_TEXT if touch_pad else None
    hint_ms = TOUCH_HINT_MS
    # The GT911 reports five points, so both thumbs get their own finger.
    touch_fingers = True
    # The walking stick starts at the left edge and the action pad reaches the
    # top one, so the OS's edge swipes would steal both: the same opt-out Doom
    # makes, through the attribute the view reads for the foreground activity.
    system_gestures_enabled = False
    # A keypad reports a press and no release, so without this a held joystick
    # turns for 180 ms and then waits for the keypad's first repeat at 400 ms.
    # The drivers that can report their real state (the fri3d 2026 expander)
    # make it a continuous hold instead.
    key_state = True
    # No audio output on the panels this engine targets; the core's mixer is a
    # silent stub (see c_mpos/duke3d/core/duke_audio.c).
    audio_rate = None
    screen_transition_ms = 0
    # Built on launch by start_engine(); they exist before onCreate() so a key
    # that arrives early (and a test that builds the activity directly) is
    # harmless rather than an AttributeError.
    _controls = None
    _controls_until = 0

    def onBackPressed(self, screen):
        """Keep the OS's back from ending a game in progress.

        A badge maps its back key to ESC (the expander's X) and the desktop
        uses Esc; either would close the activity and lose the level. The way
        out is the engine's own menu (the START touch control), whose Quit sets
        ``engine.quit`` and closes the activity through ``_leave()``. Returning
        True consumes back for as long as this activity is foreground; no
        global state has to be restored afterwards.
        """
        return True

    def on_key_event(self, key):
        """A key from the badge's pad or from a keyboard.

        On a badge the labels are the action pad's: joystick walks and turns,
        A fires, B jumps, X crouches, Y uses, START opens the menu and MENU
        picks the next weapon. X arrives as ESC and Y as its letter (the
        expander dual-delivers B and Y because LVGL takes NEXT/PREV for focus);
        START is END and MENU is HOME, so all six reach the app even though the
        OS uses X for back and MENU for the drawer.

        A keyboard has none of those buttons. It keeps the pad's letters for
        fire/jump/crouch/use and adds Space (use), Z (crouch) and, because it is
        what every player reaches for, Esc opens the engine's menu instead of
        crouching. See ``key_action`` and the controls overlay.
        """
        if key == HELP_KEY:
            if self._controls is not None and self._controls.visible:
                self._controls.set_visible(False)
            else:
                self._show_controls()
            return
        if self._controls is not None and self._controls.visible:
            self._controls.set_visible(False)
        action = key_action(key, self.touch_pad)
        if action is None:
            return
        code, kind = action
        if kind == KEY_ACTION_TAP:
            # The engine samples its menu key once a tic: press and release in
            # one frame would cancel out before it reads the key.
            self.holds.tap_held(code, MENU_TAP_MS)
        else:
            self.holds.hold(code, key)

    def _show_controls(self, ms=CONTROLS_HINT_MS):
        """Put the key list up (F1, and once at launch on a desktop)."""
        if self._controls is None:
            return
        self._controls.set_visible(True)
        self._controls_until = time.ticks_add(time.ticks_ms(), ms)

    def onCreate(self):
        _debug("onCreate")
        # These are created before the base class can deliver a touch or ask
        # for an engine. The tap callback is looked up at call time: the key
        # holds it needs are created by the base class's onCreate().
        self._touch = DukeTouch(
            self.key,
            lambda code: self.holds.tap_held(code, MENU_TAP_MS))
        self._overlay = None
        self._overlay_until = 0
        self._controls = None
        self._controls_until = 0
        self._grp = None
        # Poll faster when the engine runs on its own task: the frame loop only
        # shows what the engine published, and it publishes as soon as the
        # panel is done with the last frame.
        try:
            import mpos_core
            if getattr(mpos_core, "start_task", None) is not None:
                self.target_fps = WORKER_TARGET_FPS
        except ImportError:
            pass
        self._selftest = False
        try:
            os.stat(SELFTEST_PATH)
            self._selftest = True
        except OSError:
            pass
        self._selftest_start = None
        self._selftest_step = -1
        self._selftest_down = ()
        super().onCreate()

    def _loading(self, text, done=0, total=0):
        if total:
            text = "%s %d%%" % (text, done * 100 // total)
        self.set_message(text)
        # The binding takes the display explicitly; without it nothing is
        # repainted until the engine's first frame.
        self._repaint()

    def _extent_progress(self, phase, percent):
        if phase == extent.PHASE_SPACE or percent <= 0:
            self._loading("Preparing the engine in storage...")
        else:
            self._loading("Preparing the engine in storage... %d%%" % percent)

    def make_engine(self):
        return _make_engine()

    def onResume(self, screen):
        _debug("onResume enter")
        # MENU is the action pad's next-weapon key, so the OS drawer must not
        # open over the game when it is pressed. This is the framework's
        # per-activity switch; onPause puts it back for whatever comes next.
        InputManager.set_drawer_open_disabled(True)
        try:
            super().onResume(screen)
        except Exception as error:
            _debug("onResume raised: %r" % (error,))
            raise
        _debug("onResume exit, error=%r ready=%r" % (self.error, self._ready))

    def onPause(self, screen):
        _debug("onPause")
        super().onPause(screen)
        InputManager.set_drawer_open_disabled(False)

    def _leave(self):
        _debug("leave requested")
        super()._leave()

    def start_engine(self, surface):
        global _DEBUG_LOG
        _DEBUG_LOG = _open_debug_log()
        _log_run_start()
        # A collect cannot hand a heap *area* back to the IDF heap, so it will
        # not make room for the engine's own blocks. It does stop the Python
        # side from growing: a large allocation triggers a new GC area, and
        # every area is another PSRAM chunk that splits the free space further.
        try:
            import gc
            gc.collect()
        except Exception:
            pass
        _debug("start: surface %dx%d in %d-row bands"
               % (surface.width, surface.height, surface.rows_per_band))
        self._loading("Unpacking Duke3D data 0%")
        try:
            self._grp = prepare_grp(
                self._loading, getattr(self, "intent", None))
        except Exception as error:
            print("duke3d: prepare failed: %s" % (error,))
            sys.print_exception(error)
            _debug("prepare failed: %r" % (error,))
            self._release_grp()
            self.show_message(
                "Duke Nukem 3D cannot start.\n\n%s\n\n"
                "Restart the badge, then launch it again." % (error,))
            return False
        self._loading("Starting the engine")
        self.engine.progress = self._extent_progress
        try:
            self.engine.start(self._grp, surface)
            # The launch progress label sits above the picture and would stay
            # there for the rest of the session: nothing else clears it.
            self._clear_hint()
            if self.touch_pad:
                self._overlay = TouchOverlay(self)
                self._overlay_until = time.ticks_add(time.ticks_ms(), 6000)
            else:
                self._controls = ControlsOverlay(self)
                self._show_controls()
        except Exception as error:
            # Do not leave the loading message on screen for ever, and do not
            # keep 2.4 MB of GRP that nothing is going to read: say what went
            # wrong and give the memory back, so leaving and retrying works.
            print("duke3d: engine start failed: %s" % (error,))
            sys.print_exception(error)
            _debug("engine start failed: %r" % (error,))
            self._release_grp()
            self.show_message(
                "Duke Nukem 3D could not start.\n\n%s\n\n"
                "The engine needs a large block of free memory. Restart the "
                "badge, then launch it again." % (error,))
            return False
        return True

    def _release_grp(self):
        if self._grp is not None:
            buffer, _size = self._grp
            if not isinstance(buffer, str):
                _free_asset_buffer(buffer)
            self._grp = None

    def on_resumed(self):
        self._touch.release_all()
        _debug("resumed, error=%r" % (self.error,))
        if self._overlay is not None:
            self._overlay.set_visible(True)
            self._overlay_until = time.ticks_add(time.ticks_ms(), 6000)
        # A native game on the MicroPython task runs long C frames there, and
        # the task handler reserves a quarter of the last pass as a fairness
        # gap for the main thread; at 50-60 ms frames that is ~13 ms, a fifth
        # of the frame. It is raised while the game is in front. When the
        # engine has a task of its own the opposite is true: the handler then
        # runs back-to-back and its passes evict the engine's code from the
        # cache the two cores share, which is worth more than the gap.
        if getattr(self.engine, "_worker", False):
            return
        try:
            import mpos.ui
            mpos.ui.task_handler.duration = 200
        except Exception:
            pass

    def on_paused(self):
        _debug("activity paused")
        self._touch.release_all()
        try:
            import mpos.ui
            mpos.ui.task_handler.duration = 2
        except Exception:
            pass
        for code in self._selftest_down:
            self.key(code, False)
        self._selftest_down = ()

    def onStop(self, screen):
        global _DEBUG_LOG
        _debug("activity stopped, error=%r" % (self.error,))
        try:
            import mpos.ui
            mpos.ui.task_handler.duration = 2
        except Exception:
            pass
        super().onStop(screen)
        InputManager.set_drawer_open_disabled(False)
        self._release_grp()
        if _DEBUG_LOG is not None:
            try:
                _DEBUG_LOG.close()
            except Exception:
                pass
            _DEBUG_LOG = None

    def _run_selftest(self, now):
        """Drive the engine through the controls, for a hands-free playtest.

        Enabled only when /duke3d_selftest exists: it walks, strafes, fires,
        uses, jumps, opens the menu and navigates it, so a long soak exercises
        the same paths a player would without anybody holding the badge.
        """
        if self._selftest_start is None:
            self._selftest_start = now
        step = (time.ticks_diff(now, self._selftest_start) // 1500) % 14
        if step == self._selftest_step:
            return
        self._selftest_step = step
        for code in self._selftest_down:
            self.key(code, False)
        self._selftest_down = ()
        actions = (
            (KEY_UP,), (KEY_UP, KEY_FIRE), (KEY_RIGHT,), (KEY_LEFT,),
            (KEY_DOWN,), (KEY_FIRE,), (KEY_USE,), (KEY_WEAPON,),
            (KEY_JUMP,), (KEY_CROUCH,), (), (KEY_MENU,),
            (KEY_MENU,), (),
        )
        if step in (11, 12):
            self.key(KEY_MENU, True)
            self.key(KEY_MENU, False)
            return
        codes = actions[step]
        for code in codes:
            self.key(code, True)
        self._selftest_down = codes
        print("duke3d: selftest step %d %s" % (step, codes))

    def on_frame(self, now):
        if self._selftest:
            self._run_selftest(now)
        # The engine's task waits on this: a save or a load blocks it until
        # the host has moved the bytes.
        if getattr(self.engine, "_worker", False):
            self.engine.serve_files()
        if (self._overlay is not None and self._overlay.visible
                and time.ticks_diff(now, self._overlay_until) >= 0):
            # The full labelled overlay is a hint, not chrome: every label
            # overlapping the picture is redrawn on every present, and that is
            # a third of the frame time. The outlines stay available on resume.
            self._overlay.set_visible(False)
        if (self._controls is not None and self._controls.visible
                and time.ticks_diff(now, self._controls_until) >= 0):
            self._controls.set_visible(False)
        try:
            self.engine.tick(now)
        except Exception as error:
            _debug("frame exception: %r" % (error,))
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
