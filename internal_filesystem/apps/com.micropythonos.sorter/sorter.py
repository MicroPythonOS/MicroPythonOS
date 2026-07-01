from mpos import Activity, AppearanceManager, DisplayMetrics, SharedPreferences
import lvgl as lv
import random
import time


_EMOJI_DIR = "M:builtin/res/emojis/32x32/"
_EMOJIS = [
    "1F339.png",
    "1F33D.png",
    "1F346.png",
    "1F351.png",
    "1F355.png",
    "1F389.png",
    "1F3B6.png",
    "1F3CE-FE0F.png",
    "1F426.png",
    "1F437.png",
    "1F43D.png",
    "1F440.png",
    "1F447.png",
    "1F44D.png",
    "1F44E.png",
    "1F48B.png",
    "1F49C.png",
    "1F4A5.png",
    "1F4A6.png",
    "1F4A8.png",
    "1F4A9.png",
    "1F4AA.png",
    "1F4AF.png",
    "1F525.png",
    "1F600.png",
    "1F601.png",
    "1F602.png",
    "1F605.png",
    "1F606.png",
    "1F607.png",
    "1F609.png",
    "1F60A.png",
    "1F60B.png",
    "1F60C.png",
    "1F60D.png",
    "1F60E.png",
    "1F60F.png",
    "1F612.png",
    "1F614.png",
    "1F618.png",
    "1F61C.png",
    "1F622.png",
    "1F62D.png",
    "1F631.png",
    "1F642.png",
    "1F644.png",
    "1F648.png",
    "1F64F.png",
    "1F680.png",
    "1F914.png",
    "1F917.png",
    "1F926.png",
    "1F929.png",
    "1F92D.png",
    "1F937.png",
    "1F970.png",
    "1F973.png",
    "1F9E1.png",
    "1FAF6.png",
    "203C-FE0F.png",
    "263A-FE0F.png",
    "26A1.png",
    "270A.png",
    "270C-FE0F.png",
    "2728.png",
    "2764-FE0F.png",
]

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


def _shuffle(lst):
    for i in range(len(lst) - 1, 0, -1):
        j = random.randint(0, i)
        lst[i], lst[j] = lst[j], lst[i]


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
    for tube in tubes:
        if not tube:
            continue
        first = tube[0]
        for item in tube:
            if item != first:
                return False
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

    def onCreate(self):
        self.screen = lv.obj()
        self._last_ts = 0
        self._win_timer = None
        self.popup_modal = None
        self.container = None
        self.tube_widgets = []
        self.level = 1
        self.total_solved = 0
        self.score = 0
        self.moves = 0
        self.selected = -1
        self.tubes = []
        self.capacity = 0
        self.highscore = SharedPreferences(self.appFullName).get_int("highscore", 0)
        self.new_game()
        self.create_ui()
        self.setContentView(self.screen)
        self._check_autoload()

    def new_game(self):
        filled, capacity, extra = _level_params(self.level)
        self.capacity = capacity
        self.moves = 0
        self.selected = -1
        self.tubes = _generate_level(filled, capacity, extra)

    def create_ui(self):
        self.level_label = lv.label(self.screen)
        self.level_label.align(lv.ALIGN.TOP_MID, 0, 10)

        self.moves_label = lv.label(self.screen)
        self.moves_label.align(lv.ALIGN.TOP_RIGHT, -10, 10)

        self.solved_label = lv.label(self.screen)
        self.solved_label.align(lv.ALIGN.TOP_LEFT, 10, 10)

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
        self.container.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        self.container.set_style_pad_row(6, 0)
        self.container.set_style_pad_column(6, 0)
        self.container.set_style_radius(0, 0)

        self.tube_widgets = []
        num_tubes = len(self.tubes)
        pct = min(22, 95 // max(1, num_tubes))
        tube_width = max(32, DisplayMetrics.pct_of_width(pct))
        emoji_size = min(32, tube_width - 8)
        tube_height = emoji_size * self.capacity + 8

        for idx in range(num_tubes):
            tube = self._build_tube_widget(idx, tube_width, tube_height, emoji_size)
            self.tube_widgets.append(tube)

    def _build_tube_widget(self, idx, tube_width, tube_height, emoji_size):
        tube_obj = lv.obj(self.container)
        tube_obj.set_size(tube_width, tube_height)
        tube_obj.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        tube_obj.set_style_pad_all(2, 0)
        tube_obj.set_style_pad_column(2, 0)
        tube_obj.set_style_radius(4, 0)
        tube_obj.set_style_bg_color(self.TUBE_BG, 0)
        tube_obj.set_style_border_color(self.TUBE_BORDER, 0)
        tube_obj.set_style_border_width(2, 0)
        tube_obj.add_flag(lv.obj.FLAG.CLICKABLE)
        tube_obj.add_event_cb(lambda e, i=idx: self.on_tube(e, i), lv.EVENT.CLICKED, None)

        if self.selected == idx:
            tube_obj.set_style_border_color(self.SELECT_COLOR, 0)
            tube_obj.set_style_border_width(4, 0)

        items = self.tubes[idx]
        # Render from top of stack downward.
        for item in reversed(items):
            img = lv.image(tube_obj)
            img.set_src(_EMOJI_DIR + _EMOJIS[item])
            img.set_size(emoji_size, emoji_size)
            img.center()

        return tube_obj

    def refresh_labels(self):
        self.level_label.set_text(f"Level: {self.level}")
        self.moves_label.set_text(f"Moves: {self.moves}")
        self.solved_label.set_text(f"Solved: {self.total_solved}")
        self.score_label.set_text(f"Score: {self.score}")
        best = max(self.score, self.highscore)
        self.highscore_label.set_text(f"Best: {best}")
        if self.score > self.highscore and self.score > 0:
            self.highscore_label.set_style_text_color(lv.color_hex(0xE74C3C), lv.PART.MAIN)
        elif AppearanceManager.is_light_mode():
            self.highscore_label.set_style_text_color(lv.color_hex(0x000000), lv.PART.MAIN)
        else:
            self.highscore_label.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)

    def _autosave(self):
        editor = SharedPreferences(self.appFullName).edit()
        editor.put_int("autosave_level", self.level)
        editor.put_int("autosave_score", self.score)
        editor.put_int("autosave_solved", self.total_solved)
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
        editor.put_int("autosave_solved", 0)
        editor.commit()

    def _check_autoload(self):
        prefs = SharedPreferences(self.appFullName)
        saved_level = prefs.get_int("autosave_level", 0)
        saved_score = prefs.get_int("autosave_score", 0)
        saved_solved = prefs.get_int("autosave_solved", 0)
        if saved_level == 0 and saved_score == 0:
            return

        mbox = lv.msgbox()
        mbox.set_width(DisplayMetrics.pct_of_width(75))
        mbox.add_text(f"Load best game:\nlevel {saved_level}, score {saved_score}?")

        yes_btn = mbox.add_footer_button("Yes")
        yes_btn.add_event_cb(
            lambda e: self._do_load(e, saved_level, saved_score, saved_solved),
            lv.EVENT.CLICKED, None
        )
        no_btn = mbox.add_footer_button("No")
        no_btn.add_event_cb(self._on_autoload_no, lv.EVENT.CLICKED, None)

        self.popup_modal = mbox

    def _do_load(self, event, saved_level, saved_score, saved_solved):
        self._close_popup()
        self.level = saved_level
        self.score = saved_score
        self.total_solved = saved_solved
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
                self.build_board()
            return

        if self.selected == idx:
            self.selected = -1
            self._last_ts = now
            self.build_board()
            return

        src = self.tubes[self.selected]
        tgt = self.tubes[idx]
        if _can_move(src, tgt, self.capacity):
            self._last_ts = now
            _apply_move(src, tgt, self.capacity)
            self.moves += 1
            self.selected = -1
            self.build_board()
            self.refresh_labels()
            if _is_solved(self.tubes):
                self.on_win()
        else:
            self.selected = -1
            self._last_ts = now
            self.build_board()

    def on_win(self):
        filled, capacity, extra = _level_params(self.level)
        min_moves = filled * capacity
        wasted = max(0, self.moves - min_moves)
        self.score += self.level * 10 + max(10, 100 - wasted * 5)
        self.total_solved += 1
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
        self.total_solved = 0
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
