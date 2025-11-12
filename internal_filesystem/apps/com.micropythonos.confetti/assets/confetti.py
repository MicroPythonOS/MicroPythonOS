import time
import random
import lvgl as lv

from mpos.apps import Activity, Intent
import mpos.config
import mpos.ui

class Confetti(Activity):
    # === CONFIG ===
    SCREEN_WIDTH = 320
    SCREEN_HEIGHT = 240
    ASSET_PATH = "M:apps/com.micropythonos.confetti/res/drawable-mdpi/"
    MAX_CONFETTI = 21
    GRAVITY = 100  # pixels/sec²

    def onCreate(self):
        print("Confetti Activity starting...")

        # Background
        self.screen = lv.obj()
        self.screen.set_style_bg_color(lv.color_hex(0x000033), 0)  # Dark blue
        self.screen.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        self.screen.remove_flag(lv.obj.FLAG.SCROLLABLE)

        # Timing
        self.last_time = time.ticks_ms()

        # Confetti state
        self.confetti_pieces = []
        self.confetti_images = []
        self.used_img_indices = set()  # Track which image slots are in use

        # Pre-create LVGL image objects
        for i in range(self.MAX_CONFETTI):
            img = lv.image(self.screen)
            img.set_src(f"{self.ASSET_PATH}confetti{random.randint(1,3)}.png")
            img.add_flag(lv.obj.FLAG.HIDDEN)
            self.confetti_images.append(img)

        # Spawn initial confetti
        for _ in range(self.MAX_CONFETTI):
            self.spawn_confetti()

        self.setContentView(self.screen)

    def onResume(self, screen):
        mpos.ui.th.add_event_cb(self.update_frame, 1)

    def onPause(self, screen):
        mpos.ui.th.remove_event_cb(self.update_frame)

    def spawn_confetti(self):
        """Safely spawn a new confetti piece with unique img_idx"""
        # Find a free image slot
        for idx, img in enumerate(self.confetti_images):
            if img.has_flag(lv.obj.FLAG.HIDDEN) and idx not in self.used_img_indices:
                break
        else:
            return  # No free slot

        piece = {
            'img_idx': idx,
            'x': random.uniform(-10, self.SCREEN_WIDTH + 10),
            'y': random.uniform(50, 100),
            'vx': random.uniform(-100, 100),
            'vy': random.uniform(-250, -80),
            'spin': random.uniform(-400, 400),
            'age': 0.0,
            'lifetime': random.uniform(1.8, 5),
            'rotation': random.uniform(0, 360),
            'scale': 1.0
        }
        self.confetti_pieces.append(piece)
        self.used_img_indices.add(idx)

    def update_frame(self, a, b):
        current_time = time.ticks_ms()
        delta_ms = time.ticks_diff(current_time, self.last_time)
        delta_time = delta_ms / 1000.0
        self.last_time = current_time

        new_pieces = []

        for piece in self.confetti_pieces:
            # === UPDATE PHYSICS ===
            piece['age'] += delta_time
            piece['x'] += piece['vx'] * delta_time
            piece['y'] += piece['vy'] * delta_time
            piece['vy'] += self.GRAVITY * delta_time
            piece['rotation'] += piece['spin'] * delta_time
            piece['scale'] = max(0.3, 1.0 - (piece['age'] / piece['lifetime']) * 0.7)

            # === UPDATE LVGL IMAGE ===
            img = self.confetti_images[piece['img_idx']]
            img.remove_flag(lv.obj.FLAG.HIDDEN)
            img.set_pos(int(piece['x']), int(piece['y']))
            img.set_rotation(int(piece['rotation'] * 10))  # LVGL: 0.1 degrees
            img.set_scale(int(256 * piece['scale']* 2))       # 256 = 100%

            # === CHECK IF DEAD ===
            off_screen = (
                piece['x'] < -60 or piece['x'] > self.SCREEN_WIDTH + 60 or
                piece['y'] > self.SCREEN_HEIGHT + 60
            )
            too_old = piece['age'] > piece['lifetime']

            if off_screen or too_old:
                img.add_flag(lv.obj.FLAG.HIDDEN)
                self.used_img_indices.discard(piece['img_idx'])
                self.spawn_confetti()  # Replace immediately
            else:
                new_pieces.append(piece)

        # === APPLY NEW LIST ===
        self.confetti_pieces = new_pieces
