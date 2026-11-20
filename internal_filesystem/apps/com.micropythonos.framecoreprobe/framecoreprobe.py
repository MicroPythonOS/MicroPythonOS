# Framecore probe: a native (C) "legacy framebuffer engine" on a MicroPythonOS
# activity, and the measurement harness for the native-core spike.
#
# The C module in c_mpos/framecore_probe/ owns a 320x200 RGB565 framebuffer and
# redraws all of it every frame, the way Doom and friends do. It is deliberately
# not a game: the point is to measure the path (import cost, full-frame present,
# palette/32-bit conversion, key queue, lump reads) before committing to a port.
#
# The measurement entry points are on the activity, so they can be driven from
# the REPL over serial:
#
#     act.measure_frames(60)        # fps for a 320x200 full-frame redraw
#     act.measure_conversions(30)   # ms/frame for expand8 / LUT / expand32
#     act.measure_file_read(200)    # ms per 16 KB lump read
#
import gc
import lvgl as lv
import mpos.ui
import sys
import time

from mpos import Activity, InputManager

if sys.platform == "esp32":
    import framecore_probe_xtensawin as probe
else:
    import framecore_probe_x64 as probe

from mpos.ui.native_display import NativeDisplay

# The engine frame, 320x200 letterboxed on the 320x240 badge panel. It is the
# classic 4:3-ish size Doom renders at, and 128 KB per full frame.
ENGINE_WIDTH = 320
ENGINE_HEIGHT = 200

TARGET_FPS = 50
FRAME_SLACK_MS = 5

LUMP_BYTES = 16 * 1024


def _app_directory():
    """The folder this app lives in, on desktop and on the badge.

    `__file__` is the app-relative path while the app runs, which is also the
    form the lump reader wants for `open()`. A frozen build has no `__file__`,
    so fall back to the app folder name the OS installs it under.
    """
    path = globals().get("__file__")
    if path and "/" in path:
        return path.rsplit("/", 1)[0]
    return "apps/com.micropythonos.framecoreprobe"


LUMP_PATH = _app_directory() + "/lump16k.dat"


def _noop_band(_band):
    return None


class CachedReader:
    """One open file for the whole session: `read(path, offset, into)`.

    This is the shape probe.set_file_reader() expects, and it is the shape a WAD
    lump reader needs: an engine asks for a small block at an offset many times
    per second, so re-opening the file per read would dominate the cost.
    """

    def __init__(self):
        self._file = None
        self._path = None
        self.reads = 0

    def read(self, path, offset, into):
        offset = int(offset)
        if path != self._path:
            if self._file is not None:
                self._file.close()
            self._file = open(path, "rb")
            self._path = path
        self._file.seek(offset)
        self.reads += 1
        return self._file.readinto(into)

    def close(self):
        if self._file is not None:
            try:
                self._file.close()
            except Exception:
                pass
        self._file = None
        self._path = None


class FramecoreProbe(Activity):

    screen = None
    leftbutton = None
    rightbutton = None
    defocus_button = None
    touch_active = False
    touch_last_x = None

    _display = None
    _started = False
    _paused = True
    _benchmarking = False
    _next_frame_ms = 0
    _frame_interval_ms = 1000 // TARGET_FPS

    _reader = None
    _convert_src8 = None
    _convert_src32 = None
    _convert_dst = None
    _palette = None
    _palette_built = False

    _stats_frames = 0
    _stats_since_ms = 0
    _stats_fps = 0.0
    _last_key = -1

    def onCreate(self):
        self.screen = lv.obj()
        self.screen.add_flag(lv.obj.FLAG.CLICKABLE)
        self.screen.add_event_cb(self.touch_cb, lv.EVENT.ALL, None)

        # Invisible buttons: they exist so the keypad indev has something to
        # focus, which is how the B/Y buttons reach left()/right().
        self.leftbutton = lv.button(self.screen)
        self.leftbutton.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        self.leftbutton.set_size(1, 1)
        self.leftbutton.set_style_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        self.leftbutton.add_event_cb(lambda e: self.left(), lv.EVENT.FOCUSED, None)

        self.defocus_button = lv.button(self.screen)
        self.defocus_button.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.defocus_button.set_size(1, 1)
        self.defocus_button.set_style_opa(lv.OPA.TRANSP, lv.PART.MAIN)

        self.rightbutton = lv.button(self.screen)
        self.rightbutton.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        self.rightbutton.set_size(1, 1)
        self.rightbutton.set_style_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        self.rightbutton.add_event_cb(lambda e: self.right(), lv.EVENT.FOCUSED, None)

        self.setContentView(self.screen)

    # -- lifecycle --------------------------------------------------------

    def onResume(self, screen):
        self._paused = False
        if not self._started:
            self._started = True
            self._init_engine()

        self._display.begin()
        self._next_frame_ms = time.ticks_ms()
        self._stats_since_ms = self._next_frame_ms
        self._stats_frames = 0
        mpos.ui.task_handler.add_event_cb(
            self._drawframe, mpos.ui.task_handler.TASK_HANDLER_FINISHED)

    def _init_engine(self):
        # The module allocates the framebuffer and hands it over by reference,
        # so the surface wraps the engine's own pixels: no allocation here and
        # no copy per frame.
        buffer = probe.alloc_framebuffer(ENGINE_WIDTH, ENGINE_HEIGHT)
        self._display = NativeDisplay(
            self.screen, buffer=buffer,
            width=ENGINE_WIDTH, height=ENGINE_HEIGHT)
        probe.init(buffer, ENGINE_WIDTH, ENGINE_HEIGHT, 0)
        if __debug__:
            print("framecore: %dx%d, %d bands of %d rows" % (
                ENGINE_WIDTH, ENGINE_HEIGHT, self._display.band_count,
                self._display.rows_per_band))

    def onPause(self, screen):
        self._paused = True
        mpos.ui.task_handler.remove_event_cb(self._drawframe)
        if self._display is not None:
            self._display.end()
        if self._reader is not None:
            self._reader.close()

    def onDestroy(self, screen):
        self.onPause(screen)
        if self._display is not None:
            self._display = None
        if self._started:
            probe.free_framebuffer()
            self._started = False

    # -- frame loop -------------------------------------------------------

    def _drawframe(self, arg1=None, arg2=None):
        if self._paused or self._benchmarking:
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, self._next_frame_ms) < -FRAME_SLACK_MS:
            return
        self._next_frame_ms = time.ticks_add(now, self._frame_interval_ms)

        probe.draw(now)
        self._drain_keys()
        # The engine redraws the whole frame, so every band is dirty. The
        # render callback does nothing: the pixels are already there.
        self._display.present_all(_noop_band)

        self._stats_frames += 1
        elapsed = time.ticks_diff(now, self._stats_since_ms)
        if elapsed >= 1000:
            self._stats_fps = self._stats_frames * 1000.0 / elapsed
            self._stats_frames = 0
            self._stats_since_ms = now

    def get_fps(self):
        return self._stats_fps

    def get_stats(self):
        return {
            "fps": self._stats_fps,
            "frames": probe.get_frames(),
            "box_x": probe.get_box_x(),
            "box_y": probe.get_box_y(),
            "bands": self._display.bands if self._display else 0,
            "rows_per_band": self._display.rows_per_band if self._display else 0,
            "last_key": self._last_key,
        }

    # -- input ------------------------------------------------------------

    def key(self, code, pressed=True):
        probe.key(code, pressed)

    def _drain_keys(self):
        # The engine shape: keys are queued and polled at the engine's own pace.
        event = probe.poll_key()
        while event >= 0:
            self._last_key = event
            event = probe.poll_key()

    def left(self):
        if self._paused:
            return
        lv.group_focus_obj(self.defocus_button)
        self.key(probe.KEY_LEFT)

    def right(self):
        if self._paused:
            return
        lv.group_focus_obj(self.defocus_button)
        self.key(probe.KEY_RIGHT)

    def touch_cb(self, event):
        event_code = event.get_code()
        if event_code == lv.EVENT.PRESSED:
            x, y = InputManager.pointer_xy()
            self.touch_active = True
            self.touch_last_x = x
            return
        if event_code == lv.EVENT.PRESSING:
            x, y = InputManager.pointer_xy()
            if self.touch_last_x is not None and x < self.touch_last_x - 4:
                self.key(probe.KEY_LEFT)
                self.touch_last_x = x
            elif self.touch_last_x is not None and x > self.touch_last_x + 4:
                self.key(probe.KEY_RIGHT)
                self.touch_last_x = x
            return
        if event_code == lv.EVENT.RELEASED:
            self.touch_active = False
            self.touch_last_x = None

    # -- measurements -----------------------------------------------------

    def measure_frames(self, count=60):
        """Full 320x200 redraws, presented as fast as LVGL can push them."""
        self._benchmarking = True
        display = self._display
        try:
            for _ in range(3):
                probe.draw(time.ticks_ms())
                display.present_all(_noop_band)

            draw_us = 0
            present_us = 0
            start = time.ticks_us()
            for _ in range(count):
                t0 = time.ticks_us()
                probe.draw(time.ticks_ms())
                t1 = time.ticks_us()
                display.present_all(_noop_band)
                t2 = time.ticks_us()
                draw_us += time.ticks_diff(t1, t0)
                present_us += time.ticks_diff(t2, t1)
            elapsed_us = time.ticks_diff(time.ticks_us(), start)
        finally:
            self._benchmarking = False

        return {
            "frames": count,
            "elapsed_ms": elapsed_us / 1000.0,
            "fps": count * 1000000.0 / elapsed_us if elapsed_us else 0.0,
            "draw_ms": draw_us / 1000.0 / count,
            "present_ms": present_us / 1000.0 / count,
            "bands": display.band_count,
            "rows_per_band": display.rows_per_band,
        }

    def _conversion_buffers(self):
        pixels = ENGINE_WIDTH * ENGINE_HEIGHT
        if self._convert_src8 is None:
            self._convert_src8 = bytearray(pixels)
            probe.fill_index(self._convert_src8)
        if self._convert_src32 is None:
            self._convert_src32 = bytearray(pixels * 4)
            probe.fill_rgbx(self._convert_src32)
        if self._convert_dst is None:
            self._convert_dst = bytearray(pixels * 2)
        if self._palette is None:
            palette = bytearray(768)
            for i in range(256):
                palette[i * 3] = i
                palette[i * 3 + 1] = (i * 3) & 0xFF
                palette[i * 3 + 2] = (i * 7) & 0xFF
            self._palette = palette
        return self._convert_src8, self._convert_src32, self._convert_dst

    def _time_call(self, count, call):
        for _ in range(3):
            call()
        start = time.ticks_us()
        for _ in range(count):
            call()
        elapsed_us = time.ticks_diff(time.ticks_us(), start)
        return elapsed_us / 1000.0 / count

    def measure_conversions(self, count=30):
        """ms per 320x200 frame for each pixel format an engine might hand us."""
        src8, src32, dst = self._conversion_buffers()
        self._benchmarking = True
        try:
            expand8_ms = self._time_call(
                count, lambda: probe.expand8(src8, self._palette, dst))
            probe.set_palette(self._palette)
            lut_ms = self._time_call(count, lambda: probe.expand8_lut(src8, dst))
            expand32_ms = self._time_call(count, lambda: probe.expand32(src32, dst))
        finally:
            self._benchmarking = False
        return {
            "expand8_ms": expand8_ms,
            "expand8_lut_ms": lut_ms,
            "expand32_ms": expand32_ms,
            "pixels": ENGINE_WIDTH * ENGINE_HEIGHT,
        }

    def measure_conversions_with_present(self, count=30):
        """expand + present, i.e. what a converted frame actually costs."""
        src8, src32, dst = self._conversion_buffers()
        display = self._display
        rows = display.rows_per_band
        self._benchmarking = True
        try:
            probe.set_palette(self._palette)

            def one_lut():
                probe.expand8_lut(src8, dst)
                display.present_all(_noop_band)

            def one_32():
                probe.expand32(src32, dst)
                display.present_all(_noop_band)

            # Band by band: the conversion of one band runs while the previous
            # band is on the SPI bus, instead of converting everything first.
            def banded_lut():
                display.present_all(
                    lambda band: probe.expand8_band(
                        src8, dst, band, rows, ENGINE_WIDTH))

            def banded_32():
                display.present_all(
                    lambda band: probe.expand32_band(
                        src32, dst, band, rows, ENGINE_WIDTH))

            lut_ms = self._time_call(count, one_lut)
            expand32_ms = self._time_call(count, one_32)
            banded_lut_ms = self._time_call(count, banded_lut)
            banded_32_ms = self._time_call(count, banded_32)
        finally:
            self._benchmarking = False
        return {"expand8_lut_present_ms": lut_ms,
                "expand32_present_ms": expand32_ms,
                "expand8_lut_banded_ms": banded_lut_ms,
                "expand32_banded_ms": banded_32_ms}

    def _ensure_lump(self):
        try:
            if len(open(LUMP_PATH, "rb").read()) == LUMP_BYTES:
                return
        except Exception:
            pass
        chunk = bytearray(LUMP_BYTES)
        for i in range(LUMP_BYTES):
            chunk[i] = (i * 37 + (i >> 5)) & 0xFF
        with open(LUMP_PATH, "wb") as handle:
            handle.write(chunk)
    def measure_file_read(self, count=200):
        """ms per 16 KB lump read through the Python file shim."""
        self._ensure_lump()
        if self._reader is None:
            self._reader = CachedReader()
        if not self._palette_built:
            self._palette_built = True
        probe.set_file_reader(self._reader.read)
        into = bytearray(LUMP_BYTES)
        self._benchmarking = True
        try:
            probe.read_file(LUMP_PATH, 0, into)
            start = time.ticks_us()
            total = 0
            for i in range(count):
                total += probe.read_file(LUMP_PATH, 0, into)
            elapsed_us = time.ticks_diff(time.ticks_us(), start)
        finally:
            self._benchmarking = False
        return {
            "reads": count,
            "bytes_per_read": total // count if count else 0,
            "elapsed_ms": elapsed_us / 1000.0,
            "ms_per_read": elapsed_us / 1000.0 / count,
        }

    def measure_heap(self):
        gc.collect()
        return {"free": gc.mem_free(), "alloc": gc.mem_alloc()}
