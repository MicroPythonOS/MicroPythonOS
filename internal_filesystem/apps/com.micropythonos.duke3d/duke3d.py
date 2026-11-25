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
import time

import lvgl as lv

from mpos.ui.native_activity import NativeActivity
from duke_controls import (
    DukeTouch, KEY_CROUCH, KEY_DOWN, KEY_FIRE, KEY_JUMP,
    KEY_LEFT, KEY_MENU, KEY_RIGHT, KEY_UP, KEY_USE, KEY_WEAPON)
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

SELFTEST_PATH = "/duke3d_selftest"
# Run the engine on the MicroPython task instead of its own, for measuring the
# difference on a badge without rebuilding anything.
ON_TASK_PATH = "/duke3d_on_task"
# A run's log, on the device's filesystem. The console is a serial port that
# nobody is reading while the badge is held in a hand, so the one place a
# post-mortem can be found is here. Truncated at every start.
DEBUG_LOG_PATH = "/duke3d.log"

_DEBUG_LOG = None


def _debug(text):
    """Append a line to the run's log (no-op when it is not open)."""
    if _DEBUG_LOG is None:
        return
    try:
        _DEBUG_LOG.write("%s\n" % (text,))
    except Exception:
        pass


def _open_debug_log():
    """Open the run log unbuffered, so a probe can read it while it is open."""
    for kwargs in ({"buffering": 0}, {}):
        try:
            return open(DEBUG_LOG_PATH, "w", **kwargs)
        except Exception:
            continue
    return None

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
# the engine is ticked once per display frame. On its own task it renders as
# fast as the panel can take frames, so the loop polls for a published one at
# twice that rate (the poll is a couple of instructions when nothing is ready).
TARGET_FPS = 30
WORKER_TARGET_FPS = 60

# The name the engine opens. Its GRP loader is patched to ask for exactly this,
# and the core's read callback answers from the inflated buffer.
GRP_NAME = "duke3d.grp"
GRP_ZIP_NAME = "E1L1-4_compromise.grp.zip"

HINT_TEXT = "Hold sideways: left is walk/turn, right is the action pad"
TOUCH_HINT_MS = 8000

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
        if path == GRP_NAME and self._grp is not None and offset < self._grp_size:
            count = self._grp_size - offset
            if count > len(into):
                count = len(into)
            into[:count] = _asset_read(self._grp, offset, count)
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
        _debug("onCreate")
        # These are created before the base class can deliver a touch or ask
        # for an engine.
        self._touch = DukeTouch(self.key)
        self._overlay = None
        self._overlay_until = 0
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

    def onResume(self, screen):
        _debug("onResume enter")
        try:
            super().onResume(screen)
        except Exception as error:
            _debug("onResume raised: %r" % (error,))
            raise
        _debug("onResume exit, error=%r ready=%r" % (self.error, self._ready))

    def onPause(self, screen):
        _debug("onPause")
        super().onPause(screen)

    def _leave(self):
        _debug("leave requested")
        super()._leave()

    def start_engine(self, surface):
        global _DEBUG_LOG
        _DEBUG_LOG = _open_debug_log()
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
            self._grp = prepare_grp(self._loading)
        except Exception as error:
            print("duke3d: prepare failed: %s" % (error,))
            sys.print_exception(error)
            self._release_grp()
            self.show_message(
                "Duke Nukem 3D cannot start.\n\n%s\n\n"
                "Restart the badge, then launch it again." % (error,))
            return False
        self._loading("Starting the engine")
        self.engine.progress = self._extent_progress
        try:
            self.engine.start(self._grp, surface)
            self._overlay = TouchOverlay(self)
            self._overlay_until = time.ticks_add(time.ticks_ms(), 6000)
        except Exception as error:
            # Do not leave the loading message on screen for ever, and do not
            # keep 2.4 MB of GRP that nothing is going to read: say what went
            # wrong and give the memory back, so leaving and retrying works.
            print("duke3d: engine start failed: %s" % (error,))
            sys.print_exception(error)
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
        if (self._overlay is not None and self._overlay.visible
                and time.ticks_diff(now, self._overlay_until) >= 0):
            # The full labelled overlay is a hint, not chrome: every label
            # overlapping the picture is redrawn on every present, and that is
            # a third of the frame time. The outlines stay available on resume.
            self._overlay.set_visible(False)
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

    def on_key_event(self, key):
        # A keyboard on a desktop is not a supported engine host (there is no
        # x64 module), but the badge's IO0 back key arrives here and is left to
        # the OS: it closes the activity, which is what "back" should do.
        pass
