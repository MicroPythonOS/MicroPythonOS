"""Doom, running as a flash-resident core (PoC).

The engine is not a MicroPython module here: it is a blob in the ``retro-core``
flash partition, linked for a fixed address, mapped executable at start-up and
called through the small ABI in ``c_mpos/core_abi.h`` (see AGENTS.md, "Engines
bigger than executable RAM"). That is what makes a Doom-sized engine possible on
an S3: its code never has to fit in executable RAM.

What this activity provides to the core, through the ABI:

* the surface: the core draws RGB565 straight into the ``NativeDisplay``
  buffer, one display band at a time, so the panel transfer of one band runs
  while the next band is being converted;
* the WAD: file reads go through MicroPython's file objects, so storage stays
  the OS's business (no POSIX layer inside the core);
* memory for the engine's zone, and log lines;
* input: key events queued here are drained by the core once per frame.

Controls - touch (Waveshare 2", fri3d 2026, any touch panel):

    left third      turn left (hold)
    right third     turn right (hold)
    middle          walk forward (hold)
    tap middle      fire
    tap top edge    menu / back

Controls - buttons (fri3d 2024 and 2026; both send the same key events):

    joystick / arrows   turn and walk
    A (ENTER)           use / open, and select in menus
    B                   fire
    Y                   Doom's menu / back
    X (ESC)             leaves the app (the OS treats ESC as "back")

A single-button board can only fire; the IMU could steer some day, not now.
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
# A tap is "short" if it is released within this window. Generous on purpose:
# the input test helper holds a press for ~100 ms of wall clock, which a busy
# frame loop stretches to 300 ms, and a real finger is slower than that too.
TAP_MS = 450
HOLD_MS = 180
HINT_MS = 6000
MENU_STRIP_PX = 24

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
    hint = None
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
    _keys_sent = 0
    _touch_key = 0
    _touch_ms = 0
    _last_touch = None
    _hint_until = 0

    def onCreate(self):
        self.screen = lv.obj()
        self.screen.add_flag(lv.obj.FLAG.CLICKABLE)
        self.screen.add_event_cb(self._on_touch, lv.EVENT.ALL, None)
        self.screen.add_event_cb(self._on_key, lv.EVENT.KEY, None)
        lv.group_get_default().add_obj(self.screen)

        self._keys = []
        self._held = {}
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
                    self._wad, SURFACE_WIDTH, SURFACE_HEIGHT,
                    self._surface.buffer, self._surface.rows_per_band)
                if __debug__:
                    print("doom: core at 0x%x, %d bytes of text, wad %s" % (
                        mpos_core.mapped(), mpos_core.mapped_size(), self._wad))
                self._show_hint()

        self._surface.begin()
        self._next_frame_ms = time.ticks_ms()
        self._fps_since = self._next_frame_ms
        self._fps_frames = 0
        mpos.ui.task_handler.add_event_cb(
            self._drawframe, mpos.ui.task_handler.TASK_HANDLER_FINISHED)

    def onPause(self, screen):
        self._paused = True
        mpos.ui.task_handler.remove_event_cb(self._drawframe)
        # Nothing ticks the core while paused, so queued events and held keys
        # are dropped rather than replayed on resume.
        self._keys = []
        self._held = {}
        if self._surface is not None:
            self._surface.end()

    def onStop(self, screen):
        # Leave the shared focus group clean: the framework also does this, but
        # an activity that is torn down without it leaves a widget behind.
        try:
            lv.group_get_default().remove_obj(self.screen)
        except Exception:
            pass
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

        try:
            mpos_core.tick(now)
        except Exception as error:
            # One traceback instead of one per frame, and stop drawing the stale
            # surface: a core that faults must not take the UI down with it.
            self._error = error
            print("doom: tick failed: %s" % (error,))
            return

        # Held keys are released here rather than by the input driver: a keypad
        # only reports presses (and repeats), and Doom wants both edges.
        for code, deadline in list(self._held.items()):
            if time.ticks_diff(now, deadline) >= 0:
                self._keys.append((code, False))
                del self._held[code]

        self._expire_hint(now)

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

    # -- ABI callbacks ----------------------------------------------------

    def _present_band(self, band, rows, data):
        """A band is ready: copy it (if the core sent pixels) and flush it.

        The core draws straight into ``surface.buffer`` and only announces the
        band, so this is where the panel transfer is started - before the core
        converts the next band.
        """
        if data is not None:
            start = band * SURFACE_WIDTH * 2
            self._surface.buffer[start:start + len(data)] = data
        if not self._surface._active:
            return
        self._surface.invalidate_band(band // self._surface.rows_per_band)
        self._surface.flush()

    def _palette(self, entries):
        # The core converts its own palette; this is here for completeness.
        return bytes(entries * 2)

    def _poll_key(self):
        if not self._keys:
            return -1
        code, pressed = self._keys.pop(0)
        self._keys_sent += 1
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

    def _hold(self, code):
        """Start a held key; it is released after HOLD_MS unless refreshed."""
        if code not in self._held:
            self._keys.append((code, True))
        self._held[code] = time.ticks_add(time.ticks_ms(), HOLD_MS)

    def _release(self, code):
        if code in self._held:
            self._keys.append((code, False))
            del self._held[code]

    def _on_key(self, event):
        key = event.get_key()
        if key == lv.KEY.LEFT:
            self._hold(KEY_LEFTARROW)
        elif key == lv.KEY.RIGHT:
            self._hold(KEY_RIGHTARROW)
        elif key == lv.KEY.UP:
            self._hold(KEY_UPARROW)
        elif key == lv.KEY.DOWN:
            self._hold(KEY_DOWNARROW)
        elif key == lv.KEY.NEXT:
            self._hold(KEY_RIGHTARROW)
        elif key == lv.KEY.PREV:
            self._hold(KEY_LEFTARROW)
        elif key == lv.KEY.ENTER:
            # A is ENTER: menu select, and "use" while playing (ENTER itself is
            # not bound in game, so both can be sent). Use has to stay down for
            # a tic: the engine drains the whole queue per frame, so a press and
            # a release queued together cancel out before the tic is built.
            self.key(KEY_ENTER)
            self._hold(KEY_USE)
        elif key == lv.KEY.ESC:
            self.key(KEY_ESCAPE)
        elif key == ord("B"):
            self._hold(KEY_FIRE)
        elif key == ord("Y"):
            # Not ESC: fri3d 2026 hands ESC to the OS (back to the launcher),
            # so the Doom menu needs a key of its own.
            self.key(KEY_ESCAPE)
        elif key == lv.KEY.END:
            self.key(KEY_ESCAPE)

    def _touch_code(self, x):
        # Left third turns left, right third turns right, the middle walks.
        width = mpos.ui.main_display.get_horizontal_resolution()
        if x < width // 3:
            return KEY_LEFTARROW
        if x > (2 * width) // 3:
            return KEY_RIGHTARROW
        return KEY_UPARROW

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
            if y < MENU_STRIP_PX:
                # The top edge is the menu, not a movement zone.
                self._touch_key = 0
                self.key(KEY_ESCAPE)
                return
            self._touch_key = self._touch_code(x)
            self._touch_ms = time.ticks_ms()
            self._last_touch = ("p", x, y, self._touch_key)
            self._keys.append((self._touch_key, True))
        elif code == lv.EVENT.RELEASED:
            if self._touch_key:
                self._keys.append((self._touch_key, False))
                held = time.ticks_diff(time.ticks_ms(), self._touch_ms)
                self._last_touch = ("r", self._touch_key, held)
                if self._touch_key == KEY_UPARROW and held < TAP_MS:
                    self._hold(KEY_FIRE)
                self._touch_key = 0

    # -- hint -------------------------------------------------------------

    def _show_hint(self):
        text = ("turn: left / right\n"
                "walk: middle\n"
                "fire / select: tap\n"
                "menu: top edge")
        label = lv.label(self.screen)
        label.set_text(text)
        label.set_style_bg_color(lv.color_hex(0x000000), lv.PART.MAIN)
        label.set_style_bg_opa(lv.OPA._70, lv.PART.MAIN)
        label.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        label.set_style_pad_all(6, lv.PART.MAIN)
        label.set_style_radius(6, lv.PART.MAIN)
        # The surface is rotated by the core, so an overlay has to be rotated
        # too: drawn as-is it would read sideways on the panel.
        label.set_style_transform_rotation(900, lv.PART.MAIN)
        label.align(lv.ALIGN.CENTER, 0, 0)
        label.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.hint = label
        self._hint_until = time.ticks_add(time.ticks_ms(), HINT_MS)

    def _expire_hint(self, now):
        if self.hint is not None and time.ticks_diff(now, self._hint_until) >= 0:
            self.hint.delete()
            self.hint = None

    # -- measurements -----------------------------------------------------

    def get_stats(self):
        return {
            "fps": self._fps,
            "frames": self._frames,
            "wad": self._wad,
            "error": self._error,
            "keys": self._keys_sent,
            "touch": self._last_touch,
            "bands": self._surface.band_count if self._surface else 0,
            "rows_per_band": self._surface.rows_per_band if self._surface else 0,
        }
