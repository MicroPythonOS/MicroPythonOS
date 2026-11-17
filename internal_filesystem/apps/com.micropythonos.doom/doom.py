# Doom, running as a native (C) engine inside a MicroPythonOS activity.
#
# The engine is doomgeneric built as a MicroPython native module
# (c_mpos/doom/): it keeps an 8-bit paletted 320x200 framebuffer and this file
# converts it to RGB565 one band at a time while the panel is being fed, so the
# conversion costs nothing extra (see docs/apps/native-apps.md).
#
# Controls - keyboard and mouse (desktop), and touch on a landscape panel:
#
#   arrows / joystick   turn and walk
#   Enter               use / open, and select in a menu
#   B or space          fire
#   Y                   Doom's menu (Esc is the OS "back" key)
#   left third          turn left (hold)
#   right third         turn right (hold)
#   middle              walk forward (hold)
#   tap middle          fire
#   tap top edge        menu
import lvgl as lv
import mpos.ui
import sys
import time

from mpos import Activity, InputManager

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

# A held key is released after this long unless the input repeats it. The SDL
# keyboard reports a press per repeat and no release at all, and a badge keypad
# only reports presses, so every direction is a timed hold.
HOLD_MS = 180
# A tap is "short" if it is released within this window; a short tap on the walk
# zone fires.
TAP_MS = 450
MENU_STRIP_PX = 24
HINT_MS = 6000

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
    hint = None
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
    _touch_key = 0
    _touch_ms = 0
    _hint_until = 0
    _keys_sent = 0

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
        # Nothing ticks the engine while paused, so a half-pressed direction is
        # released now instead of being replayed on resume.
        for code in list(self._held):
            self.key(code, False)
        self._held = {}
        if self._surface is not None:
            self._surface.end()

    def _drawframe(self, arg1=None, arg2=None):
        if self._paused or self._benchmarking or self._wad is None:
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, self._next_frame_ms) < -FRAME_SLACK_MS:
            return
        self._next_frame_ms = time.ticks_add(now, self._frame_interval_ms)

        self._release_held(now)
        self._expire_hint(now)
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
        """Send one engine key event (see the engine's doomkeys.h)."""
        self._keys_sent += 1
        doom.key(code, pressed)

    def tap(self, code):
        self.key(code, True)
        self.key(code, False)

    def keys(self):
        return {
            "left": doom.KEY_LEFT, "right": doom.KEY_RIGHT,
            "up": doom.KEY_UP, "down": doom.KEY_DOWN,
            "enter": doom.KEY_ENTER, "escape": doom.KEY_ESCAPE,
            "use": doom.KEY_USE, "fire": doom.KEY_FIRE,
            "yes": doom.KEY_YES, "no": doom.KEY_NO,
        }

    def _hold(self, code):
        """Start a held key; it is released after HOLD_MS unless refreshed."""
        if code not in self._held:
            self.key(code, True)
        self._held[code] = time.ticks_add(time.ticks_ms(), HOLD_MS)

    def _release_held(self, now):
        for code in list(self._held):
            if time.ticks_diff(now, self._held[code]) >= 0:
                self.key(code, False)
                del self._held[code]

    def _on_key(self, event):
        key = event.get_key()
        if key == lv.KEY.LEFT:
            self._hold(doom.KEY_LEFT)
        elif key == lv.KEY.RIGHT:
            self._hold(doom.KEY_RIGHT)
        elif key == lv.KEY.UP:
            self._hold(doom.KEY_UP)
        elif key == lv.KEY.DOWN:
            self._hold(doom.KEY_DOWN)
        elif key == lv.KEY.NEXT:
            self._hold(doom.KEY_RIGHT)
        elif key == lv.KEY.PREV:
            self._hold(doom.KEY_LEFT)
        elif key == lv.KEY.ENTER:
            # Enter selects in a menu (the engine acts on the key event itself)
            # and opens doors in game, where the key has to stay down for at
            # least one tic: a press and a release drained in the same frame
            # cancel out before the tic is built.
            self.tap(doom.KEY_ENTER)
            self._hold(doom.KEY_USE)
        elif key == ord("B") or key == ord("b") or key == 0x20:
            self._hold(doom.KEY_FIRE)
        elif key in (lv.KEY.ESC, ord("Y"), ord("y"), lv.KEY.END):
            # Esc would be the natural Doom menu key, but the OS claims it as
            # "back" on the desktop (board/linux.py) and on the 2026 badge, so
            # it never arrives here. Y is the menu, as on the badge.
            self.tap(doom.KEY_ESCAPE)

    def _zone_key(self, x):
        width = mpos.ui.main_display.get_horizontal_resolution()
        if x < width // 3:
            return doom.KEY_LEFT
        if x > (2 * width) // 3:
            return doom.KEY_RIGHT
        return doom.KEY_UP

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
                self.tap(doom.KEY_ESCAPE)
                return
            self._touch_key = self._zone_key(x)
            self._touch_ms = time.ticks_ms()
            self.key(self._touch_key, True)
        elif code == lv.EVENT.RELEASED:
            if self._touch_key:
                self.key(self._touch_key, False)
                held = time.ticks_diff(time.ticks_ms(), self._touch_ms)
                if self._touch_key == doom.KEY_UP and held < TAP_MS:
                    self._hold(doom.KEY_FIRE)
                self._touch_key = 0

    # -- hint -------------------------------------------------------------

    def _show_hint(self):
        text = ("turn: left / right\n"
                "walk: middle\n"
                "fire: tap or B\n"
                "menu: Y or top edge")
        label = lv.label(self.screen)
        label.set_text(text)
        label.set_style_bg_color(lv.color_hex(0x000000), lv.PART.MAIN)
        label.set_style_bg_opa(lv.OPA._70, lv.PART.MAIN)
        label.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        label.set_style_pad_all(6, lv.PART.MAIN)
        label.set_style_radius(6, lv.PART.MAIN)
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
            "keys": self._keys_sent,
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
