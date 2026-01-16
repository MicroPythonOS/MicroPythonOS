import time
import random
import lvgl as lv
import mpos.ui


class Confetti:
    """Manages confetti animation with physics simulation."""
    
    def __init__(self, screen, icon_path, asset_path, duration=10000):
        """
        Initialize the Confetti system.
        
        Args:
            screen: The LVGL screen/display object
            icon_path: Path to icon assets (e.g., "M:apps/com.lightningpiggy.displaywallet/res/mipmap-mdpi/")
            asset_path: Path to confetti assets (e.g., "M:apps/com.lightningpiggy.displaywallet/res/drawable-mdpi/")
            max_confetti: Maximum number of confetti pieces to display
        """
        self.screen = screen
        self.icon_path = icon_path
        self.asset_path = asset_path
        self.duration = duration
        self.max_confetti = 21
        
        # Physics constants
        self.GRAVITY = 100  # pixels/sec²
        
        # Screen dimensions
        self.screen_width = screen.get_display().get_horizontal_resolution()
        self.screen_height = screen.get_display().get_vertical_resolution()
        
        # State
        self.is_running = False
        self.last_time = time.ticks_ms()
        self.confetti_pieces = []
        self.confetti_images = []
        self.used_img_indices = set()
        
        # Spawn control
        self.spawn_timer = 0
        self.spawn_interval = 0.15  # seconds
        self.animation_start = 0

        
        # Pre-create LVGL image objects
        self._init_images()
    
    def _init_images(self):
        """Pre-create LVGL image objects for confetti."""
        iconimages = 2
        for _ in range(iconimages):
            img = lv.image(lv.layer_top())
            img.set_src(f"{self.icon_path}icon_64x64.png")
            img.add_flag(lv.obj.FLAG.HIDDEN)
            self.confetti_images.append(img)
        
        for i in range(self.max_confetti - iconimages):
            img = lv.image(lv.layer_top())
            img.set_src(f"{self.asset_path}confetti{random.randint(0, 4)}.png")
            img.add_flag(lv.obj.FLAG.HIDDEN)
            self.confetti_images.append(img)
    
    def start(self):
        """Start the confetti animation."""
        if self.is_running:
            return
        
        self.is_running = True
        self.last_time = time.ticks_ms()
        self._clear_confetti()
        
        # Staggered spawn control
        self.spawn_timer = 0
        self.animation_start = time.ticks_ms() / 1000.0
        
        # Initial burst
        for _ in range(10):
            self._spawn_one()
        
        # Register update callback
        mpos.ui.task_handler.add_event_cb(self._update_frame, 1)
        
        # Stop spawning after 15 seconds
        lv.timer_create(self.stop, self.duration, None).set_repeat_count(1)
    
    def stop(self, timer=None):
        """Stop the confetti animation."""
        self.is_running = False
    
    def _clear_confetti(self):
        """Clear all confetti pieces from the screen."""
        for img in self.confetti_images:
            img.add_flag(lv.obj.FLAG.HIDDEN)
        self.confetti_pieces = []
        self.used_img_indices.clear()
    
    def _update_frame(self, a, b):
        """Update frame for confetti animation. Called by task handler."""
        current_time = time.ticks_ms()
        delta_time = time.ticks_diff(current_time, self.last_time) / 1000.0
        self.last_time = current_time
        
        # === STAGGERED SPAWNING ===
        if self.is_running:
            self.spawn_timer += delta_time
            if self.spawn_timer >= self.spawn_interval:
                self.spawn_timer = 0
                for _ in range(random.randint(1, 2)):
                    if len(self.confetti_pieces) < self.max_confetti:
                        self._spawn_one()
        
        # === UPDATE ALL PIECES ===
        new_pieces = []
        for piece in self.confetti_pieces:
            # Physics
            piece['age'] += delta_time
            piece['x'] += piece['vx'] * delta_time
            piece['y'] += piece['vy'] * delta_time
            piece['vy'] += self.GRAVITY * delta_time
            piece['rotation'] += piece['spin'] * delta_time
            piece['scale'] = max(0.3, 1.0 - (piece['age'] / piece['lifetime']) * 0.7)
            
            # Render
            img = self.confetti_images[piece['img_idx']]
            img.remove_flag(lv.obj.FLAG.HIDDEN)
            img.set_pos(int(piece['x']), int(piece['y']))
            img.set_rotation(int(piece['rotation'] * 10))
            orig = img.get_width()
            if orig >= 64:
                img.set_scale(int(256 * piece['scale'] / 1.5))
            elif orig < 32:
                img.set_scale(int(256 * piece['scale'] * 1.5))
            else:
                img.set_scale(int(256 * piece['scale']))
            
            # Death check
            dead = (
                piece['x'] < -60 or piece['x'] > self.screen_width + 60 or
                piece['y'] > self.screen_height + 60 or
                piece['age'] > piece['lifetime']
            )
            
            if dead:
                img.add_flag(lv.obj.FLAG.HIDDEN)
                self.used_img_indices.discard(piece['img_idx'])
            else:
                new_pieces.append(piece)
        
        self.confetti_pieces = new_pieces
        
        # Full stop when empty and paused
        if not self.confetti_pieces and not self.is_running:
            print("Confetti finished")
            mpos.ui.task_handler.remove_event_cb(self._update_frame)
    
    def _spawn_one(self):
        """Spawn a single confetti piece."""
        if not self.is_running:
            return
        
        # Find a free image slot
        for idx, img in enumerate(self.confetti_images):
            if img.has_flag(lv.obj.FLAG.HIDDEN) and idx not in self.used_img_indices:
                break
        else:
            return  # No free slot
        
        piece = {
            'img_idx': idx,
            'x': random.uniform(-50, self.screen_width + 50),
            'y': random.uniform(50, 100),  # Start above screen
            'vx': random.uniform(-80, 80),
            'vy': random.uniform(-150, 0),
            'spin': random.uniform(-500, 500),
            'age': 0.0,
            'lifetime': random.uniform(5.0, 10.0),  # Long enough to fill 10s
            'rotation': random.uniform(0, 360),
            'scale': 1.0
        }
        self.confetti_pieces.append(piece)
        self.used_img_indices.add(idx)
