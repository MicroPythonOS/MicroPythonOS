import time
import random

from mpos.apps import Activity
import mpos.ui

try:
    import lvgl as lv
except ImportError:
    pass  # lv is already available as a global in MicroPython OS


class Connect4(Activity):
    # Board dimensions
    COLS = 7
    ROWS = 6

    # Screen layout (dynamically set in onCreate)
    SCREEN_WIDTH = 320
    SCREEN_HEIGHT = 240
    BOARD_TOP = 40
    CELL_SIZE = 30
    PIECE_RADIUS = 12

    # Colors
    COLOR_EMPTY = 0x2C3E50
    COLOR_PLAYER = 0xE74C3C  # Red
    COLOR_COMPUTER = 0xF1C40F  # Yellow
    COLOR_BOARD = 0x3498DB  # Blue
    COLOR_HIGHLIGHT = 0x2ECC71  # Green
    COLOR_WIN = 0x9B59B6  # Purple

    # Game state
    EMPTY = 0
    PLAYER = 1
    COMPUTER = 2

    # Difficulty levels
    DIFFICULTY_EASY = 0
    DIFFICULTY_MEDIUM = 1
    DIFFICULTY_HARD = 2

    def __init__(self):
        super().__init__()
        self.board = [[self.EMPTY for _ in range(self.COLS)] for _ in range(self.ROWS)]
        self.difficulty = self.DIFFICULTY_EASY
        self.game_over = False
        self.winner = None
        self.winning_positions = []
        self.current_player = self.PLAYER
        self.animating = False

        # UI elements
        self.screen = None
        self.pieces = []  # 2D array of LVGL objects
        self.column_buttons = []
        self.status_label = None
        self.difficulty_label = None
        self.last_time = 0

    def onCreate(self):
        self.screen = lv.obj()
        self.screen.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        self.screen.remove_flag(lv.obj.FLAG.SCROLLABLE)

        # Get dynamic screen resolution
        d = lv.display_get_default()
        self.SCREEN_WIDTH = d.get_horizontal_resolution()
        self.SCREEN_HEIGHT = d.get_vertical_resolution()

        # Calculate scaling based on available space
        available_height = self.SCREEN_HEIGHT - 40  # Leave space for bottom bar only
        max_cell_size = min(available_height // self.ROWS, (self.SCREEN_WIDTH - 20) // self.COLS)
        self.CELL_SIZE = max_cell_size
        self.PIECE_RADIUS = int(self.CELL_SIZE * 0.4)
        self.BOARD_TOP = 5

        # Status label (bottom left)
        self.status_label = lv.label(self.screen)
        self.status_label.set_text("Your turn!")
        self.status_label.align(lv.ALIGN.BOTTOM_LEFT, 5, -8)

        # Difficulty button (bottom center)
        difficulty_btn = lv.button(self.screen)
        difficulty_btn.set_size(70, 26)
        difficulty_btn.align(lv.ALIGN.BOTTOM_MID, 0, -5)
        difficulty_btn.add_event_cb(self.cycle_difficulty, lv.EVENT.CLICKED, None)

        self.difficulty_label = lv.label(difficulty_btn)
        self.difficulty_label.set_text("Easy")
        self.difficulty_label.center()

        # New Game button (bottom right)
        new_game_btn = lv.button(self.screen)
        new_game_btn.set_size(70, 26)
        new_game_btn.align(lv.ALIGN.BOTTOM_RIGHT, -5, -5)
        new_game_btn.add_event_cb(lambda e: self.new_game(), lv.EVENT.CLICKED, None)
        new_game_label = lv.label(new_game_btn)
        new_game_label.set_text("New")
        new_game_label.center()

        # Create board background
        board_bg = lv.obj(self.screen)
        board_bg.set_size(self.COLS * self.CELL_SIZE + 10, self.ROWS * self.CELL_SIZE + 10)
        board_bg.set_pos(
            (self.SCREEN_WIDTH - self.COLS * self.CELL_SIZE) // 2 - 5,
            self.BOARD_TOP - 5
        )
        board_bg.set_style_bg_color(lv.color_hex(self.COLOR_BOARD), 0)
        board_bg.set_style_radius(8, 0)
        board_bg.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

        # Create pieces (visual representation)
        board_x = (self.SCREEN_WIDTH - self.COLS * self.CELL_SIZE) // 2
        for row in range(self.ROWS):
            piece_row = []
            for col in range(self.COLS):
                piece = lv.obj(self.screen)
                piece.set_size(self.PIECE_RADIUS * 2, self.PIECE_RADIUS * 2)
                x = board_x + col * self.CELL_SIZE + (self.CELL_SIZE - self.PIECE_RADIUS * 2) // 2
                y = self.BOARD_TOP + row * self.CELL_SIZE + (self.CELL_SIZE - self.PIECE_RADIUS * 2) // 2
                piece.set_pos(x, y)
                piece.set_style_radius(lv.RADIUS_CIRCLE, 0)
                piece.set_style_bg_color(lv.color_hex(self.COLOR_EMPTY), 0)
                piece.set_style_border_width(1, 0)
                piece.set_style_border_color(lv.color_hex(0x1C2833), 0)
                piece.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
                piece_row.append(piece)
            self.pieces.append(piece_row)

        # Create column buttons (invisible clickable areas)
        focusgroup = lv.group_get_default()
        if not focusgroup:
            print("WARNING: could not get default focusgroup")

        for col in range(self.COLS):
            btn = lv.obj(self.screen)
            btn.set_size(self.CELL_SIZE, self.ROWS * self.CELL_SIZE)
            x = board_x + col * self.CELL_SIZE
            btn.set_pos(x, self.BOARD_TOP)
            btn.set_style_bg_opa(0, 0)  # Transparent
            btn.set_style_border_width(0, 0)
            btn.add_flag(lv.obj.FLAG.CLICKABLE)
            btn.add_event_cb(lambda e, c=col: self.on_column_click(c), lv.EVENT.CLICKED, None)
            btn.add_event_cb(lambda e, b=btn: self.focus_column(b), lv.EVENT.FOCUSED, None)
            btn.add_event_cb(lambda e, b=btn: self.defocus_column(b), lv.EVENT.DEFOCUSED, None)

            if focusgroup:
                focusgroup.add_obj(btn)

            self.column_buttons.append(btn)

        self.setContentView(self.screen)

    def onResume(self, screen):
        self.last_time = time.ticks_ms()

    def focus_column(self, column_btn):
        """Highlight column when focused"""
        column_btn.set_style_border_color(lv.theme_get_color_primary(None), lv.PART.MAIN)
        column_btn.set_style_border_width(3, lv.PART.MAIN)

    def defocus_column(self, column_btn):
        """Remove highlight when unfocused"""
        column_btn.set_style_border_width(0, lv.PART.MAIN)

    def cycle_difficulty(self, event):
        if self.animating:
            return
        self.difficulty = (self.difficulty + 1) % 3
        difficulty_names = ["Easy", "Medium", "Hard"]
        self.difficulty_label.set_text(difficulty_names[self.difficulty])
        self.difficulty_label.center()

    def on_column_click(self, col):
        if self.game_over or self.animating or self.current_player != self.PLAYER:
            return

        if self.drop_piece(col, self.PLAYER):
            self.animate_drop(col)

    def drop_piece(self, col, player):
        """Try to drop a piece in the given column. Returns True if successful."""
        # Find the lowest empty row in this column
        for row in range(self.ROWS - 1, -1, -1):
            if self.board[row][col] == self.EMPTY:
                self.board[row][col] = player
                return True
        return False

    def animate_drop(self, col):
        """Animate the piece dropping and then check for win/computer move"""
        self.animating = True

        # Find which row the piece landed in
        row = -1
        player = self.EMPTY
        for r in range(self.ROWS):
            if self.board[r][col] != self.EMPTY:
                row = r
                player = self.board[r][col]
                break

        if row == -1:
            self.animating = False
            return

        # Update the visual
        color = self.COLOR_PLAYER if player == self.PLAYER else self.COLOR_COMPUTER
        self.pieces[row][col].set_style_bg_color(lv.color_hex(color), 0)

        # Check for win or tie
        if self.check_win(row, col):
            self.game_over = True
            self.winner = player
            self.highlight_winning_pieces()
            winner_text = "You win!" if player == self.PLAYER else "Computer wins!"
            self.status_label.set_text(winner_text)
            self.animating = False
            return

        if self.is_board_full():
            self.game_over = True
            self.status_label.set_text("It's a tie!")
            self.animating = False
            return

        # Switch player
        self.current_player = self.COMPUTER if player == self.PLAYER else self.PLAYER

        if self.current_player == self.COMPUTER:
            self.status_label.set_text("Computer thinking...")
            # Delay computer move slightly for better UX
            lv.timer_create(lambda t: self.computer_move(), 500, None).set_repeat_count(1)
        else:
            self.status_label.set_text("Your turn!")
            self.animating = False

    def computer_move(self):
        """Make a computer move based on difficulty"""
        if self.game_over:
            self.animating = False
            return

        if self.difficulty == self.DIFFICULTY_EASY:
            col = self.get_random_move()
        elif self.difficulty == self.DIFFICULTY_MEDIUM:
            col = self.get_medium_move()
        else:  # HARD
            col = self.get_hard_move()

        if col is not None and self.drop_piece(col, self.COMPUTER):
            self.animate_drop(col)
        else:
            self.animating = False

    def get_random_move(self):
        """Easy: Random valid column"""
        valid_cols = [c for c in range(self.COLS) if self.board[0][c] == self.EMPTY]
        return random.choice(valid_cols) if valid_cols else None

    def get_medium_move(self):
        """Medium: Block player wins, try to win, otherwise random"""
        # First, try to win
        for col in range(self.COLS):
            if self.is_valid_move(col):
                row = self.get_next_row(col)
                self.board[row][col] = self.COMPUTER
                if self.check_win(row, col):
                    self.board[row][col] = self.EMPTY
                    return col
                self.board[row][col] = self.EMPTY

        # Second, block player from winning
        for col in range(self.COLS):
            if self.is_valid_move(col):
                row = self.get_next_row(col)
                self.board[row][col] = self.PLAYER
                if self.check_win(row, col):
                    self.board[row][col] = self.EMPTY
                    return col
                self.board[row][col] = self.EMPTY

        # Otherwise, random
        return self.get_random_move()

    def get_hard_move(self):
        """Hard: Minimax algorithm"""
        best_score = -float('inf')
        best_col = None

        for col in range(self.COLS):
            if self.is_valid_move(col):
                row = self.get_next_row(col)
                self.board[row][col] = self.COMPUTER
                score = self.minimax(3, False, -float('inf'), float('inf'))
                self.board[row][col] = self.EMPTY

                if score > best_score:
                    best_score = score
                    best_col = col

        return best_col if best_col is not None else self.get_random_move()

    def minimax(self, depth, is_maximizing, alpha, beta):
        """Minimax with alpha-beta pruning"""
        # Check terminal states
        for row in range(self.ROWS):
            for col in range(self.COLS):
                if self.board[row][col] != self.EMPTY:
                    if self.check_win(row, col):
                        if self.board[row][col] == self.COMPUTER:
                            return 1000
                        else:
                            return -1000

        if self.is_board_full():
            return 0

        if depth == 0:
            return self.evaluate_board()

        if is_maximizing:
            max_score = -float('inf')
            for col in range(self.COLS):
                if self.is_valid_move(col):
                    row = self.get_next_row(col)
                    self.board[row][col] = self.COMPUTER
                    score = self.minimax(depth - 1, False, alpha, beta)
                    self.board[row][col] = self.EMPTY
                    max_score = max(max_score, score)
                    alpha = max(alpha, score)
                    if beta <= alpha:
                        break
            return max_score
        else:
            min_score = float('inf')
            for col in range(self.COLS):
                if self.is_valid_move(col):
                    row = self.get_next_row(col)
                    self.board[row][col] = self.PLAYER
                    score = self.minimax(depth - 1, True, alpha, beta)
                    self.board[row][col] = self.EMPTY
                    min_score = min(min_score, score)
                    beta = min(beta, score)
                    if beta <= alpha:
                        break
            return min_score

    def evaluate_board(self):
        """Heuristic evaluation of board position"""
        score = 0

        # Evaluate all possible windows of 4
        for row in range(self.ROWS):
            for col in range(self.COLS):
                if col <= self.COLS - 4:
                    window = [self.board[row][col + i] for i in range(4)]
                    score += self.evaluate_window(window)

                if row <= self.ROWS - 4:
                    window = [self.board[row + i][col] for i in range(4)]
                    score += self.evaluate_window(window)

                if row <= self.ROWS - 4 and col <= self.COLS - 4:
                    window = [self.board[row + i][col + i] for i in range(4)]
                    score += self.evaluate_window(window)

                if row >= 3 and col <= self.COLS - 4:
                    window = [self.board[row - i][col + i] for i in range(4)]
                    score += self.evaluate_window(window)

        return score

    def evaluate_window(self, window):
        """Evaluate a window of 4 positions"""
        score = 0
        computer_count = window.count(self.COMPUTER)
        player_count = window.count(self.PLAYER)
        empty_count = window.count(self.EMPTY)

        if computer_count == 3 and empty_count == 1:
            score += 5
        elif computer_count == 2 and empty_count == 2:
            score += 2

        if player_count == 3 and empty_count == 1:
            score -= 4

        return score

    def is_valid_move(self, col):
        """Check if a column has space"""
        return self.board[0][col] == self.EMPTY

    def get_next_row(self, col):
        """Get the row where a piece would land in this column"""
        for row in range(self.ROWS - 1, -1, -1):
            if self.board[row][col] == self.EMPTY:
                return row
        return -1

    def check_win(self, row, col):
        """Check if the piece at (row, col) creates a winning connection"""
        player = self.board[row][col]
        if player == self.EMPTY:
            return False

        # Check horizontal
        positions = self.check_direction(row, col, 0, 1)
        if len(positions) >= 4:
            self.winning_positions = positions
            return True

        # Check vertical
        positions = self.check_direction(row, col, 1, 0)
        if len(positions) >= 4:
            self.winning_positions = positions
            return True

        # Check diagonal (down-right)
        positions = self.check_direction(row, col, 1, 1)
        if len(positions) >= 4:
            self.winning_positions = positions
            return True

        # Check diagonal (down-left)
        positions = self.check_direction(row, col, 1, -1)
        if len(positions) >= 4:
            self.winning_positions = positions
            return True

        return False

    def check_direction(self, row, col, dr, dc):
        """Count consecutive pieces in a direction (both ways)"""
        player = self.board[row][col]
        positions = [(row, col)]

        # Check positive direction
        r, c = row + dr, col + dc
        while 0 <= r < self.ROWS and 0 <= c < self.COLS and self.board[r][c] == player:
            positions.append((r, c))
            r += dr
            c += dc

        # Check negative direction
        r, c = row - dr, col - dc
        while 0 <= r < self.ROWS and 0 <= c < self.COLS and self.board[r][c] == player:
            positions.append((r, c))
            r -= dr
            c -= dc

        return positions

    def highlight_winning_pieces(self):
        """Highlight the winning pieces"""
        for row, col in self.winning_positions:
            self.pieces[row][col].set_style_bg_color(lv.color_hex(self.COLOR_WIN), 0)
            self.pieces[row][col].set_style_border_width(3, 0)
            self.pieces[row][col].set_style_border_color(lv.color_hex(0xFFFFFF), 0)

    def is_board_full(self):
        """Check if the board is full"""
        return all(self.board[0][col] != self.EMPTY for col in range(self.COLS))

    def new_game(self):
        """Reset the game"""
        self.board = [[self.EMPTY for _ in range(self.COLS)] for _ in range(self.ROWS)]
        self.game_over = False
        self.winner = None
        self.winning_positions = []
        self.current_player = self.PLAYER
        self.animating = False
        self.status_label.set_text("Your turn!")

        # Reset visual pieces
        for row in range(self.ROWS):
            for col in range(self.COLS):
                self.pieces[row][col].set_style_bg_color(lv.color_hex(self.COLOR_EMPTY), 0)
                self.pieces[row][col].set_style_border_width(1, 0)
                self.pieces[row][col].set_style_border_color(lv.color_hex(0x1C2833), 0)
