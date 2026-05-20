from mpos import Activity, AppearanceManager, DisplayMetrics, SharedPreferences
import lvgl as lv
import random
import time


def _shuffle(lst):
    for i in range(len(lst) - 1, 0, -1):
        j = random.randint(0, i)
        lst[i], lst[j] = lst[j], lst[i]


def _grid_dims(n):
    best = (1, n)
    for r in range(1, int(n**0.5) + 1):
        if n % r == 0:
            c = n // r
            if abs(r - c) < abs(best[0] - best[1]):
                best = (r, c)
    return best


class Memory(Activity):
    LIGHT_BLUE = lv.color_hex(0x5DADE2)
    ORANGE = lv.color_hex(0xF39C12)
    GREEN = lv.color_hex(0x27AE60)
    RED = lv.color_hex(0xE74C3C)

    SYMBOLS = [
        chr(61441), chr(61448), chr(61451), chr(61452), chr(61452), chr(61453),
        chr(61457), chr(61459), chr(61461), chr(61465), chr(61468), chr(61473),
        chr(61478), chr(61479), chr(61480), chr(61502), chr(61507), chr(61512),
        chr(61515), chr(61516), chr(61517), chr(61521), chr(61522), chr(61523),
        chr(61524), chr(61543), chr(61544), chr(61550), chr(61552), chr(61553),
        chr(61556), chr(61559), chr(61560), chr(61561), chr(61563), chr(61587),
        chr(61589), chr(61636), chr(61637), chr(61639), chr(61641), chr(61664),
        chr(61671), chr(61674), chr(61683), chr(61724), chr(61732), chr(61787),
        chr(61931), chr(62016), chr(62017), chr(62018), chr(62019), chr(62020),
        chr(62087), chr(62099), chr(62212), chr(62189), chr(62810), chr(63426),
        chr(63650),
        chr(0xf002), chr(0xf004), chr(0xf005), chr(0xf00e), chr(0xf010),
        chr(0xf029), chr(0xf030),
        chr(0xf15a), chr(0xf164), chr(0xf165), chr(0xf1e0),
        chr(0xf2ea), chr(0xf379), chr(0xf58f),
        chr(0x2022), chr(0x20bf), chr(0x4e2f), chr(0x4e30),
    ]

    def onCreate(self):
        self.screen = lv.obj()
        self._last_ts = 0
        self._win_timer = None
        self.level = 1
        self.total_points = 0
        self.score = 0
        self.highscore = SharedPreferences(self.appFullName).get_int("highscore", 0)
        self.container = None
        self.buttons = []
        self.labels = []
        self.popup_modal = None
        self.new_game()
        self.create_ui()
        self.setContentView(self.screen)
        self._check_autoload()

    def new_game(self):
        num_cells = self.level * 2
        self.ROWS, self.COLS = _grid_dims(num_cells)
        num_pairs = num_cells // 2
        pool = self.SYMBOLS[:]
        _shuffle(pool)
        symbols = pool[:num_pairs] * 2
        _shuffle(symbols)
        self.hidden = symbols[:num_cells]
        self.revealed = [False] * num_cells
        self.shown = [" "] * num_cells
        self.first_idx = -1
        self.second_idx = -1
        self.moves = 0

    def create_ui(self):
        self.level_label = lv.label(self.screen)
        self.level_label.align(lv.ALIGN.TOP_MID, 0, 10)

        self.moves_label = lv.label(self.screen)
        self.moves_label.align(lv.ALIGN.TOP_RIGHT, -10, 10)

        self.points_label = lv.label(self.screen)
        self.points_label.align(lv.ALIGN.TOP_LEFT, 10, 10)

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
        self.labels = []
        for idx in range(len(self.hidden)):
            btn = lv.button(self.container)
            btn.set_size(lv.pct(95 // self.COLS), lv.pct(95 // self.ROWS))
            label = lv.label(btn)
            if self.revealed[idx]:
                label.set_text(self.hidden[idx] + "!")
            elif self.shown[idx] != " ":
                label.set_text(self.shown[idx])
            else:
                label.set_text("")
            label.center()
            btn.add_event_cb(lambda e, i=idx: self.on_button(e, i), lv.EVENT.CLICKED, None)
            self._color_button(btn, idx)
            self.buttons.append(btn)
            self.labels.append(label)

    def _color_button(self, btn, idx):
        if self.revealed[idx]:
            color = self.GREEN
        elif self.shown[idx] != " " and self.first_idx != -1 and self.second_idx != -1:
            color = self.RED
        elif self.shown[idx] != " ":
            color = self.ORANGE
        else:
            color = self.LIGHT_BLUE
        btn.set_style_bg_color(color, lv.PART.MAIN)

    def _update_all_buttons(self):
        for idx, btn in enumerate(self.buttons):
            label = self.labels[idx]
            if self.revealed[idx]:
                label.set_text(self.hidden[idx] + "!")
            elif self.shown[idx] != " ":
                label.set_text(self.shown[idx])
            else:
                label.set_text("")
            self._color_button(btn, idx)

    def refresh_labels(self):
        self.level_label.set_text(f"Level: {self.level}")
        self.moves_label.set_text(f"Moves: {self.moves}")
        self.points_label.set_text(f"Points: {self.total_points}")
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
        editor.put_int("autosave_points", self.total_points)
        editor.commit()

    def _delete_autosave(self):
        editor = SharedPreferences(self.appFullName).edit()
        editor.put_int("autosave_level", 0)
        editor.put_int("autosave_score", 0)
        editor.put_int("autosave_points", 0)
        editor.commit()

    def _check_autoload(self):
        prefs = SharedPreferences(self.appFullName)
        saved_level = prefs.get_int("autosave_level", 0)
        saved_score = prefs.get_int("autosave_score", 0)
        saved_points = prefs.get_int("autosave_points", 0)
        if saved_level == 0 and saved_score == 0:
            return

        self.popup_modal = lv.obj(lv.layer_top())
        self.popup_modal.set_size(DisplayMetrics.width(), DisplayMetrics.height())
        self.popup_modal.set_style_bg_color(lv.color_hex(0x000000), lv.PART.MAIN)
        self.popup_modal.set_style_bg_opa(150, lv.PART.MAIN)
        self.popup_modal.set_style_border_width(0, lv.PART.MAIN)
        self.popup_modal.set_pos(0, 0)

        popup = lv.obj(self.popup_modal)
        popup.set_size(220, 140)
        popup.set_style_bg_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        popup.set_style_border_color(lv.color_hex(0x000000), lv.PART.MAIN)
        popup.set_style_border_width(3, lv.PART.MAIN)
        popup.set_style_radius(10, lv.PART.MAIN)
        popup.center()

        question = lv.label(popup)
        question.set_text(f"Load best game:\nlevel {saved_level}, score {saved_score}?")
        question.set_style_text_color(lv.color_hex(0x000000), lv.PART.MAIN)
        question.align(lv.ALIGN.TOP_MID, 0, 10)

        yes_btn = lv.button(popup)
        yes_btn.set_size(75, 35)
        yes_btn.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        yes_btn.add_event_cb(lambda e: self._do_load(e, saved_level, saved_score, saved_points), lv.EVENT.CLICKED, None)
        yes_label = lv.label(yes_btn)
        yes_label.set_text("Yes")
        yes_label.center()

        no_btn = lv.button(popup)
        no_btn.set_size(75, 35)
        no_btn.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        no_btn.add_event_cb(self._on_autoload_no, lv.EVENT.CLICKED, None)
        no_label = lv.label(no_btn)
        no_label.set_text("No")
        no_label.center()

    def _do_load(self, event, saved_level, saved_score, saved_points):
        self._close_popup()
        self.level = saved_level
        self.score = saved_score
        self.total_points = saved_points
        self.new_game()
        self.build_board()
        self.refresh_labels()

    def _on_autoload_no(self, event):
        self._close_popup()

    def on_highscore_tap(self, event):
        self.popup_modal = lv.obj(lv.layer_top())
        self.popup_modal.set_size(DisplayMetrics.width(), DisplayMetrics.height())
        self.popup_modal.set_style_bg_color(lv.color_hex(0x000000), lv.PART.MAIN)
        self.popup_modal.set_style_bg_opa(150, lv.PART.MAIN)
        self.popup_modal.set_style_border_width(0, lv.PART.MAIN)
        self.popup_modal.set_pos(0, 0)

        popup = lv.obj(self.popup_modal)
        popup.set_size(200, 120)
        popup.set_style_bg_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        popup.set_style_border_color(lv.color_hex(0x000000), lv.PART.MAIN)
        popup.set_style_border_width(3, lv.PART.MAIN)
        popup.set_style_radius(10, lv.PART.MAIN)
        popup.center()

        question = lv.label(popup)
        question.set_text("Reset highscore?")
        question.set_style_text_color(lv.color_hex(0x000000), lv.PART.MAIN)
        question.align(lv.ALIGN.TOP_MID, 0, 15)

        yes_btn = lv.button(popup)
        yes_btn.set_size(75, 35)
        yes_btn.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        yes_btn.add_event_cb(self._on_reset_highscore_yes, lv.EVENT.CLICKED, None)
        yes_label = lv.label(yes_btn)
        yes_label.set_text("Yes")
        yes_label.center()

        no_btn = lv.button(popup)
        no_btn.set_size(75, 35)
        no_btn.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        no_btn.add_event_cb(self._on_reset_highscore_no, lv.EVENT.CLICKED, None)
        no_label = lv.label(no_btn)
        no_label.set_text("No")
        no_label.center()

    def _close_popup(self, event=None):
        if self.popup_modal:
            self.popup_modal.delete()
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

    def on_button(self, event, idx):
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_ts) < 50:
            return
        if idx < 0 or idx >= len(self.hidden):
            return
        if self.revealed[idx] or self.shown[idx] != " ":
            return

        if self.first_idx != -1 and self.second_idx != -1:
            self.shown[self.first_idx] = " "
            self.shown[self.second_idx] = " "
            self.first_idx = -1
            self.second_idx = -1

        if self.first_idx == -1:
            self._last_ts = now
            self.first_idx = idx
            self.shown[idx] = self.hidden[idx]
        elif self.second_idx == -1 and idx != self.first_idx:
            self._last_ts = now
            self.second_idx = idx
            self.shown[idx] = self.hidden[idx]
            self.moves += 1
            if self.hidden[self.first_idx] == self.hidden[self.second_idx]:
                self.total_points += 1
                pairs_before = sum(self.revealed) // 2
                wasted = self.moves - (pairs_before + 1)
                self.score += max(10, 100 - wasted * 20)
                self.revealed[self.first_idx] = True
                self.revealed[self.second_idx] = True
                self.shown[self.first_idx] = " "
                self.shown[self.second_idx] = " "
                self.first_idx = -1
                self.second_idx = -1
                if all(self.revealed):
                    self.on_win()
            self.refresh_labels()

        self._update_all_buttons()

    def on_win(self):
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
        self._close_popup()
        self.popup_modal = lv.obj(lv.layer_top())
        self.popup_modal.set_size(DisplayMetrics.width(), DisplayMetrics.height())
        self.popup_modal.set_style_bg_color(lv.color_hex(0x000000), lv.PART.MAIN)
        self.popup_modal.set_style_bg_opa(150, lv.PART.MAIN)
        self.popup_modal.set_style_border_width(0, lv.PART.MAIN)
        self.popup_modal.set_pos(0, 0)

        popup = lv.obj(self.popup_modal)
        popup.set_size(200, 120)
        popup.set_style_bg_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        popup.set_style_border_color(lv.color_hex(0x000000), lv.PART.MAIN)
        popup.set_style_border_width(3, lv.PART.MAIN)
        popup.set_style_radius(10, lv.PART.MAIN)
        popup.center()

        question = lv.label(popup)
        question.set_text("New game?")
        question.set_style_text_color(lv.color_hex(0x000000), lv.PART.MAIN)
        question.align(lv.ALIGN.TOP_MID, 0, 15)

        yes_btn = lv.button(popup)
        yes_btn.set_size(75, 35)
        yes_btn.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        yes_btn.add_event_cb(self._do_reset, lv.EVENT.CLICKED, None)
        yes_label = lv.label(yes_btn)
        yes_label.set_text("Yes")
        yes_label.center()

        no_btn = lv.button(popup)
        no_btn.set_size(75, 35)
        no_btn.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        no_btn.add_event_cb(self._close_popup, lv.EVENT.CLICKED, None)
        no_label = lv.label(no_btn)
        no_label.set_text("No")
        no_label.center()

    def _do_reset(self, event):
        self._close_popup()
        self._delete_autosave()
        if self._win_timer:
            lv.timer_del(self._win_timer)
            self._win_timer = None
        self._save_highscore()
        self._last_ts = time.ticks_ms()
        self.level = 1
        self.total_points = 0
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
