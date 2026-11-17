"""Doom, running as a flash-resident core (PoC).

The engine is not a MicroPython module here: it is a blob in the ``retro-core``
flash partition, linked for a fixed address, mapped executable at start-up and
called through the small ABI in ``c_mpos/core_abi.h`` (see AGENTS.md, "Engines
bigger than executable RAM"). That is what makes a Doom-sized engine possible on
an S3: its code never has to fit in executable RAM.

What this activity provides to the core, through the ABI:

* the surface: the core converts and rotates its 320x200 frame into a 200x320
  RGB565 surface, and this file copies bands into the ``NativeDisplay`` buffer;
* the WAD: file reads go through MicroPython's file objects, so storage stays
  the OS's business (no POSIX layer inside the core);
* memory for the engine's zone, and log lines;
* input: key events queued here are drained by the core once per frame.

It is a proof of concept: the engine boots, plays its demo, and takes input from
the touchscreen.
"""

import time

import lvgl as lv

import mpos.ui
from mpos import Activity, InputManager

import mpos_core

# Ships with the app as well as in the firmware: an .mpk has to run on firmware
# older than the one that first froze mpos.ui.native_display.
from native_display import NativeDisplay

CORE_PARTITION = "retro-core"
CORE_PARTITION_SIZE = 0xF0000

# The core rotates Doom's 320x200 frame into a portrait surface that fits the
# panel, so the picture is upright when the device lies on its long side.
SURFACE_WIDTH = 200
SURFACE_HEIGHT = 320

TARGET_FPS = 35
FRAME_SLACK_MS = 5
TAP_MS = 220

# Doom's own key codes (doomkeys.h), not ASCII.
KEY_RIGHTARROW = 0xAE
KEY_LEFTARROW = 0xAC
KEY_UPARROW = 0xAD
KEY_DOWNARROW = 0xAF
KEY_USE = 0xA2
KEY_FIRE = 0xA3
KEY_ENTER = 13
KEY_ESCAPE = 27

WAD_CANDIDATES = (
    "/sdcard/doom1.wad",
    "/sdcard/doom/doom1.wad",
    "/roms/doom/doom1.wad",
    "/doom1.wad",
    "doom1.wad",
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


class DoomCore(Activity):

    screen = None
    _surface = None
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
    _tick_us = 0
    _present_us = 0
    _touch_key = 0
    _touch_ms = 0

    def onCreate(self):
        self.screen = lv.obj()
        self.screen.add_flag(lv.obj.FLAG.CLICKABLE)
        self.screen.add_event_cb(self._on_touch, lv.EVENT.ALL, None)
        self.screen.add_event_cb(self._on_key, lv.EVENT.KEY, None)
        lv.group_get_default().add_obj(self.screen)

        self._keys = []
        self._files = {}
        self.setContentView(self.screen)

    def onResume(self, screen):
        self._paused = False
        if not self._started:
            self._started = True
            self._surface = NativeDisplay(
                self.screen, width=SURFACE_WIDTH, height=SURFACE_HEIGHT)
            self._wad = find_wad(getattr(self, "intent", None))
            if self._wad is None:
                if __debug__:
                    print("doom: no WAD found, looked at %s" % (WAD_CANDIDATES,))
            else:
                # An earlier session may have left the core mapped (an activity
                # that was torn down by an exception never reaches onStop).
                try:
                    mpos_core.stop()
                except Exception:
                    pass
                # MicroPython does not trace C statics, so the callbacks live
                # here for as long as the core does.
                self._callbacks = (
                    self._present_band, self._palette, self._poll_key,
                    self._read_file, self._file_size, self._log)
                mpos_core.start(
                    CORE_PARTITION, 0, CORE_PARTITION_SIZE,
                    *self._callbacks,
                    self._wad, SURFACE_WIDTH, SURFACE_HEIGHT)
                if __debug__:
                    print("doom: core at 0x%x, %d bytes of text, wad %s" % (
                        mpos_core.mapped(), mpos_core.mapped_size(), self._wad))

        self._surface.begin()
        self._next_frame_ms = time.ticks_ms()
        self._fps_since = self._next_frame_ms
        self._fps_frames = 0
        mpos.ui.task_handler.add_event_cb(
            self._drawframe, mpos.ui.task_handler.TASK_HANDLER_FINISHED)

    def onPause(self, screen):
        self._paused = True
        mpos.ui.task_handler.remove_event_cb(self._drawframe)
        self._keys = []
        if self._surface is not None:
            self._surface.end()

    def onStop(self, screen):
        if self._started:
            try:
                mpos_core.stop()
            except Exception:
                pass
            for file in self._files.values():
                try:
                    file.close()
                except Exception:
                    pass
            self._files = {}
            self._started = False
            self._wad = None

    def _drawframe(self, arg1=None, arg2=None):
        if self._paused or self._wad is None or self._error is not None:
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, self._next_frame_ms) < -FRAME_SLACK_MS:
            return
        self._next_frame_ms = time.ticks_add(now, self._frame_interval_ms)

        tick_us = time.ticks_us()
        try:
            mpos_core.tick(now)
        except Exception as error:
            # One traceback instead of one per frame, and stop drawing the stale
            # surface: a core that faults must not take the UI down with it.
            self._error = error
            print("doom: tick failed: %s" % (error,))
            return

        tick_us = time.ticks_diff(time.ticks_us(), tick_us)
        present_us = time.ticks_us()

        # The core already wrote the pixels; this only invalidates and flushes.
        surface = self._surface
        for band in range(surface.band_count):
            surface.invalidate_band(band)
        surface.frames += 1
        surface.flush()

        present_us = time.ticks_diff(time.ticks_us(), present_us)
        self._tick_us += tick_us
        self._present_us += present_us

        self._frames += 1
        self._fps_frames += 1
        elapsed = time.ticks_diff(now, self._fps_since)
        if elapsed >= 1000:
            frames = self._fps_frames
            self._fps = frames * 1000.0 / elapsed
            self._fps_frames = 0
            self._fps_since = now
            if __debug__ and frames:
                print("doom: %.1f fps, tick %.1f ms, present %.1f ms" % (
                    self._fps, self._tick_us / 1000.0 / frames,
                    self._present_us / 1000.0 / frames))
            self._tick_us = 0
            self._present_us = 0

    # -- ABI callbacks ----------------------------------------------------

    def _present_band(self, band, rows, data):
        start = band * SURFACE_WIDTH * 2
        self._surface.buffer[start:start + len(data)] = data

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

    # -- input ------------------------------------------------------------

    def key(self, code, pressed=True):
        """Queue one engine key event (see the engine's doomkeys.h)."""
        if pressed:
            self._keys.append((code, True))
            self._keys.append((code, False))
        else:
            self._keys.append((code, False))

    def _on_key(self, event):
        key = event.get_key()
        mapping = {
            lv.KEY.LEFT: KEY_LEFTARROW,
            lv.KEY.RIGHT: KEY_RIGHTARROW,
            lv.KEY.UP: KEY_UPARROW,
            lv.KEY.DOWN: KEY_DOWNARROW,
            lv.KEY.ENTER: KEY_ENTER,
            lv.KEY.ESC: KEY_ESCAPE,
        }
        code = mapping.get(key)
        if code is not None:
            self.key(code)

    def _touch_code(self, x):
        # Left third turns left, right third turns right, the middle walks; a
        # short tap in the middle fires.
        width = mpos.ui.main_display.get_horizontal_resolution()
        if x < width // 3:
            return KEY_LEFTARROW
        if x > (2 * width) // 3:
            return KEY_RIGHTARROW
        return KEY_UPARROW

    def _on_touch(self, event):
        code = event.get_code()
        if code == lv.EVENT.PRESSED:
            x, _ = InputManager.pointer_xy()
            self._touch_key = self._touch_code(x)
            self._touch_ms = time.ticks_ms()
            self._keys.append((self._touch_key, True))
        elif code == lv.EVENT.RELEASED:
            if self._touch_key:
                self._keys.append((self._touch_key, False))
                if (self._touch_key == KEY_UPARROW
                        and time.ticks_diff(time.ticks_ms(), self._touch_ms) < TAP_MS):
                    self._keys.append((KEY_FIRE, True))
                    self._keys.append((KEY_FIRE, False))
                self._touch_key = 0

    # -- measurements -----------------------------------------------------

    def get_stats(self):
        return {
            "fps": self._fps,
            "frames": self._frames,
            "wad": self._wad,
            "error": self._error,
            "bands": self._surface.band_count if self._surface else 0,
            "rows_per_band": self._surface.rows_per_band if self._surface else 0,
        }
