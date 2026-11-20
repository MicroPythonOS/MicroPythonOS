"""An activity whose picture comes from a native engine.

A game engine that renders its own frames (a C module, or a blob in the
flash-resident core partition) needs the same four things from MicroPythonOS no
matter which engine it is: a surface the engine can draw into, a paced tick, an
input path and a way to say "the player quit". This class owns that half, so an
app is left with its engine, its controls and its assets.

What a subclass provides
------------------------
* ``engine`` - an object with ``surface_size(display)``, ``start(wad_or_data,
  surface)``, ``tick(now)``, ``key(code, pressed)``, ``resume()``, ``pause()``,
  ``stop()`` and a ``quit`` flag. ``com.micropythonos.doom`` has two of them
  (the core and the native module) behind that one shape.
* ``start_engine(surface)`` - called once, when the surface exists; return
  False (or raise) when there is nothing to run, and the activity shows
  ``self.error`` instead of pumping frames.
* optionally ``on_frame(now)`` for a presentation policy of its own: the
  default ticks the engine, which presents its bands itself; Breakout instead
  asks its renderer which bands are dirty and calls
  ``surface.present(bands, render)``.
* optionally ``on_screen(screen)`` to add widgets, and ``on_resumed`` /
  ``on_paused`` for game state.

What it owns
------------
The screen and its event handlers, the surface lifecycle, frame pacing and fps
stats, the hint/message labels (rotated with the picture on a portrait panel),
``to_game()`` for touch coordinates, and closing the activity - either on the
OS back key or when ``engine.quit`` goes true.

The engine contract's one asymmetry: an engine presents in *the surface's*
orientation. The core rotates Doom's 320x200 frame into a 200x320 surface for a
portrait panel; the native module cannot, so on such a panel the surface is the
engine's own and the picture is letterboxed sideways.
"""

import time

import lvgl as lv

import mpos.ui
from mpos import Activity, InputManager
from mpos.ui.native_display import NativeDisplay
from mpos.ui.native_input import KeyHolds, TouchFingers, TouchMonitor

# Doom's own tic rate is 35 and its frame is what limits a full redraw; a game
# that presents whole frames wants ~30, one that presents dirty bands can go
# higher. A subclass sets its own.
DEFAULT_FPS = 30
FRAME_SLACK_MS = 5
HINT_MS = 6000

# A finger's phase from TouchFingers is a plain name; an activity sees LVGL's
# event codes, the same ones on_pointer() gets from a single-pointer panel.
TOUCH_EVENTS = {
    TouchFingers.PRESSED: lv.EVENT.PRESSED,
    TouchFingers.MOVING: lv.EVENT.PRESSING,
    TouchFingers.RELEASED: lv.EVENT.RELEASED,
}

# The screen is registered for EVENT.ALL so it gets the pointer events, but
# that also delivers refresh, draw and style events. on_pointer() is only
# promised the three input codes, and a refresh event has no touch position.
POINTER_EVENTS = (lv.EVENT.PRESSED, lv.EVENT.PRESSING, lv.EVENT.RELEASED)


class NativeActivity(Activity):

    engine = None
    target_fps = DEFAULT_FPS
    frame_slack_ms = FRAME_SLACK_MS
    hint_text = None
    hint_ms = HINT_MS
    surface_width = None
    surface_height = None
    # A panel that can report more than one point can drive two thumbs at
    # once, but LVGL's pointer device only ever shows one of them (a second
    # finger is reported as a release, on purpose, so a pinch cannot click).
    # A game that wants both sets this and receives every finger through
    # on_touch_finger() instead of on_pointer().
    touch_fingers = False
    # LVGL never delivers a key release, so a keypad press is normally a timed
    # hold that a repeat has to refresh. A game sets this to use the keypad's
    # real held state instead, when the driver can report it: pressing turns at
    # once, releasing stops within a frame, and the keypad's typing repeats are
    # switched off while the game is in the foreground (a repeated menu press
    # would open and close the menu). A driver that cannot report held state
    # keeps the timed behaviour, so this is safe on every board.
    key_state = False
    # Set audio_rate when the engine has a mixer: the base then opens a PCM sink
    # and pulls `engine.audio_mix(buffer)` at that rate, every frame.
    audio_rate = None
    audio_output_kind = "i2s"

    screen = None
    error = None
    hint = None
    _surface = None
    _paused = True
    _started = False
    _leaving = False
    _next_frame_ms = 0
    _frame_interval_ms = 1000 // DEFAULT_FPS
    _frames = 0
    _fps = 0.0
    _fps_since = 0
    _fps_frames = 0
    _hint_until = 0
    _rotated = False
    # The engine's own frame, when the surface is a scaled copy of it. None
    # means the surface size is the frame size.
    _game_width = None
    _game_height = None
    _keys_sent = 0
    _sink = None
    _audio_buffer = None
    _audio_ms = 0
    touch = None
    # Games stack (a game under a settings dialog), so typing repeats come back
    # only when the last activity that wanted key state pauses.
    _keypad_state_users = 0
    _keypad_state_active = False

    # -- lifecycle --------------------------------------------------------

    def onCreate(self):
        self.screen = lv.obj()
        self.screen.add_flag(lv.obj.FLAG.CLICKABLE)
        self.screen.add_event_cb(self._on_touch, lv.EVENT.ALL, None)
        self.screen.add_event_cb(self._on_key, lv.EVENT.KEY, None)
        # Without this the keyboard has nowhere to send its keys: the SDL
        # keypad driver delivers to the focused object of the default group.
        lv.group_get_default().add_obj(self.screen)

        self._frame_interval_ms = 1000 // self.target_fps
        self._keys_sent = 0
        self.holds = KeyHolds(
            self.key, source=InputManager.held_keys if self.key_state else None)
        self.touch = TouchMonitor() if self.touch_fingers else None
        self.on_screen(self.screen)
        self.setContentView(self.screen)

    def onResume(self, screen):
        self._paused = False
        self._keypad_state(True)
        if not self._started:
            self._started = True
            self._begin_session()
        if self.error is not None or self._surface is None:
            return
        if self.engine is not None:
            self.engine.resume()
        self._open_audio()
        self._surface.begin()
        self._next_frame_ms = time.ticks_ms()
        self._fps_since = self._next_frame_ms
        self._fps_frames = 0
        mpos.ui.task_handler.add_event_cb(
            self._drawframe, mpos.ui.task_handler.TASK_HANDLER_FINISHED)
        self.on_resumed()

    def onPause(self, screen):
        self._paused = True
        self._keypad_state(False)
        mpos.ui.task_handler.remove_event_cb(self._drawframe)
        self.on_paused()
        # Nothing ticks the engine while paused, so a half-pressed direction is
        # released now instead of being replayed on resume.
        if self.holds is not None:
            self.holds.release_all()
        if self.touch is not None:
            # A finger that is still on the panel across the pause is a new
            # press when the game comes back, not a held one.
            self.touch.reset()
        if self.engine is not None:
            self.engine.pause()
        self._close_audio()
        if self._surface is not None:
            self._surface.end()

    def onStop(self, screen):
        self._keypad_state(False)
        # Leave the shared focus group clean: the framework also does this, but
        # an activity that is torn down without it leaves a widget behind.
        try:
            lv.group_get_default().remove_obj(self.screen)
        except Exception:
            pass
        # The sink goes first: an engine that is stopped while its samples are
        # still in the hardware's ring is a device writing into memory that no
        # longer belongs to it.
        self._close_audio()
        if self.engine is not None:
            self.engine.stop()
        # A resumed activity starts a fresh engine; see _begin_session().
        self.engine = None
        self._started = False

    def _keypad_state(self, active):
        """Turn the keypads' typing repeats off (or back on) for this activity.

        Only drivers that can also report their held state are touched: for one
        that cannot, a repeat is the only thing that keeps a press alive, so
        switching it off would make every hold stop after HOLD_MS.
        """
        if not self.key_state or active == self._keypad_state_active:
            return
        self._keypad_state_active = active
        if active:
            NativeActivity._keypad_state_users += 1
        elif NativeActivity._keypad_state_users > 0:
            NativeActivity._keypad_state_users -= 1
        enabled = NativeActivity._keypad_state_users == 0
        for indev in InputManager.list_indevs():
            setter = getattr(indev, "set_repeat_enabled", None)
            if setter is None or getattr(indev, "held_keys", None) is None:
                continue
            try:
                setter(enabled)
            except Exception:
                pass

    def _begin_session(self):
        self._frame_interval_ms = 1000 // self.target_fps
        try:
            display = mpos.ui.main_display
            engine = self.make_engine()
            self.engine = engine
            if engine is not None:
                width, height = engine.surface_size(display)
            else:
                width = self.surface_width or display.get_horizontal_resolution()
                height = self.surface_height or display.get_vertical_resolution()
            self._surface = NativeDisplay(
                self.screen, width=width, height=height)
            # A surface taller than it is wide means the engine transposed the
            # picture, so overlays and touch coordinates have to follow.
            self._rotated = height > width
            # An engine that presents its frame scaled says what its own frame
            # is; a 240x240 panel gets Doom's 320x200 at three quarters.
            self._game_width = None
            self._game_height = None
            frame = getattr(engine, "frame_size", None) if engine else None
            if frame is not None:
                self._game_width, self._game_height = frame
            started = self.start_engine(self._surface)
        except Exception as error:
            # The engine is the one part of such an app that can be missing: a
            # firmware without the module, a board without the partition, a
            # checkout without the .mpy. Say so instead of a black screen.
            self.error = error
            print("%s: %s" % (self.who(), error))
            self.show_message(str(error))
            return
        if started is False:
            return
        if self.hint_text:
            self.show_hint(self.hint_text)

    def who(self):
        """A name for log lines: the app's full name once it has one."""
        return getattr(self, "appFullName", None) or type(self).__name__

    # -- subclass hooks ---------------------------------------------------

    def make_engine(self):
        """The engine for this host; may raise when there is none."""
        return self.engine

    def on_screen(self, screen):
        """Add widgets to the activity's screen before it is shown."""

    def start_engine(self, surface):
        """Start the engine on this surface; return False if there is nothing to run."""
        self.engine.start(surface)
        return True

    def on_resumed(self):
        """The frame loop is about to run (a timer, saved state, ...)."""

    def on_paused(self):
        """The frame loop stopped (save state, silence, ...)."""

    def on_key_event(self, key):
        """A keyboard or keypad key (an ``lv.KEY`` value)."""

    def on_pointer(self, event_code, x, y):
        """PRESSED / PRESSING / RELEASED at a panel point."""

    def on_touch_finger(self, finger, event_code, x, y):
        """One finger of a multi-point panel, when ``touch_fingers`` is set.

        ``finger`` stays the same while it is down, so an activity can keep a
        control state per thumb. The points are the same logical panel
        coordinates ``on_pointer()`` gets.
        """

    # -- frame loop -------------------------------------------------------

    def _drawframe(self, arg1=None, arg2=None):
        if self._paused or self.error is not None:
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, self._next_frame_ms) < -self.frame_slack_ms:
            return
        self._next_frame_ms = time.ticks_add(now, self._frame_interval_ms)

        self.holds.tick(now)
        self._poll_touch()
        self._expire_hint(now)
        try:
            self.on_frame(now)
        except Exception as error:
            # One traceback instead of one per frame, and stop drawing the stale
            # surface: an engine that faults must not take the UI down with it.
            self.error = error
            print("%s: frame failed: %s" % (self.who(), error))
            return

        if self.engine is not None and self.engine.quit:
            self._leave()
            return

        self._pump_audio(now)
        self._frames += 1
        self._fps_frames += 1
        elapsed = time.ticks_diff(now, self._fps_since)
        if elapsed >= 1000:
            frames = self._fps_frames
            self._fps = frames * 1000.0 / elapsed
            self._fps_frames = 0
            self._fps_since = now
            if __debug__ and frames:
                print("%s: %.1f fps" % (self.who(), self._fps))

    def on_frame(self, now):
        """One frame. The default advances the engine, which presents itself."""
        self.engine.tick(now)

    def _leave(self):
        """Close the activity because the engine asked for it (its menu)."""
        if self._leaving:
            return
        self._leaving = True
        self._paused = True
        mpos.ui.task_handler.remove_event_cb(self._drawframe)
        self.finish()

    # -- audio ------------------------------------------------------------

    def _open_audio(self):
        """Open the PCM sink the engine's mixer writes into.

        Which device that is comes from the user's choice in Settings -> Audio,
        with one exception an app can make: Doom's effects are 11 kHz broadband
        PCM, and a piezo resonator with no output below 2 kHz turns that into a
        screech, so it asks for `i2s` only and a buzzer-only board stays silent.
        A host with no PCM sink at all (an old firmware, a build without
        `machine.I2S` and without hosted_audio) also stays silent; the game is
        still playable.
        """
        if self.audio_rate is None or self._sink is not None:
            return
        from mpos import AudioManager
        output = AudioManager.get_default_output()
        if self.audio_output_kind is not None and (
            output is None or output.kind != self.audio_output_kind
        ):
            output = AudioManager.find_output_by_kind(self.audio_output_kind)
        if output is None:
            return
        try:
            self._sink = AudioManager.open_pcm(self.audio_rate, output=output)
        except AttributeError:
            self._sink = None
            return
        except Exception as error:
            print("%s: audio init failed: %s" % (self.who(), error))
            self._sink = None
            return
        if self._sink is None or not self._sink.active:
            self._sink = None
            return
        self._audio_buffer = bytearray(2048 * 2)
        self._audio_ms = time.ticks_ms()

    def _close_audio(self):
        if self._sink is not None:
            try:
                self._sink.close()
            except Exception:
                pass
            self._sink = None
        self._audio_buffer = None

    def _pump_audio(self, now):
        """Give the sink the samples the frame loop's elapsed time needs."""
        if self._sink is None:
            return
        elapsed = time.ticks_diff(now, self._audio_ms)
        if elapsed <= 0:
            return
        samples = (elapsed * self.audio_rate) // 1000
        if samples > 2048:
            samples = 2048
        elif samples < 64:
            return
        self._audio_ms = now
        view = memoryview(self._audio_buffer)[:samples * 2]
        self.engine.audio_mix(view)
        try:
            self._sink.write(view)
        except Exception:
            # A short write means the ring is full; the next frame catches up.
            pass

    # -- input ------------------------------------------------------------

    def key(self, code, pressed=True):
        """Send one engine key event."""
        if self.engine is None:
            return
        self._keys_sent += 1
        self.engine.key(code, pressed)

    def _on_key(self, event):
        self.on_key_event(event.get_key())

    def _on_touch(self, event):
        if event.get_code() not in POINTER_EVENTS:
            return
        # LVGL also sends PRESSED/RELEASED to the focused object when ENTER is
        # pressed on a keypad, so only a pointer may drive the touch zones.
        indev = lv.indev_active()
        if indev is not None and indev.get_type() != lv.INDEV_TYPE.POINTER:
            return
        touches = self.touch
        if touches is not None and touches.available:
            # The frame loop reports every finger instead, including the first
            # one: LVGL's pointer only ever shows one point of a multi-touch
            # panel, so handling its events as well would double the presses.
            return
        # setContentView loads the screen before onResume starts the engine, so
        # events can arrive when there is nothing to map them on to yet.
        if self._surface is None:
            return
        x, y = InputManager.pointer_xy()
        self._expire_hint(time.ticks_ms())
        self.on_pointer(event.get_code(), x, y)

    def _poll_touch(self):
        touches = self.touch
        if touches is None or not touches.available:
            return
        if self._surface is None:
            return
        for finger, phase, x, y in touches.poll():
            self.on_touch_finger(finger, TOUCH_EVENTS[phase], x, y)

    def _game_frame(self):
        """The engine's own frame: the surface, unless the picture is scaled."""
        if self._game_width and self._game_height:
            return self._game_width, self._game_height
        surface = self._surface
        if self._rotated:
            # A transposed surface has the frame's sides swapped.
            return surface.height, surface.width
        return surface.width, surface.height

    @staticmethod
    def _into_frame(panel_value, panel_length, frame_length):
        """A panel coordinate in the engine's frame, rounded to the nearest.

        The core samples a scaled surface with the same rounding, so a touch
        lands on the source pixel the panel is showing.
        """
        return (panel_value * frame_length + panel_length // 2) // panel_length

    @staticmethod
    def _onto_panel(frame_value, panel_length, frame_length):
        """The inverse of :meth:`_into_frame`."""
        return (frame_value * panel_length + frame_length // 2) // frame_length

    def to_game(self, x, y):
        """Panel point -> the engine's own frame.

        An engine that presents in a portrait surface has transposed its frame
        (a source pixel (sx, sy) lands at surface (199 - sy, sx)), so touch
        coordinates have to be turned back before they mean anything: without
        it, a thumb at the panel's left edge means the game's *top*. A surface
        smaller than the frame is scaled, and the point is scaled up by the
        same factor.
        """
        surface = self._surface
        dx = x - surface._image_x
        dy = y - surface._image_y
        game_width, game_height = self._game_frame()
        if not self._rotated:
            return (self._into_frame(dx, surface.width, game_width),
                    self._into_frame(dy, surface.height, game_height))
        return (self._into_frame(dy, surface.height, game_width),
                self._into_frame((surface.width - 1) - dx,
                                 surface.width, game_height))

    def game_to_panel(self, x, y):
        """A point in the engine's frame -> a panel point.

        The inverse of :meth:`to_game`: an app that draws over the picture
        (touch hints, a HUD) can place its widgets in the game's own
        coordinates and let this apply the scale, the letterbox and the
        rotation.
        """
        surface = self._surface
        game_width, game_height = self._game_frame()
        if not self._rotated:
            return (surface._image_x
                    + self._onto_panel(x, surface.width, game_width),
                    surface._image_y
                    + self._onto_panel(y, surface.height, game_height))
        return (surface._image_x + surface.width - 1
                - self._onto_panel(y, surface.width, game_height),
                surface._image_y
                + self._onto_panel(x, surface.height, game_width))

    def game_rect_to_panel(self, x, y, width, height):
        """A rect in the engine's frame -> ``(x, y, width, height)`` on the panel.

        A 90 degree rotation swaps the rect's width and height, and a scaled
        surface shrinks both, so overlays do not have to special-case either.
        """
        surface = self._surface
        game_width, game_height = self._game_frame()
        if not self._rotated:
            x0 = self._onto_panel(x, surface.width, game_width)
            y0 = self._onto_panel(y, surface.height, game_height)
            x1 = self._onto_panel(x + width - 1, surface.width, game_width)
            y1 = self._onto_panel(y + height - 1, surface.height, game_height)
            return (surface._image_x + x0, surface._image_y + y0,
                    x1 - x0 + 1, y1 - y0 + 1)
        top = self._onto_panel(x, surface.height, game_width)
        bottom = self._onto_panel(x + width - 1, surface.height, game_width)
        left = surface.width - 1 - self._onto_panel(
            y + height - 1, surface.width, game_height)
        right = surface.width - 1 - self._onto_panel(
            y, surface.width, game_height)
        return (surface._image_x + left, surface._image_y + top,
                right - left + 1, bottom - top + 1)

    # -- labels -----------------------------------------------------------

    def _add_label(self, text):
        label = lv.label(self.screen)
        label.set_text(text)
        label.set_style_bg_color(lv.color_hex(0x000000), lv.PART.MAIN)
        label.set_style_bg_opa(lv.OPA._70, lv.PART.MAIN)
        label.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        label.set_style_pad_all(6, lv.PART.MAIN)
        label.set_style_radius(6, lv.PART.MAIN)
        if self._rotated:
            # The engine rotated the picture for a portrait panel, so an
            # overlay has to be rotated too: as-is it would read sideways.
            label.set_style_transform_rotation(900, lv.PART.MAIN)
        label.align(lv.ALIGN.CENTER, 0, 0)
        label.remove_flag(lv.obj.FLAG.CLICKABLE)
        return label

    def _clear_hint(self):
        if self.hint is not None:
            try:
                self.hint.delete()
            except Exception:
                # The screen may have been torn down under the label already.
                pass
            self.hint = None

    def show_hint(self, text, ms=None):
        """Show controls/help for a few seconds."""
        self._clear_hint()
        self.hint = self._add_label(text)
        seconds = self.hint_ms if ms is None else ms
        self._hint_until = time.ticks_add(time.ticks_ms(), seconds)

    def show_message(self, text):
        """Show something that stays: a missing engine, a missing WAD."""
        self._clear_hint()
        self.hint = self._add_label(text)
        self._hint_until = 0

    def set_message(self, text):
        """Replace the standing message's text, reusing its label.

        A launch that reports progress would otherwise create and delete a
        label for every update.
        """
        if self.hint is None:
            self.hint = self._add_label(text)
            self._hint_until = 0
        else:
            self.hint.set_text(text)

    def _expire_hint(self, now):
        if (self.hint is not None and self._hint_until
                and time.ticks_diff(now, self._hint_until) >= 0):
            self._clear_hint()

    # -- measurements -----------------------------------------------------

    def native_stats(self):
        """The counters every native activity has; a subclass adds its own."""
        return {
            "fps": self._fps,
            "frames": self._frames,
            "error": self.error,
            "keys": self._keys_sent,
            "bands": self._surface.band_count if self._surface else 0,
            "rows_per_band": self._surface.rows_per_band if self._surface else 0,
        }

    def get_stats(self):
        return self.native_stats()
