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


def _solve_path(tubes, capacity, max_states=5000):
    """Return list of (src, tgt) moves that solve this state or []."""
    if _is_solved(tubes):
        return []
    start = tuple(tuple(t) for t in tubes)
    parent = {start: (None, None, None)}
    queue = [start]
    idx = 0
    while idx < len(queue) and len(parent) < max_states:
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
                    new_state = tuple(tuple(t) for t in new_tubes)
                    if new_state not in parent:
                        parent[new_state] = (state, i, j)
                        if _is_solved(new_tubes):
                            path = [(i, j)]
                            cur = state
                            while parent[cur][0] is not None:
                                _, s, t = parent[cur]
                                path.append((s, t))
                                cur = parent[cur][0]
                            path.reverse()
                            return path
                        queue.append(new_state)
    return []


def _generate_level(filled, capacity, extra, max_retries=30):
    """Generate a mixed, guaranteed-solvable water-sort level.

    Random fill + BFS solver to produce (tubes, solution_moves).
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
        solution = _solve_path(tubes, capacity)
        if solution:
            return tubes, solution

    return tubes, []


def _level_params(level):
    level = max(1, min(level, _MAX_LEVEL))
    filled = min(_MAX_FILLED, _LEVEL1_FILLED + (level - 1) // _FILLED_STEP_EVERY)
    capacity = min(_MAX_CAPACITY, _LEVEL1_CAPACITY + (level - 1) // _CAPACITY_STEP_EVERY)
    extra = max(_EXTRA_MIN, _LEVEL1_EXTRA - (level - 1) // _EXTRA_DROP_EVERY)
    return filled, capacity, extra


class Sorter(Activity):
    TUBE_BORDER = lv.color_hex(0x5D6D7E)

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
        self.shuffle_moves = []
        self._anim = None
        self.prefs = SharedPreferences(self.appFullName)
        self.highscore = self.prefs.get_int("highscore", 0)
        self.sound_effects = self._load_sound_effects()
        self.create_ui()
        self.setContentView(self.screen)
        self._check_autoload()

    def _new_game(self):
        """Start a brand new game (level 1) with a fresh emoji order."""
        self.level = 1
        self.score = 0
        self.emoji_order = _generate_emoji_order()
        self._start_level()

    def _start_level(self):
        """Generate tubes for the current level, keeping the current emoji order."""
        filled, capacity, extra = _level_params(self.level)
        self.capacity = capacity
        self.moves = 0
        self.selected = -1
        self.tubes, self.shuffle_moves = _generate_level(filled, capacity, extra)
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

        settings_btn = lv.button(self.screen)
        settings_label = lv.label(settings_btn)
        settings_label.set_text(lv.SYMBOL.SETTINGS)
        settings_btn.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        settings_btn.add_event_cb(self.on_settings, lv.EVENT.CLICKED, None)
        mpos.ui.add_focus_border(settings_btn)

        help_btn = lv.button(self.screen)
        help_label = lv.label(help_btn)
        help_label.set_text("?")
        help_btn.align_to(settings_btn, lv.ALIGN.OUT_RIGHT_MID, 4, 0)
        help_btn.add_event_cb(self.on_help, lv.EVENT.CLICKED, None)

        refresh_btn = lv.button(self.screen)
        refresh_label = lv.label(refresh_btn)
        refresh_label.set_text(lv.SYMBOL.REFRESH)
        refresh_btn.align_to(help_btn, lv.ALIGN.OUT_RIGHT_MID, 4, 0)
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
        self.container.set_size(DisplayMetrics.width(), DisplayMetrics.pct_of_height(75))
        self.container.align(lv.ALIGN.CENTER, 0, 0)
        self.container.set_style_pad_all(0, 0)
        self.container.set_style_border_width(0, 0)
        self.container.set_style_bg_opa(lv.OPA.TRANSP, 0)
        self.container.remove_flag(lv.obj.FLAG.SCROLLABLE)

        num_tubes = len(self.tubes)
        gap = 4
        tube_width = max(28, (DisplayMetrics.width() - (num_tubes - 1) * gap) // num_tubes)
        game_h = DisplayMetrics.pct_of_height(75)
        max_tube_h = DisplayMetrics.pct_of_height(65)
        emoji_sz = max(14, min(32, tube_width - 4, int(max_tube_h // (self.capacity * 1.3))))
        spacing = int(emoji_sz * 1.3)
        tube_height = spacing * self.capacity
        lift_space = int(emoji_sz * 0.75)

        total_w = num_tubes * tube_width + (num_tubes - 1) * gap
        start_x = 0
        total_h = tube_height + lift_space
        start_y = (game_h - total_h) // 2 + lift_space

        scale = int(256 * emoji_sz / 32)

        self.tube_borders = []
        self.emoji_images = []

        for idx in range(num_tubes):
            tube_x = start_x + idx * (tube_width + gap)

            border = lv.obj(self.container)
            border.set_size(tube_width, tube_height)
            border.set_pos(tube_x, start_y)
            border.set_style_bg_opa(lv.OPA.TRANSP, 0)
            border.set_style_border_color(self.TUBE_BORDER, 0)
            border.set_style_border_width(2, 0)
            border.set_style_radius(4, 0)
            border.add_flag(lv.obj.FLAG.CLICKABLE)
            border.add_event_cb(lambda e, i=idx: self.on_tube(e, i), lv.EVENT.CLICKED, None)
            mpos.ui.add_focus_border(border, mode="bg")
            self.tube_borders.append(border)

            emoji_x = tube_x + (tube_width - emoji_sz) // 2
            items = self.tubes[idx]
            imgs = []
            for i, item in enumerate(items):
                emoji_y = start_y + tube_height - (i + 1) * spacing + (spacing - emoji_sz) // 2
                img = lv.image(self.container)
                img.set_src(_EMOJI_DIR + _EMOJIS[self.emoji_order[item]])
                img.set_size(emoji_sz, emoji_sz)
                img.set_scale(scale)
                img.set_pos(emoji_x, emoji_y)
                imgs.append(img)
            self.emoji_images.append(imgs)

        self.tube_widgets = self.tube_borders
        self._emoji_sz = emoji_sz
        if self.tube_borders:
            lv.group_focus_obj(self.tube_borders[0])

    def _animate_top_emoji(self, tube_idx, up):
        imgs = self.emoji_images[tube_idx]
        if not imgs:
            return
        top = imgs[-1]
        cur = top.get_y()
        offset = int(self._emoji_sz * 0.75)
        target = cur - offset if up else cur + offset

        anim = lv.anim_t()
        anim.init()
        anim.set_var(top)
        anim.set_values(cur, target)
        anim.set_duration(150)
        anim.set_path_cb(lv.anim_t.path_ease_in_out)
        anim.set_custom_exec_cb(lambda a, v: top.set_y(int(v)))
        anim.start()
        self._anim = anim

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

    def _play_rtttl(self, rtttl):
        if not self.sound_effects:
            return
        output = AudioManager.find_output_by_kind("buzzer")
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
            self._new_game()
            self.build_board()
            self.refresh_labels()
            return
        if saved_level == 1 and saved_score == 0:
            self._new_game()
            self.build_board()
            self.refresh_labels()
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
        self._new_game()
        self.build_board()
        self.refresh_labels()

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

    def on_help(self, event):
        self._close_popup()
        if not self.shuffle_moves:
            return

        lines = [f"Level {self.level} Solution:"]
        for i, (src, tgt) in enumerate(self.shuffle_moves, 1):
            lines.append(f"{i}: from {src + 1} to {tgt + 1}")

        mbox = lv.msgbox()
        mbox.set_width(DisplayMetrics.pct_of_width(85))
        mbox.add_title("Help")
        mbox.add_text("\n".join(lines))

        content = mbox.get_content()
        content.set_height(DisplayMetrics.pct_of_height(55))
        content.add_flag(lv.obj.FLAG.SCROLLABLE)

        close_btn = mbox.add_footer_button("Close")
        close_btn.add_event_cb(self._close_popup, lv.EVENT.CLICKED, None)

        self.popup_modal = mbox

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
                self._animate_top_emoji(idx, True)
                self._play_rtttl(_RTTTL_SELECT)
            return

        if self.selected == idx:
            self._animate_top_emoji(idx, False)
            self.selected = -1
            self._last_ts = now
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
            self._animate_top_emoji(self.selected, False)
            self.selected = -1
            self._last_ts = now
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
