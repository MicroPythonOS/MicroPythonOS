# Doom, running as a native (C) engine inside a MicroPythonOS activity.
#
# The engine is doomgeneric built as a MicroPython native module
# (c_mpos/doom/): it keeps an 8-bit paletted 320x200 framebuffer and this file
# converts it to RGB565 one band at a time while the panel is being fed, so the
# conversion costs nothing extra (see docs/apps/native-apps.md).
#
# The first cut of the port: the engine boots, plays its demo, and is measured.
# Input (touch and buttons) comes next.
import lvgl as lv
import mpos.ui
import sys
import time

from mpos import Activity

if sys.platform == "esp32":
    import doom_xtensawin as doom
else:
    import doom_x64 as doom

# Ships with the app as well as in the firmware: an .mpk has to run on firmware
# older than the one that first froze mpos.ui.native_display.
from native_display import NativeDisplay

ENGINE_WIDTH = 320
ENGINE_HEIGHT = 200

# Doom's own tic rate is 35, and the present is what limits a full-screen frame
# to ~30fps on the badge.
TARGET_FPS = 35
FRAME_SLACK_MS = 5

# Doom wants a zone heap; the badge has ~7 MB free after the engine is loaded.
ZONE_MB = 4

def _app_directory():
    path = globals().get("__file__")
    if path and "/" in path:
        return path.rsplit("/", 1)[0]
    return "apps/com.micropythonos.doom"


WAD_CANDIDATES = (
    "/sdcard/doom1.wad",
    "/sdcard/doom/doom1.wad",
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
        try:
            if path.startswith("/sdcard/"):
                from mpos import SDCardManager
                if not SDCardManager.mounted:
                    continue
            open(path, "rb").close()
            return path
        except Exception:
            continue
    return None


class Doom(Activity):

    screen = None
    _surface = None
    _started = False
    _paused = True
    _benchmarking = False
    _next_frame_ms = 0
    _frame_interval_ms = 1000 // TARGET_FPS
    _frames = 0
    _fps = 0.0
    _fps_since = 0
    _fps_frames = 0
    _wad = None

    def onCreate(self):
        self.screen = lv.obj()
        self.setContentView(self.screen)

    def onResume(self, screen):
        self._paused = False
        if not self._started:
            self._started = True
            self._surface = NativeDisplay(
                self.screen, width=ENGINE_WIDTH, height=ENGINE_HEIGHT)
            self._wad = find_wad(getattr(self, "intent", None))
            if self._wad is None:
                if __debug__:
                    print("doom: no WAD found, looked at %s" % (WAD_CANDIDATES,))
            else:
                doom.create(self._wad, ZONE_MB)
                if __debug__:
                    print("doom: started with %s" % (self._wad,))

        self._surface.begin()
        self._next_frame_ms = time.ticks_ms()
        self._fps_since = self._next_frame_ms
        self._fps_frames = 0
        mpos.ui.task_handler.add_event_cb(
            self._drawframe, mpos.ui.task_handler.TASK_HANDLER_FINISHED)

    def onPause(self, screen):
        self._paused = True
        mpos.ui.task_handler.remove_event_cb(self._drawframe)
        if self._surface is not None:
            self._surface.end()

    def _drawframe(self, arg1=None, arg2=None):
        if self._paused or self._benchmarking or self._wad is None:
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, self._next_frame_ms) < -FRAME_SLACK_MS:
            return
        self._next_frame_ms = time.ticks_add(now, self._frame_interval_ms)

        doom.tick(now)
        self._surface.present_all(self._blit_band)

        self._frames += 1
        self._fps_frames += 1
        elapsed = time.ticks_diff(now, self._fps_since)
        if elapsed >= 1000:
            self._fps = self._fps_frames * 1000.0 / elapsed
            self._fps_frames = 0
            self._fps_since = now

    def _blit_band(self, band):
        # One band: the panel transfer of the previous band overlaps this
        # conversion.
        doom.blit_band(self._surface.buffer, band, self._surface.rows_per_band)

    # -- input ------------------------------------------------------------

    def key(self, code, pressed=True):
        doom.key(code, pressed)

    def keys(self):
        return {
            "left": doom.KEY_LEFT, "right": doom.KEY_RIGHT,
            "up": doom.KEY_UP, "down": doom.KEY_DOWN,
            "enter": doom.KEY_ENTER, "escape": doom.KEY_ESCAPE,
            "use": doom.KEY_USE, "fire": doom.KEY_FIRE,
            "yes": doom.KEY_YES, "no": doom.KEY_NO,
        }

    # -- measurements -----------------------------------------------------

    def get_stats(self):
        return {
            "fps": self._fps,
            "frames": self._frames,
            "wad": self._wad,
            "bands": self._surface.band_count if self._surface else 0,
            "rows_per_band": self._surface.rows_per_band if self._surface else 0,
        }

    def measure_frames(self, count=60):
        """Engine frame + full present, back to back."""
        self._benchmarking = True
        surface = self._surface
        try:
            for _ in range(3):
                doom.tick(time.ticks_ms())
                surface.present_all(self._blit_band)

            tick_us = 0
            present_us = 0
            start = time.ticks_us()
            for _ in range(count):
                t0 = time.ticks_us()
                doom.tick(time.ticks_ms())
                t1 = time.ticks_us()
                surface.present_all(self._blit_band)
                t2 = time.ticks_us()
                tick_us += time.ticks_diff(t1, t0)
                present_us += time.ticks_diff(t2, t1)
            elapsed_us = time.ticks_diff(time.ticks_us(), start)
        finally:
            self._benchmarking = False
        return {
            "frames": count,
            "fps": count * 1000000.0 / elapsed_us if elapsed_us else 0.0,
            "tick_ms": tick_us / 1000.0 / count,
            "present_ms": present_us / 1000.0 / count,
            "bands": surface.band_count,
            "rows_per_band": surface.rows_per_band,
        }
