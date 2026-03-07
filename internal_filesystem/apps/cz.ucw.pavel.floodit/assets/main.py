import time
import random

"""
Flood-It game

Fill the entire board with a single color
using the smallest number of moves.

Touch a color button to flood the region
starting from the top-left corner.
"""

from mpos import Activity

try:
    import lvgl as lv
except ImportError:
    pass


class Main(Activity):

    COLS = 10
    ROWS = 10

    COLORS = [
        0xE74C3C,  # red
        0xF1C40F,  # yellow
        0x2ECC71,  # green
        0x3498DB,  # blue
        0x9B59B6,  # purple
        0xE67E22,  # orange
    ]

    def __init__(self):
        super().__init__()

        self.board = []
        self.cells = []

        self.moves = 0

    # ---------------------------------------------------------------------

    def onCreate(self):

        self.screen = lv.obj()
        self.screen.remove_flag(lv.obj.FLAG.SCROLLABLE)

        font = lv.font_montserrat_20

        score = lv.label(self.screen)
        score.align(lv.ALIGN.TOP_LEFT, 5, 25)
        score.set_text("Moves")
        score.set_style_text_font(font, 0)
        self.lb_score = score

        d = lv.display_get_default()
        self.SCREEN_WIDTH = d.get_horizontal_resolution()
        self.SCREEN_HEIGHT = d.get_vertical_resolution()

        # color buttons
        btn_size = 45
        spacing = 5

        self.CELL = min(
            self.SCREEN_WIDTH // (self.COLS + 2),
            (self.SCREEN_HEIGHT - btn_size) // (self.ROWS + 3)
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
                    board_y + r * self.CELL + 1 - btn_size // 2
                )

                o.set_style_radius(4, 0)
                o.set_style_border_width(1, 0)

                row.append(o)

            self.cells.append(row)


        for i, col in enumerate(self.COLORS):

            btn = lv.button(self.screen)
            btn.set_size(btn_size, btn_size)

            btn.align(
                lv.ALIGN.BOTTOM_LEFT,
                5 + i * (btn_size + spacing),
                -5
            )

            btn.set_style_bg_color(lv.color_hex(col), 0)

            btn.add_event_cb(
                lambda e, c=i: self.pick_color(c),
                lv.EVENT.CLICKED,
                None
            )

        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(self.screen)

        self.setContentView(self.screen)

        self.new_game()

    # ---------------------------------------------------------------------

    def new_game(self):

        self.moves = 0
        self.lb_score.set_text("Moves\n0")

        self.board = [
            [random.randrange(len(self.COLORS)) for _ in range(self.COLS)]
            for _ in range(self.ROWS)
        ]

        self.redraw()

    # ---------------------------------------------------------------------

    def pick_color(self, color):

        start_color = self.board[0][0]

        if start_color == color:
            return

        self.flood_fill(start_color, color)

        self.moves += 1
        self.lb_score.set_text("Moves\n%d" % self.moves)

        self.redraw()

        if self.check_win():
            self.win()

    # ---------------------------------------------------------------------

    def flood_fill(self, old, new):

        stack = [(0, 0)]

        while stack:

            r, c = stack.pop()

            if not (0 <= r < self.ROWS and 0 <= c < self.COLS):
                continue

            if self.board[r][c] != old:
                continue

            self.board[r][c] = new

            stack.append((r + 1, c))
            stack.append((r - 1, c))
            stack.append((r, c + 1))
            stack.append((r, c - 1))

    # ---------------------------------------------------------------------

    def check_win(self):

        color = self.board[0][0]

        for r in range(self.ROWS):
            for c in range(self.COLS):
                if self.board[r][c] != color:
                    return False

        return True

    # ---------------------------------------------------------------------

    def win(self):

        label = lv.label(self.screen)
        label.set_text("Finished in %d moves!" % self.moves)
        label.center()

    # ---------------------------------------------------------------------

    def redraw(self):

        for r in range(self.ROWS):
            for c in range(self.COLS):

                v = self.board[r][c]

                self.cells[r][c].set_style_bg_color(
                    lv.color_hex(self.COLORS[v]), 0
                )
