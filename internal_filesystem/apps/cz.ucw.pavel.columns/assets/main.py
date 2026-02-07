import time
import random

"""
bugs:
[x] does not explode on diagonal

should blink explosions

explodes while moving?

explosions should work in series

movement should be immediate

/ vlevo dole nezmizi

chce to skore

<> umozny pohyb do obsazene oblasti

"""

from mpos import Activity

try:
    import lvgl as lv
except ImportError:
    pass


class Main(Activity):

    COLS = 6
    ROWS = 12

    COLORS = [
        0xE74C3C,  # red
        0xF1C40F,  # yellow
        0x2ECC71,  # green
        0x3498DB,  # blue
        0x9B59B6,  # purple
    ]

    EMPTY = -1

    FALL_INTERVAL = 600  # ms

    def __init__(self):
        super().__init__()
        self.board = [[self.EMPTY for _ in range(self.COLS)] for _ in range(self.ROWS)]
        self.cells = []

        self.active_col = self.COLS // 2
        self.active_row = -3
        self.active_colors = []

        self.timer = None
        self.animating = False

    # ---------------------------------------------------------------------

    def onCreate(self):
        self.screen = lv.obj()
        self.screen.remove_flag(lv.obj.FLAG.SCROLLABLE)

        d = lv.display_get_default()
        self.SCREEN_WIDTH = d.get_horizontal_resolution()
        self.SCREEN_HEIGHT = d.get_vertical_resolution()

        self.CELL = min(
            self.SCREEN_WIDTH // self.COLS,
            self.SCREEN_HEIGHT // self.ROWS
        )

        board_x = (self.SCREEN_WIDTH - self.CELL * self.COLS) // 2
        board_y = (self.SCREEN_HEIGHT - self.CELL * self.ROWS) // 2

        for r in range(self.ROWS):
            row = []
            for c in range(self.COLS):
                o = lv.obj(self.screen)
                o.set_size(self.CELL - 2, self.CELL - 2)
                o.set_pos(
                    board_x + c * self.CELL + 1,
                    board_y + r * self.CELL + 1
                )
                o.set_style_radius(4, 0)
                o.set_style_bg_color(lv.color_hex(0x1C2833), 0)
                o.set_style_border_width(1, 0)
                row.append(o)
            self.cells.append(row)

        # Make screen focusable for keyboard input
        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(self.screen)

        self.screen.add_event_cb(self.on_touch, lv.EVENT.CLICKED, None)
        self.screen.add_event_cb(self.on_key, lv.EVENT.KEY, None)
        
        self.setContentView(self.screen)

        self.spawn_piece()

    # ---------------------------------------------------------------------

    def onResume(self, screen):
        self.timer = lv.timer_create(self.tick, self.FALL_INTERVAL, None)

    def onPause(self, screen):
        if self.timer:
            self.timer.delete()
            self.timer = None

    # ---------------------------------------------------------------------

    def spawn_piece(self):
        self.active_col = self.COLS // 2
        self.active_row = -3
        self.active_colors = [random.randrange(len(self.COLORS)) for _ in range(3)]

    def tick(self, t):
        if self.can_fall():
            self.active_row += 1
        else:
            self.lock_piece()
            self.clear_matches()
            self.spawn_piece()

        self.redraw()

    # ---------------------------------------------------------------------

    def can_fall(self):
        for i in range(3):
            r = self.active_row + i + 1
            c = self.active_col
            if r >= self.ROWS:
                return False
            if r >= 0 and self.board[r][c] != self.EMPTY:
                return False
        return True

    def lock_piece(self):
        for i in range(3):
            r = self.active_row + i
            if r >= 0:
                self.board[r][self.active_col] = self.active_colors[i]

    # ---------------------------------------------------------------------

    def clear_matches(self):
        to_clear = set()
        score = 0

        for r in range(self.ROWS):
            for c in range(self.COLS):
                color = self.board[r][c]
                if color == self.EMPTY:
                    continue

                # horizontal
                if c <= self.COLS - 3:
                    if all(self.board[r][c + i] == color for i in range(3)):
                        for i in range(3):
                            to_clear.add((r, c + i))
                            score += 1

                # vertical
                if r <= self.ROWS - 3:
                    if all(self.board[r + i][c] == color for i in range(3)):
                        for i in range(3):
                            to_clear.add((r + i, c))
                            score += 1

                # diagonal \
                if r <= self.ROWS - 3 and c <= self.COLS - 3:
                    if all(self.board[r + i][c + i] == color for i in range(3)):
                        for i in range(3):
                            to_clear.add((r + i, c + i))
                            score += 1

                # diagonal /
                if r <= self.ROWS - 3 and c > 2:
                    if all(self.board[r + i][c - i] == color for i in range(3)):
                        for i in range(3):
                            to_clear.add((r + i, c - i))
                            score += 1
                            
        if not to_clear:
            return

        print("Score: ", score)
        for r, c in to_clear:
            self.board[r][c] = self.EMPTY

        self.redraw()
        time.sleep(.5)
        self.apply_gravity()
        self.redraw()
        time.sleep(.5)
        self.clear_matches()
        self.redraw()

    def apply_gravity(self):
        for c in range(self.COLS):
            stack = [self.board[r][c] for r in range(self.ROWS) if self.board[r][c] != self.EMPTY]
            for r in range(self.ROWS):
                self.board[r][c] = self.EMPTY
            for i, v in enumerate(reversed(stack)):
                self.board[self.ROWS - 1 - i][c] = v

    # ---------------------------------------------------------------------

    def redraw(self):
        # draw board
        for r in range(self.ROWS):
            for c in range(self.COLS):
                v = self.board[r][c]
                if v == self.EMPTY:
                    self.cells[r][c].set_style_bg_color(lv.color_hex(0x1C2833), 0)
                else:
                    self.cells[r][c].set_style_bg_color(
                        lv.color_hex(self.COLORS[v]), 0
                    )

        # draw active piece
        for i in range(3):
            r = self.active_row + i
            if r >= 0 and r < self.ROWS:
                self.cells[r][self.active_col].set_style_bg_color(
                    lv.color_hex(self.COLORS[self.active_colors[i]]), 0
                )

    # ---------------------------------------------------------------------

    def on_touch(self, e):
        print("Touch event")
        p = lv.indev_get_act().get_point()
        x = p.x

        if x < self.SCREEN_WIDTH // 3:
            self.move(-1)
        elif x > self.SCREEN_WIDTH * 2 // 3:
            self.move(1)
        else:
            self.rotate()

    def on_key(self, event):
        """Handle keyboard input"""
        print("Keyboard event")
        key = event.get_key()
        if key == ord("a"):
            self.move(-1)
            return
        if key == ord("w"):
            self.rotate()
            return
        if key == ord("d"):
            self.move(1)
            return
        if key == ord("s"):
            self.tick(0)
            return
        
        #if key == lv.KEY.ENTER or key == lv.KEY.UP or key == ord("A") or key == ord("a"):
        print(f"on_key: unhandled key {key}")

    def move(self, dx):
        nc = self.active_col + dx
        if 0 <= nc < self.COLS:
            self.active_col = nc
        self.redraw()

    def rotate(self):
        self.active_colors = self.active_colors[-1:] + self.active_colors[:-1]
        self.redraw()

