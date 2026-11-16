# Breakout: a native (C) game on a MicroPythonOS activity.
#
# The C module in c_mpos/breakout/ owns the game state and draws the bands of
# rows that changed into an RGB565 surface. This file is the glue: input, save
# state, sound, and the frame loop.
#
# The frame loop is the interesting part. mpos.ui.native_display.NativeDisplay
# hands the renderer a full-screen buffer and shows it with one lv_image widget,
# so LVGL stays the only writer of the panel (no flicker) and only the bands
# that changed are blitted and flushed (a frame that moves the ball and the
# paddle costs two bands, not a whole screen).
import lvgl as lv
import mpos.ui
import time
from mpos import Activity, InputManager, SharedPreferences, AudioManager

import sys
if sys.platform == "esp32":
    import breakout_xtensawin as breakout
else:
    import breakout_x64 as breakout

# Ships with the app as well as in the firmware: an .mpk has to run on
# firmware older than the one that first froze mpos.ui.native_display.
from native_display import NativeDisplay


# Frames per second the pump aims for. Measured on the badge: a frame that
# touches two bands costs about 10ms end to end, so 50fps leaves half the budget
# free; a full screen redraw (level change) costs about 30ms.
TARGET_FPS = 50

# The frame loop runs on the task handler's passes, which are a few
# milliseconds apart. Presenting a frame that is up to this many milliseconds
# early keeps the pacing on its grid instead of slipping a whole pass each time.
FRAME_SLACK_MS = 5


class Beep:
    """Square-wave tones on the badge's piezo buzzer, without blocking.

    A game cannot afford AudioManager here: it decodes and streams on its own
    clock, which costs milliseconds per frame and allocates. Driving the piezo
    with a PWM channel costs a few microseconds and a deadline check.
    """

    def __init__(self, enabled=True):
        self._pwm = None
        self._off_at = None
        self._enabled = enabled
        self.tones = 0

    def _ensure_pwm(self):
        if self._pwm is not None or not self._enabled:
            return self._pwm
        try:
            from machine import Pin, PWM
            output = AudioManager.find_output_by_kind("buzzer")
            if output is None or output.buzzer_pin is None:
                # Boards without a piezo (this one has no audio at all) simply
                # play nothing; the game must not depend on sound.
                self._enabled = False
                return None
            self._pwm = PWM(Pin(output.buzzer_pin), freq=4000, duty_u16=0)
        except Exception:
            self._enabled = False
            self._pwm = None
        return self._pwm

    def tone(self, freq, ms):
        pwm = self._ensure_pwm()
        if pwm is None:
            return
        try:
            pwm.freq(freq)
            pwm.duty_u16(32768)
        except Exception:
            self._enabled = False
            return
        self.tones += 1
        self._off_at = time.ticks_add(time.ticks_ms(), ms)

    def poll(self, now_ms):
        if self._off_at is None or self._pwm is None:
            return
        if time.ticks_diff(now_ms, self._off_at) >= 0:
            self._off_at = None
            try:
                self._pwm.duty_u16(0)
            except Exception:
                pass

    def stop(self):
        self._off_at = None
        if self._pwm is not None:
            try:
                self._pwm.duty_u16(0)
                self._pwm.deinit()
            except Exception:
                pass
            self._pwm = None


class Breakout(Activity):

    # Play area and pacing.
    hor_res = 0
    ver_res = 0
    paddle_move_step = 0

    screen = None
    leftbutton = None
    rightbutton = None
    _display = None
    _frame_interval_ms = 1000 // TARGET_FPS
    _next_frame_ms = 0
    _paused = True
    _started = False

    # Touch tracking.
    touch_active = False
    touch_last_x = None

    # State mirrors of the native module (used for saving, not for display).
    score = 0
    level = 1
    lives = 5
    highscore = 0
    _autosaved_level = 0
    _autosaved_lives = 5
    _game_over_handled = False
    _state_timer = None

    _beep = None

    def onCreate(self):
        self.screen = lv.obj()
        self.screen.add_flag(lv.obj.FLAG.CLICKABLE)
        self.screen.add_event_cb(self.touch_cb, lv.EVENT.ALL, None)

        d = lv.display_get_default()
        self.hor_res = d.get_horizontal_resolution()
        self.paddle_move_step = round(self.hor_res / 10)
        self.ver_res = d.get_vertical_resolution()

        # Invisible buttons: they exist so the keypad indev has something to
        # focus, which is how the B/Y buttons reach move_left()/move_right().
        self.leftbutton = lv.button(self.screen)
        self.leftbutton.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        self.leftbutton.set_size(1, 1)
        self.leftbutton.set_style_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        self.leftbutton.add_event_cb(lambda e: self.move_left(), lv.EVENT.FOCUSED, None)

        # Invisible button, just for defocusing the left and right buttons:
        self.defocus_button = lv.button(self.screen)
        self.defocus_button.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.defocus_button.set_size(1, 1)
        self.defocus_button.set_style_opa(lv.OPA.TRANSP, lv.PART.MAIN)

        self.rightbutton = lv.button(self.screen)
        self.rightbutton.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        self.rightbutton.set_size(1, 1)
        self.rightbutton.set_style_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        self.rightbutton.add_event_cb(lambda e: self.move_right(), lv.EVENT.FOCUSED, None)

        self.setContentView(self.screen)

    def onResume(self, screen):
        self._paused = False
        self.highscore = SharedPreferences(self.appFullName).get_int("highscore", 0)

        if not self._started:
            self._started = True
            self._init_display()
            breakout.set_highscore(self.highscore)
            self._check_autoload()
            self._beep = Beep()

        self._display.begin()
        # The surface may hold anything after another activity used the panel.
        breakout.mark_all_dirty()
        self._next_frame_ms = time.ticks_ms()

        mpos.ui.task_handler.add_event_cb(self.drawframe, mpos.ui.task_handler.TASK_HANDLER_FINISHED)

        if self._state_timer is None:
            self._state_timer = lv.timer_create(self._update_state, 2000, None)

    def _init_display(self):
        self._display = NativeDisplay(self.screen)
        breakout.init(self._display.buffer, self.hor_res, self.ver_res)
        bands = breakout.set_band_rows(self._display.rows_per_band)
        if __debug__:
            print("breakout: %dx%d, %d bands of %d rows" % (
                self.hor_res, self.ver_res, bands, self._display.rows_per_band))

    def onPause(self, screen):
        self._paused = True
        mpos.ui.task_handler.remove_event_cb(self.drawframe)
        if self._display is not None:
            self._display.end()
        if self._beep is not None:
            self._beep.stop()
        self._save_state()
        self._stop_state_timer()

    def onDestroy(self, screen):
        self.onPause(screen)

    # -- frame loop -------------------------------------------------------

    def drawframe(self, arg1=None, arg2=None):
        if self._paused:
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, self._next_frame_ms) < -FRAME_SLACK_MS:
            return
        self._next_frame_ms = time.ticks_add(now, self._frame_interval_ms)

        breakout.tick(now)
        events = breakout.poll_events()
        beep = self._beep
        if beep is not None:
            if events:
                self._play_events(events)
            # Polled every frame, not just after an event: a tone has to be
            # turned off on time even when the next frame has nothing to say.
            beep.poll(now)

        self._display.present(self._dirty_bands(), breakout.render_band)

    def _dirty_bands(self):
        # next_dirty() keeps reporting a band until render_band() has drawn it,
        # so a renderer that forgets to clear a flag would spin here forever.
        # Seen bands are skipped for that reason.
        seen = 0
        band = breakout.next_dirty()
        while band >= 0 and not (seen >> band) & 1:
            seen |= 1 << band
            yield band
            band = breakout.next_dirty()

    # -- sound ------------------------------------------------------------

    def _play_events(self, events):
        beep = self._beep
        if beep is None:
            return
        if events & breakout.EVENT_LOST_LIFE:
            beep.tone(300, 350)
        elif events & breakout.EVENT_LEVEL_UP:
            beep.tone(2400, 120)
        elif events & breakout.EVENT_GAME_OVER:
            beep.tone(200, 600)
        elif events & breakout.EVENT_BRICK:
            beep.tone(3200, 25)
        elif events & breakout.EVENT_PADDLE:
            beep.tone(4400, 20)
        elif events & breakout.EVENT_WALL:
            beep.tone(2400, 15)

    # -- input ------------------------------------------------------------

    def move_left(self):
        # A queued FOCUSED event can arrive after the activity paused and its
        # widgets were deleted; focusing then raises LvReferenceError.
        if self._paused or breakout.is_game_over():
            return
        lv.group_focus_obj(self.defocus_button)
        breakout.move_paddle(-self.paddle_move_step)

    def move_right(self):
        if self._paused or breakout.is_game_over():
            return
        lv.group_focus_obj(self.defocus_button)
        breakout.move_paddle(self.paddle_move_step)

    def touch_cb(self, event):
        if breakout.is_game_over():
            return

        event_code = event.get_code()
        if event_code == lv.EVENT.PRESSED:
            x, y = InputManager.pointer_xy()
            self.touch_active = True
            self.touch_last_x = x
            return

        if event_code == lv.EVENT.PRESSING:
            if not self.touch_active:
                x, y = InputManager.pointer_xy()
                self.touch_active = True
                self.touch_last_x = x
                return
            x, y = InputManager.pointer_xy()
            if self.touch_last_x is not None:
                delta = x - self.touch_last_x
                if delta:
                    breakout.move_paddle(round(delta * 1.3))
            self.touch_last_x = x
            return

        if event_code == lv.EVENT.RELEASED:
            self.touch_active = False
            self.touch_last_x = None
            return

    # -- persistence ------------------------------------------------------

    def _stop_state_timer(self):
        if self._state_timer is not None:
            try:
                self._state_timer.delete()
            except Exception:
                pass
            self._state_timer = None

    def _update_state(self, _=None):
        try:
            self.score = breakout.get_score()
            self.level = breakout.get_level()
            self.lives = breakout.get_lives()
            game_over = breakout.is_game_over()
        except Exception:
            return

        if self.score > self.highscore:
            self.highscore = self.score

        # Only write to flash when the game moved on, not on every point: a
        # prefs commit takes milliseconds and stalls the frame after it.
        if self.lives > 0 and (
            self.level != self._autosaved_level or
            self.lives != self._autosaved_lives
        ):
            self._autosave()

        if game_over and not self._game_over_handled:
            self._save_highscore()
            self._delete_autosave()
            self._game_over_handled = True

        # Detect that the native module has restarted and reset our flag.
        if self._game_over_handled and self.lives == 5 and self.score == 0:
            self._game_over_handled = False

    def _save_state(self):
        try:
            self.score = breakout.get_score()
            self.level = breakout.get_level()
            self.lives = breakout.get_lives()
        except Exception:
            pass
        self._save_highscore()
        self._autosave()

    def _autosave(self):
        if self.lives <= 0:
            return
        self._autosaved_level = self.level
        self._autosaved_lives = self.lives
        editor = SharedPreferences(self.appFullName).edit()
        editor.put_int("autosave_level", self.level)
        editor.put_int("autosave_score", self.score)
        editor.put_int("autosave_lives", self.lives)
        editor.commit()

    def _save_highscore(self):
        best = max(self.score, self.highscore)
        if best > self.highscore:
            self.highscore = best
        if best > 0:
            editor = SharedPreferences(self.appFullName).edit()
            editor.put_int("highscore", self.highscore)
            editor.commit()

    def _delete_autosave(self):
        self._autosaved_level = 0
        self._autosaved_lives = 5
        editor = SharedPreferences(self.appFullName).edit()
        editor.put_int("autosave_level", 0)
        editor.put_int("autosave_score", 0)
        editor.put_int("autosave_lives", 0)
        editor.commit()

    def _check_autoload(self):
        prefs = SharedPreferences(self.appFullName)
        saved_level = prefs.get_int("autosave_level", 0)
        saved_score = prefs.get_int("autosave_score", 0)
        saved_lives = prefs.get_int("autosave_lives", 0)

        if saved_level <= 0 or saved_lives <= 0:
            self._delete_autosave()
            breakout.new_game(time.ticks_ms())
            self._autosaved_level = 1
            self._autosaved_lives = 5
            return

        self.level = saved_level
        self.score = saved_score
        self.lives = saved_lives
        self._autosaved_level = self.level
        self._autosaved_lives = self.lives
        breakout.set_highscore(self.highscore)
        breakout.set_level(self.level)
        breakout.set_score(self.score)
        breakout.set_lives(self.lives)
