"""The touch map for Duke Nukem 3D.

The game frame is 320x200 and the picture is not rotated (the panel is
landscape), so the zones are simple halves: the left thumb is the walking and
turning stick, the right thumb gets a 2x3 pad of action buttons.

    left half              right half
    +-------------+        +------+------+
    |             |        |  X   |  Y   |
    |   WALK/TURN |        +------+------+
    |             |        |  A   |  B   |
    |             |        +------+------+
    +-------------+        |START | MENU |
                           +------+------+

Every finger keeps its own state, so the left thumb can hold a direction while
the right one fires. The keys are the small protocol in duke_keys.h, not SDL
keycodes (the host's queue carries one byte per press).
"""

# Duke key protocol; keep in step with c_mpos/duke3d/core/duke_keys.h.
KEY_LEFT = 1
KEY_RIGHT = 2
KEY_UP = 3
KEY_DOWN = 4
KEY_FIRE = 5
KEY_JUMP = 6
KEY_CROUCH = 7
KEY_USE = 8
KEY_MENU = 9
KEY_WEAPON = 10
KEY_ENTER = 11
KEY_MAP = 12

# Hit areas, in the engine's own 320x200 frame.
STICK_WIDTH = 160
PAD_LEFT = 168
PAD_RIGHT = 312
PAD_TOP = 12
PAD_BOTTOM = 196
COLUMN_SPLIT = (PAD_LEFT + PAD_RIGHT) // 2
ROW_HEIGHT = (PAD_BOTTOM - PAD_TOP) // 3
STICK_DEADZONE = 7

# The action each cell sends. A tap (press then release) for the menu keys, a
# hold for the action keys.
BUTTONS = (
    # (label, column, row, key, hold)
    ("X", 0, 0, KEY_CROUCH, True),
    ("Y", 1, 0, KEY_USE, True),
    ("A", 0, 1, KEY_FIRE, True),
    ("B", 1, 1, KEY_JUMP, True),
    ("START", 0, 2, KEY_MENU, False),
    ("MENU", 1, 2, KEY_WEAPON, False),
)


def button_rect(column, row):
    """(x, y, width, height) of a pad cell in the engine's frame."""
    x0 = PAD_LEFT if column == 0 else COLUMN_SPLIT
    x1 = COLUMN_SPLIT if column == 0 else PAD_RIGHT
    y0 = PAD_TOP + row * ROW_HEIGHT
    return x0, y0, x1 - x0, ROW_HEIGHT


class DukeTouch:
    """Fingers -> engine keys, with one owner per stick direction and button."""

    def __init__(self, send):
        self._send = send
        self._fingers = {}
        self._owners = {}
        self.last = None

    def pressed(self, finger, x, y):
        state = self._fingers.get(finger)
        if state is None:
            state = self._fingers[finger] = {}
        if x < STICK_WIDTH:
            if not self._claim("stick", finger):
                return None
            state.update(kind="stick", anchor=(x, y), x=0, y=0)
            self.last = "stick"
            return "stick"
        for label, column, row, key, hold in BUTTONS:
            x0, y0, width, height = button_rect(column, row)
            if x0 <= x < x0 + width and y0 <= y < y0 + height:
                if not self._claim(label, finger):
                    return None
                state.update(kind="button", key=key, hold=hold, x=0, y=0)
                if hold:
                    self._send(key, True)
                else:
                    self._send(key, True)
                    self._send(key, False)
                self.last = label
                return label
        return None

    def moving(self, finger, x, y):
        state = self._fingers.get(finger)
        if state is None or state.get("kind") != "stick":
            return
        ax, ay = state["anchor"]
        horizontal = 0
        if x < ax - STICK_DEADZONE:
            horizontal = KEY_LEFT
        elif x > ax + STICK_DEADZONE:
            horizontal = KEY_RIGHT
        vertical = 0
        if y < ay - STICK_DEADZONE:
            vertical = KEY_UP
        elif y > ay + STICK_DEADZONE:
            vertical = KEY_DOWN
        for old in (state.get("x"), state.get("y")):
            if old and old != horizontal and old != vertical:
                self._send(old, False)
        if horizontal and horizontal != state.get("x"):
            self._send(horizontal, True)
        if vertical and vertical != state.get("y"):
            self._send(vertical, True)
        state["x"] = horizontal
        state["y"] = vertical

    def released(self, finger):
        state = self._fingers.pop(finger, None)
        if state is None:
            return
        if state.get("kind") == "stick":
            for code in (state.get("x"), state.get("y")):
                if code:
                    self._send(code, False)
        elif state.get("hold"):
            self._send(state["key"], False)
        for name, owner in list(self._owners.items()):
            if owner == finger:
                del self._owners[name]

    def release_all(self):
        for finger in list(self._fingers):
            self.released(finger)
        self._fingers = {}
        self._owners = {}

    def _claim(self, name, finger):
        owner = self._owners.get(name)
        if owner is not None and owner != finger:
            return False
        self._owners[name] = finger
        return True
