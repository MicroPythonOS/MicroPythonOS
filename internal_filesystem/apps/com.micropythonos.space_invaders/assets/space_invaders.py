from mpos import Activity, DisplayMetrics, InputManager, SharedPreferences
import random
import time
import lvgl as lv


SPRITE_W = 20
SPRITE_H = 20
PLAYER_W = 24
PLAYER_H = 18
BULLET_W = 4
BULLET_H = 14
COLS = 8

_G = lv.color_hex(0x00FF00)
_C = lv.color_hex(0x00FFFF)
_Y = lv.color_hex(0xFFFF00)
_R = lv.color_hex(0xFF0000)
_W = lv.color_hex(0xFFFFFF)
_O = lv.color_hex(0xFF8800)
_P = lv.color_hex(0xFF00FF)
_LG = lv.color_hex(0x88FF88)
_BG = lv.color_hex(0x000011)


INVADER_A_TEMPLATE = (
    "     ##  ##     ",
    "    #  ##  #    ",
    "   ##########   ",
    "  ############  ",
    "  ############# ",
    "  ##  ####  ##  ",
    "  ##  ####  ##  ",
    "  #   ####   #  ",
    "  ##  #  #  ##  ",
    "  ### #  # ###  ",
    "  ### #  # ###  ",
    "   ##      ##   ",
    "   #        #   ",
    "  # ##    ## #  ",
    " #  #      #  # ",
    " #  #      #  # ",
)

INVADER_B_TEMPLATE = (
    "      #  #      ",
    "     ######     ",
    "    ########    ",
    "   ##########   ",
    "  ## # ## # ##  ",
    "  ############# ",
    "  ############# ",
    "  ############# ",
    "  ##  #  #  ##  ",
    "  #   #  #   #  ",
    "  #  #    #  #  ",
    "   ## #  # ##   ",
    "   ## #  # ##   ",
    "  #  #    #  #  ",
    " ##  #    #  ## ",
    " #   #    #   # ",
)

INVADER_C_TEMPLATE = (
    "    ##    ##    ",
    "   #  #  #  #   ",
    "  ############# ",
    "  ############# ",
    "  ############# ",
    "  # ## # ## #   ",
    "   # ## ## #    ",
    "   #  ###  #    ",
    "   ########     ",
    "   ## # # ##    ",
    "  #  #   #  #   ",
    "  #  #   #  #   ",
    "  #  #   #  #   ",
    "  #  #   #  #   ",
    "  #  #   #  #   ",
    "  #  #   #  #   ",
)

PLAYER_TEMPLATE = (
    "          #           ",
    "         ###          ",
    "        #####         ",
    "       #######        ",
    "      #########       ",
    "     ###########      ",
    "    #############     ",
    "   ###############    ",
    "   ###############    ",
    "   ###############    ",
    "   ####       ####    ",
    "   ####       ####    ",
    "   ####       ####    ",
    "    ###       ###     ",
    "    ###       ###     ",
    "    ###       ###     ",
    "     #         #      ",
    "     #         #      ",
)

EXPLOSION_TEMPLATE = (
    "  #    #    #  ",
    "   #   #   #   ",
    "  # ### ### #  ",
    "   ########   ",
    "  ##  ###  ##  ",
    " ########### ",
    " ########### ",
    "  ##  ###  ##  ",
    "   ########   ",
    "  # ### ### #  ",
    "   #   #   #   ",
    "  #    #    #  ",
)


class SpaceInvaders(Activity):
    def onCreate(self):
        self.screen = lv.obj()
        self.screen.add_flag(lv.obj.FLAG.CLICKABLE)
        self.screen.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.screen.set_style_bg_color(_BG, 0)

        self.update_timer = None
        self.last_time = 0
        self._popup_modal = None

        prefs = SharedPreferences(self.appFullName)
        self.highscore = prefs.get_int("highscore", 0)

        self.score = 0
        self.level = 1
        self.lives = 3
        self.game_state = "start"
        self.player_x = 0
        self.player_dir = 0
        self.player_canvas = None

        self.invaders = []
        self.bullets = []
        self.enemy_bullets = []
        self.invader_canvases = []
        self.bullet_pool = []
        self.enemy_bullet_pool = []
        self.explosion_pool = []
        self.active_explosions = []

        self.invader_direction = 1
        self.invader_speed = 0
        self.invader_drop_dist = 0
        self.invader_move_accum = 0.0
        self.invader_shoot_timer = 0.0

        self.shoot_cooldown = 0.0
        self.touch_last_x = None

        self._create_ui()
        self._create_game_area()
        self._create_entity_pools()

        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(self.screen)

        self.screen.add_event_cb(self.on_tap, lv.EVENT.ALL, None)
        self.screen.add_event_cb(self.on_key, lv.EVENT.KEY, None)

        self.setContentView(self.screen)

        prefs = SharedPreferences(self.appFullName)
        saved_level = prefs.get_int("autosave_level", 0)
        saved_lives = prefs.get_int("autosave_lives", 0)
        if saved_level > 0 and saved_lives > 0:
            self._check_autoload()
        else:
            self._show_start_screen()

    def on_key(self, event):
        key = event.get_key()
        if self.game_state != "playing":
            if key in (lv.KEY.ENTER, lv.KEY.UP, 0x20):
                self._start_game()
            return
        if key == lv.KEY.LEFT:
            self.player_dir = -1
        elif key == lv.KEY.RIGHT:
            self.player_dir = 1
        elif key in (lv.KEY.UP, lv.KEY.ENTER, 0x20):
            self._fire_player_bullet()

    def on_tap(self, event):
        code = event.get_code()
        if code == lv.EVENT.PRESSED:
            if self.game_state != "playing":
                self._start_game()
                return
            tx, ty = InputManager.pointer_xy()
            ga_y = self.game_area.get_y()
            if ty < ga_y or ty > ga_y + self.ga_h:
                return
            self._fire_player_bullet()
            self.touch_last_x = tx
            self.player_dir = 0
            return
        if code == lv.EVENT.PRESSING:
            if self.game_state == "playing":
                tx, ty = InputManager.pointer_xy()
                ga_y = self.game_area.get_y()
                if ty < ga_y or ty > ga_y + self.ga_h:
                    return
                if self.touch_last_x is not None:
                    delta = tx - self.touch_last_x
                    self.player_x += delta
                    self.player_x = max(
                        PLAYER_W // 2,
                        min(self.player_x, self.ga_w - PLAYER_W // 2),
                    )
                self.touch_last_x = tx
            return
        if code == lv.EVENT.RELEASED:
            self.touch_last_x = None
            self.player_dir = 0

    def _create_ui(self):
        top = lv.obj(self.screen)
        top.set_size(lv.pct(100), DisplayMetrics.pct_of_height(12))
        top.align(lv.ALIGN.TOP_MID, 0, 0)
        top.set_style_bg_color(lv.color_hex(0x000022), 0)
        top.set_style_border_width(0, 0)
        top.set_style_pad_all(2, 0)

        self.score_label = lv.label(top)
        self.score_label.align(lv.ALIGN.LEFT_MID, 4, 0)
        self.score_label.set_style_text_color(_W, 0)
        self.score_label.set_text("SCORE: 0")

        self.level_label = lv.label(top)
        self.level_label.align(lv.ALIGN.TOP_MID, 0, 2)

        self.highscore_label = lv.label(top)
        self.highscore_label.align(lv.ALIGN.RIGHT_MID, -4, 0)
        self.highscore_label.set_style_text_color(_W, 0)
        self.highscore_label.add_flag(lv.obj.FLAG.CLICKABLE)
        self.highscore_label.add_event_cb(
            self._on_highscore_tap, lv.EVENT.CLICKED, None
        )

        self.lives_label = lv.label(top)
        self.lives_label.align(lv.ALIGN.BOTTOM_MID, 0, -2)
        self.lives_label.set_style_text_color(_R, 0)

    def _create_game_area(self):
        self.game_area = lv.obj(self.screen)
        self.game_area.set_size(DisplayMetrics.width(), DisplayMetrics.pct_of_height(82))
        self.game_area.align(lv.ALIGN.TOP_MID, 0, DisplayMetrics.pct_of_height(12))
        self.game_area.set_style_bg_color(lv.color_hex(0x000008), 0)
        self.game_area.set_style_border_width(0, 0)
        self.game_area.set_style_pad_all(0, 0)
        self.game_area.set_style_radius(0, 0)
        self.game_area.set_style_clip_corner(True, 0)
        self.game_area.add_flag(lv.obj.FLAG.EVENT_BUBBLE)
        self.game_area.remove_flag(lv.obj.FLAG.SCROLLABLE)

        self.ga_w = DisplayMetrics.width()
        self.ga_h = DisplayMetrics.pct_of_height(82)

        self._spacing_x = max(
            2, (self.ga_w - COLS * SPRITE_W) // (COLS + 1)
        )
        self._spacing_y = max(2, SPRITE_H + 6)
        self._invader_start_y = 8

        self._player_speed = self.ga_w * 0.55
        self._bullet_speed = self.ga_h * 0.9

    def _make_sprite(self, parent, pixel_data, w, h, color):
        canvas = lv.canvas(parent)
        canvas.set_size(w, h)
        buf = bytearray(w * h * 4)
        canvas.set_buffer(buf, w, h, lv.COLOR_FORMAT.NATIVE)
        canvas.set_style_border_width(0, 0)
        canvas.set_style_bg_opa(lv.OPA.TRANSP, 0)

        for y, row in enumerate(pixel_data):
            if y >= h:
                break
            for x, ch in enumerate(row):
                if x >= w:
                    break
                if ch == "#":
                    canvas.set_px(x, y, color, lv.OPA.COVER)
        return canvas

    def _create_entity_pools(self):
        max_invaders = COLS * 5
        templates = [
            (INVADER_A_TEMPLATE, _G),
            (INVADER_B_TEMPLATE, _LG),
            (INVADER_C_TEMPLATE, _P),
        ]

        self.invader_canvases = []
        for i in range(max_invaders):
            tmpl, col = templates[i % 3]
            c = self._make_sprite(self.game_area, tmpl, SPRITE_W, SPRITE_H, col)
            c.add_flag(lv.obj.FLAG.HIDDEN)
            c.set_style_bg_opa(lv.OPA.TRANSP, 0)
            self.invader_canvases.append(c)

        self.player_canvas = self._make_sprite(
            self.game_area, PLAYER_TEMPLATE, PLAYER_W, PLAYER_H, _C
        )
        self.player_canvas.add_flag(lv.obj.FLAG.HIDDEN)

        bullet_style = lv.style_t()
        bullet_style.init()
        bullet_style.set_bg_color(_Y)
        bullet_style.set_bg_opa(lv.OPA.COVER)
        bullet_style.set_border_width(0)
        bullet_style.set_radius(2)

        self.bullet_pool = []
        for _ in range(8):
            b = lv.obj(self.game_area)
            b.set_size(BULLET_W, BULLET_H)
            b.add_style(bullet_style, 0)
            b.add_flag(lv.obj.FLAG.HIDDEN)
            self.bullet_pool.append(b)

        enemy_style = lv.style_t()
        enemy_style.init()
        enemy_style.set_bg_color(_R)
        enemy_style.set_bg_opa(lv.OPA.COVER)
        enemy_style.set_border_width(0)
        enemy_style.set_radius(4)

        self.enemy_bullet_pool = []
        for _ in range(8):
            b = lv.obj(self.game_area)
            b.set_size(5, 10)
            b.add_style(enemy_style, 0)
            b.add_flag(lv.obj.FLAG.HIDDEN)
            self.enemy_bullet_pool.append(b)

        self.explosion_pool = []
        for _ in range(4):
            c = self._make_sprite(
                self.game_area, EXPLOSION_TEMPLATE, SPRITE_W, SPRITE_H, _O
            )
            c.add_flag(lv.obj.FLAG.HIDDEN)
            self.explosion_pool.append(c)

    def _show_start_screen(self):
        self.game_state = "start"
        if self.highscore > 0:
            txt = "SPACE INVADERS\n\nHigh Score: " + str(self.highscore)
        else:
            txt = "SPACE INVADERS\n\nNo high score yet"
        txt += "\n\nTap or press A/ENTER to start"
        self._create_cover_overlay(txt, "start")

    def _create_cover_overlay(self, text, state):
        self._close_popup()
        modal = lv.obj(self.game_area)
        modal.set_size(self.ga_w, self.ga_h)
        modal.set_pos(0, 0)
        modal.set_style_bg_color(lv.color_hex(0x000011), 0)
        modal.set_style_border_width(0, 0)
        modal.set_style_radius(0, 0)
        modal.add_flag(lv.obj.FLAG.EVENT_BUBBLE)
        modal.remove_flag(lv.obj.FLAG.SCROLLABLE)

        label = lv.label(modal)
        label.set_text(text)
        label.set_style_text_color(_G, 0)
        label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        label.set_long_mode(lv.label.LONG_MODE.WRAP)
        label.set_size(self.ga_w - 20, self.ga_h - 20)
        label.center()

        self._popup_modal = modal

    def _close_popup(self, event=None):
        if self._popup_modal:
            self._popup_modal.delete()
            self._popup_modal = None

    def _start_game(self):
        self._close_popup()
        self._delete_autosave()
        self.score = 0
        self.level = 1
        self.lives = 3
        self._start_level()
        self.game_state = "playing"
        self._update_labels()

    def _start_level(self):
        rows = min(3 + self.level - 1, 5)

        self.invaders = []
        inv_types = [0, 1, 2]
        for r in range(rows):
            t = inv_types[r % 3]
            for c in range(COLS):
                self.invaders.append(
                    {
                        "col": c,
                        "row": r,
                        "type": t,
                        "alive": True,
                        "x": 0,
                        "y": 0,
                    }
                )

        self._recalc_invader_positions()

        self.invader_direction = 1
        self.invader_speed = 30 + self.level * 8
        self.invader_drop_dist = SPRITE_H // 4 + 2
        self.invader_move_accum = 0.0
        self.invader_shoot_timer = 0.0
        self.shoot_cooldown = 0.0

        self.bullets = []
        self.enemy_bullets = []
        self.active_explosions = []

        self.player_x = self.ga_w // 2
        self.player_dir = 0
        self.player_canvas.remove_flag(lv.obj.FLAG.HIDDEN)

        self._update_entity_positions()
        self._update_labels()

    def _recalc_invader_positions(self):
        alive = [i for i in self.invaders if i["alive"]]
        if not alive:
            return
        min_col = min(i["col"] for i in alive)
        max_col = max(i["col"] for i in alive)
        min_row = min(i["row"] for i in alive)
        for i in self.invaders:
            i["x"] = (
                self._spacing_x
                + (i["col"] - min_col) * (SPRITE_W + self._spacing_x)
            )
            i["y"] = self._invader_start_y + (i["row"] - min_row) * self._spacing_y

    def _update_entity_positions(self):
        px = int(self.player_x - PLAYER_W // 2)
        self.player_canvas.set_pos(
            max(0, min(px, self.ga_w - PLAYER_W)), self.ga_h - PLAYER_H - 4
        )

        idx = 0
        for inv in self.invaders:
            if inv["alive"]:
                c = self.invader_canvases[idx]
                c.remove_flag(lv.obj.FLAG.HIDDEN)
                c.set_pos(int(inv["x"]), int(inv["y"]))
                idx += 1

        for idx in range(idx, len(self.invader_canvases)):
            self.invader_canvases[idx].add_flag(lv.obj.FLAG.HIDDEN)

        for b in self.bullet_pool:
            b.add_flag(lv.obj.FLAG.HIDDEN)
        for i, b_data in enumerate(self.bullets):
            if i < len(self.bullet_pool):
                self.bullet_pool[i].remove_flag(lv.obj.FLAG.HIDDEN)
                self.bullet_pool[i].set_pos(int(b_data["x"]), int(b_data["y"]))

        for b in self.enemy_bullet_pool:
            b.add_flag(lv.obj.FLAG.HIDDEN)
        for i, b_data in enumerate(self.enemy_bullets):
            if i < len(self.enemy_bullet_pool):
                self.enemy_bullet_pool[i].remove_flag(lv.obj.FLAG.HIDDEN)
                self.enemy_bullet_pool[i].set_pos(
                    int(b_data["x"]), int(b_data["y"])
                )

        for e in self.explosion_pool:
            e.add_flag(lv.obj.FLAG.HIDDEN)
        for i, exp in enumerate(self.active_explosions):
            if i < len(self.explosion_pool):
                self.explosion_pool[i].remove_flag(lv.obj.FLAG.HIDDEN)
                self.explosion_pool[i].set_pos(int(exp["x"]), int(exp["y"]))

    def _update_labels(self):
        self.score_label.set_text("SCORE: " + str(self.score))
        self.level_label.set_text("LEVEL " + str(self.level))
        self.level_label.set_style_text_color(_Y, 0)
        lives_str = "♥" * max(0, self.lives)
        self.lives_label.set_text(lives_str)
        best = max(self.score, self.highscore)
        self.highscore_label.set_text("HI: " + str(best))
        if self.score > self.highscore and self.score > 0:
            self.highscore_label.set_style_text_color(_R, 0)
        else:
            self.highscore_label.set_style_text_color(_W, 0)

    def onResume(self, screen):
        self.ga_w = DisplayMetrics.width()
        self.ga_h = DisplayMetrics.pct_of_height(82)
        self._spacing_x = max(
            2, (self.ga_w - COLS * SPRITE_W) // (COLS + 1)
        )
        self._player_speed = self.ga_w * 0.55
        self._bullet_speed = self.ga_h * 0.9
        self.update_timer = lv.timer_create(self._update_frame, 33, None)
        self.last_time = time.ticks_ms()

    def onPause(self, screen):
        if self.update_timer:
            self.update_timer.delete()
            self.update_timer = None
        self._autosave()

    def onDestroy(self, screen):
        if self.update_timer:
            self.update_timer.delete()
            self.update_timer = None
        self._save_highscore()
        self._close_popup()

    def _update_frame(self, timer):
        now = time.ticks_ms()
        delta_ms = time.ticks_diff(now, self.last_time)
        self.last_time = now
        dt = delta_ms / 1000.0
        if dt > 0.05:
            dt = 0.05

        if self.game_state == "playing":
            self._update_game(dt)
            self._update_entity_positions()
            self._update_labels()

    def _update_game(self, dt):
        self._move_player(dt)
        self._move_invaders(dt)
        self._move_bullets(dt)
        self._move_enemy_bullets(dt)
        self._check_collisions()
        self._check_level_complete()
        self._check_game_over()
        self._update_explosions(dt)

    def _move_player(self, dt):
        if self.player_dir != 0:
            self.player_x += self.player_dir * self._player_speed * dt
            self.player_x = max(PLAYER_W // 2, min(self.player_x, self.ga_w - PLAYER_W // 2))

        self.shoot_cooldown = max(0, self.shoot_cooldown - dt)

    def _move_invaders(self, dt):
        alive = [i for i in self.invaders if i["alive"]]
        if not alive:
            return

        self.invader_move_accum += self.invader_speed * dt

        while self.invader_move_accum >= 1:
            self.invader_move_accum -= 1
            should_drop = False
            for inv in alive:
                inv["x"] += self.invader_direction
                if inv["x"] <= 0 or inv["x"] >= self.ga_w - SPRITE_W:
                    should_drop = True

            if should_drop:
                self.invader_direction *= -1
                for inv in alive:
                    inv["x"] += self.invader_direction
                    inv["y"] += self.invader_drop_dist
                for inv in alive:
                    if inv["y"] >= self.ga_h - PLAYER_H - SPRITE_H - 10:
                        self.game_state = "game_over"
                        self._on_game_over()
                        return

        self.invader_shoot_timer -= dt
        if self.invader_shoot_timer <= 0 and alive:
            self.invader_shoot_timer = 0.5 + random.random() * 1.5 / (1 + self.level * 0.2)
            shooter = random.choice(alive)
            self._fire_enemy_bullet(
                shooter["x"] + SPRITE_W // 2, shooter["y"] + SPRITE_H
            )

    def _move_bullets(self, dt):
        for b in self.bullets[:]:
            b["y"] -= self._bullet_speed * dt
            if b["y"] + BULLET_H < 0:
                self.bullets.remove(b)

    def _move_enemy_bullets(self, dt):
        for b in self.enemy_bullets[:]:
            b["y"] += self._bullet_speed * 0.6 * dt
            if b["y"] > self.ga_h:
                self.enemy_bullets.remove(b)

    def _check_collisions(self):
        for b in self.bullets[:]:
            bx, by = b["x"], b["y"]
            bw, bh = BULLET_W, BULLET_H
            hit = False
            for inv in self.invaders:
                if not inv["alive"]:
                    continue
                ix, iy = inv["x"], inv["y"]
                if (
                    bx < ix + SPRITE_W
                    and bx + bw > ix
                    and by < iy + SPRITE_H
                    and by + bh > iy
                ):
                    inv["alive"] = False
                    self.score += 10 + inv["type"] * 10
                    self.bullets.remove(b)
                    self._spawn_explosion(ix, iy)
                    hit = True
                    break

        for eb in self.enemy_bullets[:]:
            ex, ey = eb["x"], eb["y"]
            ew, eh = 5, 10
            px = self.player_x - PLAYER_W // 2
            py = self.ga_h - PLAYER_H - 4
            if (
                ex < px + PLAYER_W
                and ex + ew > px
                and ey < py + PLAYER_H
                and ey + eh > py
            ):
                self.enemy_bullets.remove(eb)
                self._on_player_hit()

    def _on_player_hit(self):
        if self.game_state != "playing":
            return
        self.lives -= 1
        self._spawn_explosion(
            self.player_x - SPRITE_W // 2, self.ga_h - PLAYER_H - SPRITE_H
        )
        self.player_canvas.add_flag(lv.obj.FLAG.HIDDEN)
        if self.lives <= 0:
            self.game_state = "game_over"
            self._on_game_over()
        else:
            lv.timer_create(self._respawn_player, 1000, None).set_repeat_count(1)

    def _respawn_player(self, timer):
        self.player_canvas.remove_flag(lv.obj.FLAG.HIDDEN)
        self.player_x = self.ga_w // 2

    def _spawn_explosion(self, x, y):
        for exp in self.active_explosions:
            if exp["timer"] > 0.25:
                exp["x"] = x
                exp["y"] = y
                exp["timer"] = 0
                return
        self.active_explosions.append({"x": x, "y": y, "timer": 0})

    def _update_explosions(self, dt):
        for exp in self.active_explosions[:]:
            exp["timer"] += dt
            if exp["timer"] > 0.3:
                self.active_explosions.remove(exp)

    def _fire_enemy_bullet(self, x, y):
        b = {"x": x - 2, "y": y}
        self.enemy_bullets.append(b)

    def _fire_player_bullet(self):
        if self.shoot_cooldown > 0:
            return
        b = {"x": self.player_x - BULLET_W // 2, "y": self.ga_h - PLAYER_H - BULLET_H - 8}
        self.bullets.append(b)
        self.shoot_cooldown = 0.25

    def _check_level_complete(self):
        if self.game_state != "playing":
            return
        alive = [i for i in self.invaders if i["alive"]]
        if not alive:
            self.level += 1
            lv.timer_create(self._start_level_delayed, 500, None).set_repeat_count(1)

    def _start_level_delayed(self, timer):
        self._start_level()

    def _check_game_over(self):
        if self.game_state == "game_over":
            return
        for inv in self.invaders:
            if inv["alive"] and inv["y"] >= self.ga_h - PLAYER_H - SPRITE_H - 10:
                self.game_state = "game_over"
                self._on_game_over()
                return

    def _on_game_over(self):
        self._save_highscore()
        self.player_canvas.add_flag(lv.obj.FLAG.HIDDEN)
        self._close_popup()
        self._create_cover_overlay(
            " GAME OVER\n\nScore: "
            + str(self.score)
            + "\nBest: "
            + str(max(self.score, self.highscore))
            + "\n\nTap or press A/ENTER to restart",
            "game_over",
        )

    def _on_highscore_tap(self, event):
        self._close_popup()
        modal = lv.obj(lv.layer_top())
        modal.set_size(DisplayMetrics.width(), DisplayMetrics.height())
        modal.set_pos(0, 0)
        modal.set_style_bg_color(lv.color_hex(0x000000), 0)
        modal.set_style_bg_opa(160, 0)
        modal.set_style_border_width(0, 0)

        popup = lv.obj(modal)
        popup.set_size(200, 130)
        popup.set_style_bg_color(lv.color_hex(0x222222), 0)
        popup.set_style_border_color(_G, 0)
        popup.set_style_border_width(2, 0)
        popup.set_style_radius(10, 0)
        popup.center()

        q = lv.label(popup)
        q.set_text("Reset high score?")
        q.set_style_text_color(_W, 0)
        q.align(lv.ALIGN.TOP_MID, 0, 15)

        yes_btn = lv.button(popup)
        yes_btn.set_size(75, 35)
        yes_btn.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        yes_btn.add_event_cb(self._on_reset_hs_yes, lv.EVENT.CLICKED, None)
        yes_lbl = lv.label(yes_btn)
        yes_lbl.set_text("Yes")
        yes_lbl.center()

        no_btn = lv.button(popup)
        no_btn.set_size(75, 35)
        no_btn.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        no_btn.add_event_cb(self._close_modal, lv.EVENT.CLICKED, None)
        no_lbl = lv.label(no_btn)
        no_lbl.set_text("No")
        no_lbl.center()

        self._popup_modal = modal

    def _close_modal(self, event=None):
        self._close_popup()

    def _on_reset_hs_yes(self, event):
        self.highscore = 0
        editor = SharedPreferences(self.appFullName).edit()
        editor.put_int("highscore", 0)
        editor.commit()
        self._close_popup()
        self._update_labels()

    def _save_highscore(self):
        best = max(self.score, self.highscore)
        if best > self.highscore:
            self.highscore = best
            editor = SharedPreferences(self.appFullName).edit()
            editor.put_int("highscore", self.highscore)
            editor.commit()

    def _autosave(self):
        if self.game_state == "playing" and self.lives > 0:
            editor = SharedPreferences(self.appFullName).edit()
            editor.put_int("autosave_level", self.level)
            editor.put_int("autosave_score", self.score)
            editor.put_int("autosave_lives", self.lives)
            editor.commit()

    def _delete_autosave(self):
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
        if saved_level == 0 or saved_lives <= 0:
            return

        self._close_popup()
        modal = lv.obj(lv.layer_top())
        modal.set_size(DisplayMetrics.width(), DisplayMetrics.height())
        modal.set_pos(0, 0)
        modal.set_style_bg_color(lv.color_hex(0x000000), 0)
        modal.set_style_bg_opa(160, 0)
        modal.set_style_border_width(0, 0)

        popup = lv.obj(modal)
        popup.set_size(220, 140)
        popup.set_style_bg_color(lv.color_hex(0x222222), 0)
        popup.set_style_border_color(_G, 0)
        popup.set_style_border_width(2, 0)
        popup.set_style_radius(10, 0)
        popup.center()

        q = lv.label(popup)
        q.set_text(
            "Continue saved game?\nLevel "
            + str(saved_level)
            + ", Score "
            + str(saved_score)
        )
        q.set_style_text_color(_W, 0)
        q.set_long_mode(lv.label.LONG_MODE.WRAP)
        q.set_size(200, 80)
        q.align(lv.ALIGN.TOP_MID, 0, 10)

        yes_btn = lv.button(popup)
        yes_btn.set_size(75, 35)
        yes_btn.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        yes_btn.add_event_cb(
            lambda e: self._do_autoload(e, saved_level, saved_score, saved_lives),
            lv.EVENT.CLICKED,
            None,
        )
        yes_lbl = lv.label(yes_btn)
        yes_lbl.set_text("Yes")
        yes_lbl.center()

        no_btn = lv.button(popup)
        no_btn.set_size(75, 35)
        no_btn.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        no_btn.add_event_cb(self._on_autoload_no, lv.EVENT.CLICKED, None)
        no_lbl = lv.label(no_btn)
        no_lbl.set_text("No")
        no_lbl.center()

        self._popup_modal = modal

    def _on_autoload_no(self, event):
        self._close_popup()
        self._show_start_screen()

    def _do_autoload(self, event, saved_level, saved_score, saved_lives):
        self._close_popup()
        self.score = saved_score
        self.level = saved_level
        self.lives = saved_lives
        self._start_level()
        self.game_state = "playing"
        self._update_labels()
