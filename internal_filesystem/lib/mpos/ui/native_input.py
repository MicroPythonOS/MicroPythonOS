"""Input helpers for native-game activities.

Both patterns exist because the same game has to work on a keyboard, a touch
panel and a badge keypad, and the events those produce differ in one important
way: a keypad reports presses (and repeats) but **no releases**, while a
pointer reports both edges. A game that wants "hold left to turn" therefore
needs two different rules for the same key, which is what ``KeyHolds`` encodes.

``ThumbZones`` is the handheld layout: a joystick anchored under the left thumb
and action bands under the right. The zones are in the *game's* frame, not the
panel's, so they still work when the engine rotated the picture for a portrait
panel - see ``NativeActivity.to_game()``.
"""

import time

# A keypad press is released after this long unless the input repeats it.
HOLD_MS = 180
# A pointer that lands on the joystick and lifts within this window has not
# dragged anywhere; a caller can use that as a tap.
TAP_MS = 450


class KeyHolds:
    """Presses with lifetimes, for engines that want both edges.

    ``send(code, pressed)`` is the app's key sink. A key is either *held* (a
    pointer is still down) or *timed* (a keypad press that has to be released
    after a deadline because no release will ever arrive).
    """

    def __init__(self, send, hold_ms=HOLD_MS):
        self._send = send
        self.hold_ms = hold_ms
        self._held = {}

    def held(self):
        return self._held

    def is_held(self, code):
        return code in self._held

    def hold(self, code):
        """Press for ``hold_ms`` unless refreshed: a keypad reports presses only."""
        if code not in self._held:
            self._send(code, True)
        self._held[code] = time.ticks_add(time.ticks_ms(), self.hold_ms)

    def press(self, code):
        """Press and keep down until :meth:`release`: a pointer reports both edges."""
        if code not in self._held:
            self._send(code, True)
        self._held[code] = None

    def tap(self, code):
        """Press and release at once: an event-driven action (a menu select)."""
        self._send(code, True)
        self._send(code, False)

    def release(self, code):
        if code in self._held:
            self._send(code, False)
            del self._held[code]

    def release_all(self):
        for code in list(self._held):
            self._send(code, False)
        self._held = {}

    def tick(self, now):
        for code, deadline in list(self._held.items()):
            if deadline is not None and time.ticks_diff(now, deadline) >= 0:
                self._send(code, False)
                del self._held[code]


class ThumbZones:
    """A joystick under the left thumb and three action bands under the right.

    The layout is in the game's frame (``game_width`` x ``game_height``): the
    left half is the joystick, anchored where the thumb lands, and the right
    half is split into menu / use / fire bands. Coordinates go through
    ``NativeActivity.to_game()`` first.

    ``keys`` is a dict with ``left``, ``right``, ``up``, ``down``, ``menu``,
    ``use`` and ``fire`` engine key codes.
    """

    STICK_WIDTH = 160
    MENU_BOTTOM = 60
    USE_BOTTOM = 120
    STICK_DEADZONE = 16

    def __init__(self, keys, hold=None, stick_width=STICK_WIDTH,
                 menu_bottom=MENU_BOTTOM, use_bottom=USE_BOTTOM,
                 deadzone=STICK_DEADZONE):
        self.keys = keys
        self.hold = hold
        self.stick_width = stick_width
        self.menu_bottom = menu_bottom
        self.use_bottom = use_bottom
        self.deadzone = deadzone
        self.zone = None
        self.stick = None
        self._stick_h = 0
        self._stick_v = 0

    def pressed(self, sx, sy):
        """The pointer went down at a point in the game's frame."""
        hold = self.hold
        if sx < self.stick_width:
            # Anchored, not a fixed pad: any touch on the left half starts a
            # turn, so the thumb does not have to hit a target.
            self.zone = "stick"
            self.stick = (sx, sy)
            self._apply(0, 0)
        elif sy < self.menu_bottom:
            self.zone = "menu"
            hold.tap(self.keys["menu"])
        elif sy < self.use_bottom:
            self.zone = "use"
            hold.press(self.keys["use"])
        else:
            self.zone = "fire"
            hold.press(self.keys["fire"])

    def moving(self, sx, sy):
        """The pointer moved while down."""
        if self.zone != "stick" or self.stick is None:
            return
        horizontal = 0
        if sx < self.stick[0] - self.deadzone:
            horizontal = self.keys["left"]
        elif sx > self.stick[0] + self.deadzone:
            horizontal = self.keys["right"]
        vertical = 0
        if sy < self.stick[1] - self.deadzone:
            vertical = self.keys["up"]
        elif sy > self.stick[1] + self.deadzone:
            vertical = self.keys["down"]
        self._apply(horizontal, vertical)

    def released(self, sx, sy):
        """The pointer lifted; returns how long it was down (ms) or None."""
        hold = self.hold
        if self.zone == "stick":
            self._apply(0, 0)
            self.stick = None
        elif self.zone == "use":
            hold.release(self.keys["use"])
        elif self.zone == "fire":
            hold.release(self.keys["fire"])
        self.zone = None

    def _apply(self, horizontal, vertical):
        hold = self.hold
        for code in (self._stick_h, self._stick_v):
            if code and code != horizontal and code != vertical:
                hold.release(code)
        if horizontal and horizontal != self._stick_h:
            hold.press(horizontal)
        if vertical and vertical != self._stick_v:
            hold.press(vertical)
        self._stick_h = horizontal
        self._stick_v = vertical
