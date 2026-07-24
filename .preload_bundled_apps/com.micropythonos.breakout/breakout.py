# Breakout app UI/driver glue. This app renders into a framebuffer that may be
# smaller than the full display (partial framebuffer). The draw loop is more
# complex because it slices the screen into chunks, renders each slice in C,
# and flushes them sequentially using a flush-ready IRQ callback. A scheduled
# (non-IRQ) handler advances chunks so it can work on larger-than-320x230
# displays without requiring a full-size framebuffer.
import lvgl as lv
import mpos.ui
from mpos import Activity, InputManager, SharedPreferences

import sys
if sys.platform == "esp32":
    import breakout_xtensawin as breakout
else:
    import breakout_x64 as breakout


class Breakout(Activity):

    hor_res = 0
    ver_res = 0
    paddle_move_step = None
    layer = None
    buffer = None
    touch_active = False
    touch_last_x = None
    last_fps = 0
    average_fps = 0

    old_callback = None

    render_next = True
    flush_ready = False
    chunk_in_progress = False
    chunk_waiting = False
    chunk_rows_per = 0
    chunk_total = 0
    chunk_index = 0

    # Widgets:
    screen = None
    leftbutton = None
    rightbutton = None

    # State mirrors of native state (not displayed without fonts).
    score = 0
    level = 1
    lives = 5
    highscore = 0
    _initialized = False
    _paused = False
    _game_over_handled = False
    _state_timer = None
    _autosaved_level = 0
    _autosaved_score = 0
    _autosaved_lives = 5

    def onCreate(self):
        self.screen = lv.obj()
        self.screen.add_flag(lv.obj.FLAG.CLICKABLE)
        self.screen.add_event_cb(self.touch_cb, lv.EVENT.ALL, None)

        d = lv.display_get_default()
        self.hor_res = d.get_horizontal_resolution()
        self.paddle_move_step = round(self.hor_res / 10)
        self.ver_res = d.get_vertical_resolution()

        self.leftbutton = lv.button(self.screen)
        self.leftbutton.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        self.leftbutton.set_size(1,1)
        self.leftbutton.set_style_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        self.leftbutton.add_event_cb(lambda e: self.move_left(), lv.EVENT.FOCUSED, None)

        # Invisible button, just for defocusing the left and right buttons:
        self.defocus_button = lv.button(self.screen)
        self.defocus_button.align(lv.ALIGN.BOTTOM_MID,0,0)
        self.defocus_button.set_size(1,1)
        self.defocus_button.set_style_opa(lv.OPA.TRANSP, lv.PART.MAIN)

        self.rightbutton = lv.button(self.screen)
        self.rightbutton.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        self.rightbutton.set_size(1,1)
        self.rightbutton.set_style_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        self.rightbutton.add_event_cb(lambda e: self.move_right(), lv.EVENT.FOCUSED, None)

        self.setContentView(self.screen)

    def onResume(self, screen):
        self._paused = False
        if not self._initialized:
            self._initialized = True
            breakout.init(mpos.ui.main_display._frame_buffer1, self.hor_res, self.ver_res)
            mpos.ui.task_handler.add_event_cb(self.drawframe, mpos.ui.task_handler.TASK_HANDLER_FINISHED)

        mpos.ui.main_display._data_bus.register_callback(self.flush_ready_cb)

        prefs = SharedPreferences(self.appFullName)
        self.highscore = prefs.get_int("highscore", 0)
        breakout.set_highscore(self.highscore)

        self._check_autoload()

        if self._state_timer is None:
            self._state_timer = lv.timer_create(self._update_state, 2000, None)

    def onPause(self, screen):
        self._paused = True
        self._save_state()
        self._stop_state_timer()
        # If a chunk is mid-flight, release the display driver so the next
        # activity can flush normally.
        if self.chunk_waiting:
            self.chunk_waiting = False
            self.chunk_in_progress = False
            self.render_next = True
            self.flush_ready = False
            try:
                mpos.ui.main_display._disp_drv.flush_ready()
            except Exception:
                pass
        mpos.ui.main_display._data_bus.register_callback(mpos.ui.main_display._flush_ready_cb)

    def onDestroy(self, screen):
        self._paused = True
        self._save_state()
        self._stop_state_timer()

    def _stop_state_timer(self):
        if self._state_timer is not None:
            try:
                self._state_timer.delete()
            except Exception:
                pass
            self._state_timer = None

    def _save_state(self):
        self._save_highscore()
        self._autosave()

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

        # Save progress when the level changes; skip when dead to avoid
        # reloading a game that is already over.
        if self.lives > 0 and (
            self.level != self._autosaved_level or
            self.score != self._autosaved_score or
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

    def move_left(self):
        if not breakout.is_game_over():
            lv.group_focus_obj(self.defocus_button)
            breakout.move_paddle(-self.paddle_move_step)

    def move_right(self):
        if not breakout.is_game_over():
            lv.group_focus_obj(self.defocus_button)
            breakout.move_paddle(self.paddle_move_step)

    def flush_ready_cb(self, arg1=None, arg2=None):
        # This is called in IRQ (interrupt) context so it can't allocate memory
        # So no printf, no calling drawframe() directly, just setting variables or scheduling a function.
        mpos.ui.main_display._disp_drv.flush_ready()
        self.flush_ready = True

    def drawframe(self, arg1=None, arg2=None):
        if self._paused:
            return

        if self.chunk_waiting:
            if self.flush_ready:
                self.flush_ready = False
                self.chunk_waiting = False
                self.chunk_index += 1
                if self.chunk_index >= self.chunk_total:
                    self.chunk_in_progress = False
                    self.render_next = True
                else:
                    self._render_and_send_chunk()
            return

        if self.chunk_in_progress or not self.render_next:
            return

        self.render_next = False

        buffer_len = len(mpos.ui.main_display._frame_buffer1)
        bytes_per_row = self.hor_res * 2
        if bytes_per_row <= 0:
            self.render_next = True
            return

        rows_per_chunk = buffer_len // bytes_per_row
        if rows_per_chunk <= 0:
            self.render_next = True
            return

        if rows_per_chunk >= self.ver_res:
            self.chunk_rows_per = self.ver_res
            self.chunk_index = 0
            self.chunk_total = 1
        else:
            self.chunk_rows_per = rows_per_chunk
            self.chunk_index = 0
            self.chunk_total = (self.ver_res + rows_per_chunk - 1) // rows_per_chunk

        self.chunk_in_progress = True
        self.chunk_waiting = False
        self.flush_ready = False
        self._render_and_send_chunk()

    def _render_and_send_chunk(self):
        if not self.chunk_in_progress:
            return
        if self.chunk_waiting:
            return
        if self.chunk_index >= self.chunk_total:
            self.chunk_in_progress = False
            self.render_next = True
            return

        y_offset = self.chunk_index * self.chunk_rows_per
        rows = min(self.chunk_rows_per, self.ver_res - y_offset)

        self.chunk_waiting = True
        breakout.render(y_offset, rows)
        self.send_to_display(y_offset, rows)

    def send_to_display(self, y_offset=0, rows=None):
        x1 = 0
        x2 = mpos.ui.main_display.get_horizontal_resolution() - 1
        x2 = x2 + mpos.ui.main_display._offset_x
        x1 = x1 + mpos.ui.main_display._offset_x

        if rows is None:
            rows = mpos.ui.main_display.get_vertical_resolution()
        y1 = y_offset
        y2 = y_offset + rows - 1
        y1 = y1 + mpos.ui.main_display._offset_y
        y2 = y2 + mpos.ui.main_display._offset_y

        cmd = mpos.ui.main_display._set_memory_location(x1, y1, x2, y2)
        bytes_needed = rows * mpos.ui.main_display.get_horizontal_resolution() * 2
        data_view = memoryview(mpos.ui.main_display._frame_buffer1)[:bytes_needed]

        tx_last = True
        mpos.ui.main_display._data_bus.tx_color(
            cmd,
            data_view,
            x1, y1, x2, y2,
            mpos.ui.main_display._rotation,
            tx_last,
        )

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

    def _autosave(self):
        if self.lives <= 0:
            return
        self._autosaved_level = self.level
        self._autosaved_score = self.score
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
        self._autosaved_score = 0
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
            # Start a fresh game and clear any stale dead save.
            self._delete_autosave()
            breakout.new_game()
            self._autosaved_level = 1
            self._autosaved_score = 0
            self._autosaved_lives = 5
            return

        self.level = saved_level
        self.score = saved_score
        self.lives = saved_lives
        self._autosaved_level = self.level
        self._autosaved_score = self.score
        self._autosaved_lives = self.lives
        breakout.set_highscore(self.highscore)
        breakout.set_level(self.level)
        breakout.set_score(self.score)
        breakout.set_lives(self.lives)

    def log_callback(self, level, log_str):
        pass
