from mpos import Activity, AppearanceManager, DisplayMetrics, SharedPreferences
import lvgl as lv
import random
import time


def _toggle(state, rows, cols, r, c):
    state[r][c] = not state[r][c]
    if r > 0:
        state[r - 1][c] = not state[r - 1][c]
    if r < rows - 1:
        state[r + 1][c] = not state[r + 1][c]
    if c > 0:
        state[r][c - 1] = not state[r][c - 1]
    if c < cols - 1:
        state[r][c + 1] = not state[r][c + 1]


def _generate_puzzle(rows, cols):
    state = [[False] * cols for _ in range(rows)]
    for _ in range(rows * cols * 2):
        r = random.randint(0, rows - 1)
        c = random.randint(0, cols - 1)
        _toggle(state, rows, cols, r, c)
    if not any(any(row) for row in state):
        r = random.randint(0, rows - 1)
        c = random.randint(0, cols - 1)
        _toggle(state, rows, cols, r, c)
    return state


class LightsOut(Activity):
    ON_COLOR = lv.color_hex(0xF1C40F)
    OFF_COLOR = lv.color_hex(0x2C3E50)

    def onCreate(self):
        self.screen = lv.obj()
        self._last_ts = 0
        self._win_timer = None
        self.level = 1
        self.total_levels = 0
        self.score = 0
        self.highscore = SharedPreferences(self.appFullName).get_int("highscore", 0)
        self.container = None
        self.buttons = []
        self.rows = 0
        self.cols = 0
        self.state = None
        self.moves = 0
        self.popup_modal = None
        self.new_game()
        self.create_ui()
        self.setContentView(self.screen)
        self._check_autoload()

    def _grid_dims(self):
        cols = (self.level + 1) // 2
        rows = self.level // 2 + 1
        return rows, cols

    def new_game(self):
        self.rows, self.cols = self._grid_dims()
        self.state = _generate_puzzle(self.rows, self.cols)
        self.moves = 0

    def create_ui(self):
        self.level_label = lv.label(self.screen)
        self.level_label.align(lv.ALIGN.TOP_MID, 0, 10)

        self.moves_label = lv.label(self.screen)
        self.moves_label.align(lv.ALIGN.TOP_RIGHT, -10, 10)

        self.levels_label = lv.label(self.screen)
        self.levels_label.align(lv.ALIGN.TOP_LEFT, 10, 10)

        self.score_label = lv.label(self.screen)
        self.score_label.align(lv.ALIGN.BOTTOM_LEFT, 10, -10)

        self.highscore_label = lv.label(self.screen)
        self.highscore_label.align(lv.ALIGN.BOTTOM_MID, 0, -10)
        self.highscore_label.add_flag(lv.obj.FLAG.CLICKABLE)
        self.highscore_label.add_event_cb(self.on_highscore_tap, lv.EVENT.CLICKED, None)
        self.refresh_labels()

        self.build_board()

        reset_btn = lv.button(self.screen)
        reset_label = lv.label(reset_btn)
        reset_label.set_text("New Game")
        reset_btn.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        reset_btn.add_event_cb(self.on_reset, lv.EVENT.CLICKED, None)

    def build_board(self):
        if self.container:
            self.container.delete()
        self.container = lv.obj(self.screen)
        self.container.set_size(lv.pct(100), DisplayMetrics.pct_of_height(75))
        self.container.align(lv.ALIGN.CENTER, 0, 0)
        self.container.set_flex_flow(lv.FLEX_FLOW.ROW_WRAP)
        self.container.set_style_pad_row(2, 0)
        self.container.set_style_pad_column(2, 0)
        self.container.set_style_radius(0, 0)

        self.buttons = []
        for r in range(self.rows):
            for c in range(self.cols):
                btn = lv.button(self.container)
                btn.set_size(lv.pct(95 // self.cols), lv.pct(95 // self.rows))
                self._color_button(btn, self.state[r][c])
                btn.add_event_cb(lambda e, rr=r, cc=c: self.on_button(e, rr, cc), lv.EVENT.CLICKED, None)
                self.buttons.append(btn)

    def _color_button(self, btn, is_on):
        if is_on:
            btn.set_style_bg_color(self.ON_COLOR, lv.PART.MAIN)
        else:
            btn.set_style_bg_color(self.OFF_COLOR, lv.PART.MAIN)

    def _update_all_buttons(self):
        idx = 0
        for r in range(self.rows):
            for c in range(self.cols):
                self._color_button(self.buttons[idx], self.state[r][c])
                idx += 1

    def refresh_labels(self):
        self.level_label.set_text(f"Level: {self.level}")
        self.moves_label.set_text(f"Moves: {self.moves}")
        self.levels_label.set_text(f"Solved: {self.total_levels}")
        self.score_label.set_text(f"Score: {self.score}")
        best = max(self.score, self.highscore)
        self.highscore_label.set_text(f"Best: {best}")
        if self.score > self.highscore and self.score > 0:
            self.highscore_label.set_style_text_color(lv.color_hex(0xE74C3C), lv.PART.MAIN)
        elif AppearanceManager.is_light_mode():
            self.highscore_label.set_style_text_color(lv.color_hex(0x000000), lv.PART.MAIN)
        else:
            self.highscore_label.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)

    def _save_highscore(self):
        best = max(self.score, self.highscore)
        if best > self.highscore:
            self.highscore = best
            editor = SharedPreferences(self.appFullName).edit()
            editor.put_int("highscore", self.highscore)
            editor.commit()

    def _autosave(self):
        editor = SharedPreferences(self.appFullName).edit()
        editor.put_int("autosave_level", self.level)
        editor.put_int("autosave_score", self.score)
        editor.put_int("autosave_levels", self.total_levels)
        editor.commit()

    def _delete_autosave(self):
        editor = SharedPreferences(self.appFullName).edit()
        editor.put_int("autosave_level", 0)
        editor.put_int("autosave_score", 0)
        editor.put_int("autosave_levels", 0)
        editor.commit()

    def _check_autoload(self):
        prefs = SharedPreferences(self.appFullName)
        saved_level = prefs.get_int("autosave_level", 0)
        saved_score = prefs.get_int("autosave_score", 0)
        saved_levels = prefs.get_int("autosave_levels", 0)
        if saved_level == 0 and saved_score == 0:
            return

        mbox = lv.msgbox()
        mbox.set_width(DisplayMetrics.pct_of_width(75))
        mbox.add_text(f"Load best game:\nlevel {saved_level}, score {saved_score}?")

        yes_btn = mbox.add_footer_button("Yes")
        yes_btn.add_event_cb(
            lambda e: self._do_load(e, saved_level, saved_score, saved_levels),
            lv.EVENT.CLICKED, None
        )
        no_btn = mbox.add_footer_button("No")
        no_btn.add_event_cb(self._on_autoload_no, lv.EVENT.CLICKED, None)

        self.popup_modal = mbox

    def _do_load(self, event, saved_level, saved_score, saved_levels):
        self._close_popup()
        self.level = saved_level
        self.score = saved_score
        self.total_levels = saved_levels
        self.new_game()
        self.build_board()
        self.refresh_labels()

    def _on_autoload_no(self, event):
        self._close_popup()

    def on_highscore_tap(self, event):
        self._show_confirm_popup("Reset highscore?", self._on_reset_highscore_yes, self._on_reset_highscore_no)

    def _show_confirm_popup(self, message, yes_cb, no_cb):
        self._close_popup()

        mbox = lv.msgbox()
        mbox.set_width(DisplayMetrics.pct_of_width(75))
        mbox.add_text(message)

        yes_btn = mbox.add_footer_button("Yes")
        yes_btn.add_event_cb(yes_cb, lv.EVENT.CLICKED, None)
        no_btn = mbox.add_footer_button("No")
        no_btn.add_event_cb(no_cb, lv.EVENT.CLICKED, None)

        self.popup_modal = mbox

    def _close_popup(self, event=None):
        if self.popup_modal:
            try:
                self.popup_modal.close()
            except Exception:
                pass
            self.popup_modal = None

    def _on_reset_highscore_yes(self, event):
        self.highscore = 0
        editor = SharedPreferences(self.appFullName).edit()
        editor.put_int("highscore", 0)
        editor.commit()
        self._delete_autosave()
        self._close_popup()
        self.refresh_labels()

    def _on_reset_highscore_no(self, event):
        self._close_popup()

    def on_button(self, event, r, c):
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_ts) < 50:
            return
        if r < 0 or r >= self.rows or c < 0 or c >= self.cols:
            return

        self._last_ts = now
        self.moves += 1

        _toggle(self.state, self.rows, self.cols, r, c)

        self._update_all_buttons()
        self.refresh_labels()

        if not any(any(row) for row in self.state):
            self.on_win()

    def on_win(self):
        wasted = self.moves - self.rows
        self.score += max(10, 100 - wasted * 20)
        self.total_levels += 1
        self.refresh_labels()
        self._win_timer = lv.timer_create(self._advance_level, 1000, None)
        self._win_timer.set_repeat_count(1)

    def _advance_level(self, timer):
        self._win_timer = None
        self.level += 1
        self._autosave()
        self._last_ts = time.ticks_ms()
        self.new_game()
        self.build_board()
        self.refresh_labels()

    def on_reset(self, event):
        self._show_confirm_popup("New game?", self._do_reset, self._close_popup)

    def _do_reset(self, event):
        self._close_popup()
        self._delete_autosave()
        if self._win_timer:
            lv.timer_del(self._win_timer)
            self._win_timer = None
        self._save_highscore()
        self._last_ts = time.ticks_ms()
        self.level = 1
        self.total_levels = 0
        self.score = 0
        self.new_game()
        self.build_board()
        self.refresh_labels()

    def onDestroy(self, screen):
        self._autosave()
        self._save_highscore()
        self._close_popup()
        if self._win_timer:
            lv.timer_del(self._win_timer)
            self._win_timer = None
        if self.container:
            self.container.delete()
            self.container = None
