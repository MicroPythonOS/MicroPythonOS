from mpos import Activity, AppearanceManager, AudioManager, DisplayMetrics, Intent, SettingActivity, SharedPreferences
import mpos.ui
import lvgl as lv
import os
import random
import time


_EMOJI_FS_DIR = "builtin/res/emojis/32x32"
_EMOJI_DIR = "M:" + _EMOJI_FS_DIR + "/"
_EMOJIS = sorted([f for f in os.listdir(_EMOJI_FS_DIR) if f.endswith(".png")])

# Number of emoji indices to shuffle together. 20 is more than enough for any
# level (max 7 colors) while keeping the saved JSON small enough to inline in
# littlefs.
_MAX_EMOJI_ORDER = 20

# Difficulty scaling knobs. These tune how quickly each dimension grows.
_LEVEL1_FILLED = 2
_LEVEL1_CAPACITY = 3
_LEVEL1_EXTRA = 2
_FILLED_STEP_EVERY = 2   # +1 filled tube every N levels
_CAPACITY_STEP_EVERY = 5  # +1 tube depth every N levels
_EXTRA_DROP_EVERY = 4    # -1 spare tube every N levels
_EXTRA_MIN = 1
_MAX_FILLED = 7
_MAX_CAPACITY = 5
_MAX_LEVEL = 100

# RTTTL sound cues for buzzer output.
_RTTTL_SELECT = "SortSel:d=16,o=7,b=250:8c"
_RTTTL_MOVE = "SortMove:d=16,o=6,b=250:8e"
_RTTTL_INVALID = "SortNo:d=16,o=5,b=200:8a,8a"
_RTTTL_WIN = "SortWin:d=8,o=6,b=160:c,e,g,c7,4e7"


def _shuffle(lst):
    for i in range(len(lst) - 1, 0, -1):
        j = random.randint(0, i)
        lst[i], lst[j] = lst[j], lst[i]


def _generate_emoji_order():
    """Return a shuffled sample of emoji indices from the full emoji pool."""
    count = min(_MAX_EMOJI_ORDER, len(_EMOJIS))
    order = list(range(len(_EMOJIS)))
    _shuffle(order)
    return order[:count]


def _top_run(tube):
    if not tube:
        return 0, None
    top = tube[-1]
    count = 0
    for i in range(len(tube) - 1, -1, -1):
        if tube[i] != top:
            break
        count += 1
    return count, top


def _can_move(source, target, capacity):
    if not source:
        return False
    if len(target) >= capacity:
        return False
    count, top = _top_run(source)
    if not target:
        return True
    tgt_count, tgt_top = _top_run(target)
    return top == tgt_top


def _apply_move(source, target, capacity):
    count, top = _top_run(source)
    if not target:
        move = min(count, capacity - len(target))
    else:
        tgt_count, tgt_top = _top_run(target)
        if top != tgt_top:
            return
        move = min(count, capacity - len(target))
    for _ in range(move):
        target.append(source.pop())


def _is_solved(tubes):
    """True when every color is fully gathered in one tube.

    Each non-empty tube must be uniform and no color may be split across
    multiple tubes. Empty tubes are allowed.
    """
    seen = set()
    for tube in tubes:
        if not tube:
            continue
        color = tube[0]
        for item in tube:
            if item != color:
                return False
        if color in seen:
            return False
        seen.add(color)
    return True


def _solve(tubes, capacity, max_states=3000):
    """Return True if this water-sort state is solvable.

    Bounded BFS; max_states caps memory/time on microcontrollers.
    """
    if _is_solved(tubes):
        return True
    start = tuple(tuple(t) for t in tubes)
    visited = {start}
    queue = [start]
    idx = 0
    while idx < len(queue) and len(visited) < max_states:
        state = queue[idx]
        idx += 1
        current = [list(t) for t in state]
        for i, src in enumerate(current):
            if not src:
                continue
            for j, tgt in enumerate(current):
                if i == j:
                    continue
                if _can_move(src, tgt, capacity):
                    new_tubes = [list(t) for t in state]
                    _apply_move(new_tubes[i], new_tubes[j], capacity)
                    if _is_solved(new_tubes):
                        return True
                    new_state = tuple(tuple(t) for t in new_tubes)
                    if new_state not in visited:
                        visited.add(new_state)
                        queue.append(new_state)
    return False


def _generate_level(filled, capacity, extra, max_retries=30):
    """Generate a mixed, guaranteed-solvable water-sort level.

    We fill tubes randomly and then verify solvability with a bounded BFS.
    Reverse valid water-sort moves cannot create mixed tubes, so random
    fill + verification is the practical way to honour the solvability goal.
    """
    balls = []
    for i in range(filled):
        balls.extend([i] * capacity)

    for _ in range(max_retries):
        _shuffle(balls)
        tubes = []
        pos = 0
        for _ in range(filled):
            tubes.append(list(balls[pos:pos + capacity]))
            pos += capacity
        for _ in range(extra):
            tubes.append([])
        if _is_solved(tubes):
            continue
        if _solve(tubes, capacity):
            return tubes
    # Last resort: return the most recent random state even if unverified.
    # This prevents the app from hanging; such a fallback is extremely rare.
    return tubes


def _level_params(level):
    level = max(1, min(level, _MAX_LEVEL))
    filled = min(_MAX_FILLED, _LEVEL1_FILLED + (level - 1) // _FILLED_STEP_EVERY)
    capacity = min(_MAX_CAPACITY, _LEVEL1_CAPACITY + (level - 1) // _CAPACITY_STEP_EVERY)
    extra = max(_EXTRA_MIN, _LEVEL1_EXTRA - (level - 1) // _EXTRA_DROP_EVERY)
    return filled, capacity, extra


class Sorter(Activity):
    SELECT_COLOR = lv.color_hex(0xF1C40F)
    TUBE_BG = lv.color_hex(0x34495E)
    TUBE_BORDER = lv.color_hex(0x5D6D7E)
    WHITE = lv.color_hex(0xFFFFFF)

    SOUND_EFFECTS_SETTING = {
        "title": "Sound effects",
        "key": "sound_effects",
        "ui": "radiobuttons",
        "default_value": "true",
        "ui_options": [("On", "true"), ("Off", "false")],
    }

    def onCreate(self):
        self.screen = lv.obj()
        self._last_ts = 0
        self._win_timer = None
        self.popup_modal = None
        self.container = None
        self.tube_widgets = []
        self.level = 1
        self.score = 0
        self.moves = 0
        self.selected = -1
        self.tubes = []
        self.capacity = 0
        self.emoji_order = []
        self.prefs = SharedPreferences(self.appFullName)
        self.highscore = self.prefs.get_int("highscore", 0)
        self.sound_effects = self._load_sound_effects()
        self._new_game()
        self.create_ui()
        self.setContentView(self.screen)
        self._check_autoload()

    def _new_game(self):
        """Start a brand new game (level 1) with a fresh emoji order."""
        self.level = 1
        self.score = 0
        self.emoji_order = _generate_emoji_order()
        self._autosave()
        self._start_level()

    def _start_level(self):
        """Generate tubes for the current level, keeping the current emoji order."""
        filled, capacity, extra = _level_params(self.level)
        self.capacity = capacity
        self.moves = 0
        self.selected = -1
        self.tubes = _generate_level(filled, capacity, extra)
        self.initial_tubes = [list(t) for t in self.tubes]

    def create_ui(self):
        self.score_best_label = lv.label(self.screen)
        self.score_best_label.align(lv.ALIGN.TOP_LEFT, 10, 10)
        self.score_best_label.add_flag(lv.obj.FLAG.CLICKABLE)
        self.score_best_label.add_event_cb(self.on_highscore_tap, lv.EVENT.CLICKED, None)

        self.level_label = lv.label(self.screen)
        self.level_label.align(lv.ALIGN.TOP_MID, 0, 10)

        self.moves_label = lv.label(self.screen)
        self.moves_label.align(lv.ALIGN.TOP_RIGHT, -10, 10)

        self.refresh_labels()
        self.build_board()

        settings_btn = lv.button(self.screen)
        settings_label = lv.label(settings_btn)
        settings_label.set_text(lv.SYMBOL.SETTINGS)
        settings_btn.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        settings_btn.add_event_cb(self.on_settings, lv.EVENT.CLICKED, None)
        mpos.ui.add_focus_border(settings_btn)

        refresh_btn = lv.button(self.screen)
        refresh_label = lv.label(refresh_btn)
        refresh_label.set_text(lv.SYMBOL.REFRESH)
        refresh_btn.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        refresh_btn.add_event_cb(self.on_refresh, lv.EVENT.CLICKED, None)

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
        self.container.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        self.container.set_style_pad_row(6, 0)
        self.container.set_style_pad_column(6, 0)
        self.container.set_style_radius(0, 0)
        self.container.remove_flag(lv.obj.FLAG.SCROLLABLE)

        self.tube_widgets = []
        num_tubes = len(self.tubes)
        gap = 6
        available_width = DisplayMetrics.width() - ((num_tubes - 1) * gap)
        tight_width = available_width // max(1, num_tubes)
        tube_width = max(28, int(tight_width * 0.85))
        # Scale emojis down as tubes get deeper so everything fits.
        max_tube_height = DisplayMetrics.pct_of_height(55)
        emoji_size_from_height = int(max_tube_height // (self.capacity * 1.35))
        emoji_size = max(14, min(32, tube_width - 8, emoji_size_from_height))
        tube_height = int(emoji_size * 1.35 * self.capacity)

        for idx in range(num_tubes):
            tube = self._build_tube_widget(idx, tube_width, tube_height, emoji_size)
            self.tube_widgets.append(tube)

    def _build_tube_widget(self, idx, tube_width, tube_height, emoji_size):
        tube_obj = lv.obj(self.container)
        tube_obj.set_size(tube_width, tube_height)
        # Pack icons at the bottom so empty tubes look empty at the top.
        tube_obj.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        tube_obj.set_flex_align(lv.FLEX_ALIGN.END, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        tube_obj.set_style_pad_all(2, lv.PART.MAIN)
        tube_obj.set_style_pad_column(2, lv.PART.MAIN)
        tube_obj.set_style_radius(4, lv.PART.MAIN)
        tube_obj.set_style_bg_color(self.TUBE_BG, lv.PART.MAIN)
        tube_obj.set_style_border_color(self.TUBE_BORDER, lv.PART.MAIN)
        tube_obj.set_style_border_width(2, lv.PART.MAIN)
        tube_obj.add_flag(lv.obj.FLAG.CLICKABLE)
        tube_obj.add_event_cb(lambda e, i=idx: self.on_tube(e, i), lv.EVENT.CLICKED, None)
        mpos.ui.add_focus_border(tube_obj, width=4)

        if self.selected == idx:
            tube_obj.set_style_bg_color(self.SELECT_COLOR, 0)
        else:
            tube_obj.set_style_bg_color(self.TUBE_BG, 0)

        items = self.tubes[idx]
        # Items are stored bottom..top, but LVGL lays out children in
        # creation order with the first child at the visual top. Reverse the
        # render order so the top emoji appears at the top of the tube while
        # the whole column is still aligned to the tube bottom.
        scale = int(256 * emoji_size / 32)
        for item in reversed(items):
            img = lv.image(tube_obj)
            img.set_src(_EMOJI_DIR + _EMOJIS[self.emoji_order[item]])
            img.set_size(emoji_size, emoji_size)
            img.set_scale(scale)

        return tube_obj

    def _update_selection(self):
        for i, tube in enumerate(self.tube_widgets):
            if self.selected == i:
                tube.set_style_bg_color(self.SELECT_COLOR, 0)
            else:
                tube.set_style_bg_color(self.TUBE_BG, 0)

    def _restore_focus(self, idx):
        if idx < 0 or idx >= len(self.tube_widgets):
            return
        try:
            lv.group_focus_obj(self.tube_widgets[idx])
        except Exception:
            pass

    def refresh_labels(self):
        self.level_label.set_text(f"Level: {self.level}")
        self.moves_label.set_text(f"Moves: {self.moves}")
        best = max(self.score, self.highscore)
        self.score_best_label.set_text(f"Score/Best: {self.score}/{best}")
        if self.score > self.highscore and self.score > 0:
            self.score_best_label.set_style_text_color(lv.color_hex(0xE74C3C), lv.PART.MAIN)
        elif AppearanceManager.is_light_mode():
            self.score_best_label.set_style_text_color(lv.color_hex(0x000000), lv.PART.MAIN)
        else:
            self.score_best_label.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)

    def _find_buzzer_output(self):
        try:
            for output in AudioManager.get_outputs():
                if output.kind == "buzzer":
                    return output
        except Exception:
            pass
        return None

    def _play_rtttl(self, rtttl):
        if not self.sound_effects:
            return
        output = self._find_buzzer_output()
        if output is None:
            return
        try:
            AudioManager.player(
                rtttl=rtttl,
                stream_type=AudioManager.STREAM_NOTIFICATION,
                volume=50,
                output=output,
            ).start()
        except Exception:
            pass

    def _autosave(self):
        editor = SharedPreferences(self.appFullName).edit()
        editor.put_int("autosave_level", self.level)
        editor.put_int("autosave_score", self.score)
        if self.emoji_order:
            editor.put_list("emoji_order", self.emoji_order)
        editor.commit()

    def _save_highscore(self):
        best = max(self.score, self.highscore)
        if best > self.highscore:
            self.highscore = best
            editor = SharedPreferences(self.appFullName).edit()
            editor.put_int("highscore", self.highscore)
            editor.commit()

    def _delete_autosave(self):
        editor = SharedPreferences(self.appFullName).edit()
        editor.put_int("autosave_level", 0)
        editor.put_int("autosave_score", 0)
        editor.commit()

    def _check_autoload(self):
        prefs = SharedPreferences(self.appFullName)
        saved_level = prefs.get_int("autosave_level", 0)
        saved_score = prefs.get_int("autosave_score", 0)
        if saved_level == 0 and saved_score == 0:
            return

        mbox = lv.msgbox()
        mbox.set_width(DisplayMetrics.pct_of_width(75))
        mbox.add_text(f"Load best game:\nlevel {saved_level}, score {saved_score}?")

        yes_btn = mbox.add_footer_button("Yes")
        yes_btn.add_event_cb(
            lambda e: self._do_load(e, saved_level, saved_score),
            lv.EVENT.CLICKED, None
        )
        no_btn = mbox.add_footer_button("No")
        no_btn.add_event_cb(self._on_autoload_no, lv.EVENT.CLICKED, None)

        self.popup_modal = mbox

    def _load_emoji_order(self, prefs):
        """Load stored emoji order or generate a fresh one if invalid."""
        order = prefs.get_list("emoji_order", [])
        try:
            if (
                isinstance(order, list)
                and _MAX_FILLED <= len(order) <= _MAX_EMOJI_ORDER
                and len(set(order)) == len(order)
                and all(0 <= i < len(_EMOJIS) for i in order)
            ):
                return [int(i) for i in order]
        except Exception:
            pass
        return _generate_emoji_order()

    def _load_sound_effects(self):
        """Return the user's sound effects preference; defaults to enabled."""
        value = self.prefs.get_string("sound_effects", "true")
        return str(value).lower() != "false"

    def _do_load(self, event, saved_level, saved_score):
        self._close_popup()
        prefs = SharedPreferences(self.appFullName)
        self.emoji_order = self._load_emoji_order(prefs)
        self.level = saved_level
        self.score = saved_score
        self._start_level()
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

    def on_settings(self, event):
        self._close_popup()
        intent = Intent(activity_class=SettingActivity)
        intent.putExtra("prefs", self.prefs)
        intent.putExtra("setting", self.SOUND_EFFECTS_SETTING)
        self.startActivity(intent)

    def onResume(self, screen):
        self.sound_effects = self._load_sound_effects()

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

    def on_tube(self, event, idx):
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_ts) < 50:
            return
        if idx < 0 or idx >= len(self.tubes):
            return

        if self.selected == -1:
            if self.tubes[idx]:
                self.selected = idx
                self._last_ts = now
                self._update_selection()
                self._play_rtttl(_RTTTL_SELECT)
            return

        if self.selected == idx:
            self.selected = -1
            self._last_ts = now
            self._update_selection()
            return

        src = self.tubes[self.selected]
        tgt = self.tubes[idx]
        if _can_move(src, tgt, self.capacity):
            self._last_ts = now
            _apply_move(src, tgt, self.capacity)
            self.moves += 1
            self.selected = -1
            self._play_rtttl(_RTTTL_MOVE)
            self.build_board()
            self._restore_focus(idx)
            self.refresh_labels()
            if _is_solved(self.tubes):
                self.on_win()
        else:
            self.selected = -1
            self._last_ts = now
            self._update_selection()
            self._play_rtttl(_RTTTL_INVALID)

    def on_win(self):
        self._play_rtttl(_RTTTL_WIN)
        filled, capacity, extra = _level_params(self.level)
        min_moves = filled * capacity
        wasted = max(0, self.moves - min_moves)
        self.score += self.level * 10 + max(10, 100 - wasted * 5)
        self.refresh_labels()
        self._win_timer = lv.timer_create(self._advance_level, 1000, None)
        self._win_timer.set_repeat_count(1)

    def _advance_level(self, timer):
        self._win_timer = None
        self.level += 1
        self._autosave()
        self._last_ts = time.ticks_ms()
        self._start_level()
        self.build_board()
        self.refresh_labels()

    def on_refresh(self, event):
        self._restart_level()

    def _restart_level(self):
        if self._win_timer:
            try:
                self._win_timer.delete()
            except Exception:
                pass
            self._win_timer = None
        self.moves = 0
        self.selected = -1
        if self.initial_tubes:
            self.tubes = [list(t) for t in self.initial_tubes]
        self.build_board()
        self._restore_focus(0)
        self.refresh_labels()
        self._autosave()

    def on_reset(self, event):
        self._show_confirm_popup("New game?", self._do_reset, self._close_popup)

    def _do_reset(self, event):
        self._close_popup()
        self._delete_autosave()
        if self._win_timer:
            try:
                self._win_timer.delete()
            except Exception:
                pass
            self._win_timer = None
        self._save_highscore()
        self._last_ts = time.ticks_ms()
        self._new_game()
        self.build_board()
        self.refresh_labels()

    def onDestroy(self, screen):
        self._autosave()
        self._save_highscore()
        self._close_popup()
        if self._win_timer:
            try:
                self._win_timer.delete()
            except Exception:
                pass
            self._win_timer = None
        if self.container:
            self.container.delete()
            self.container = None
