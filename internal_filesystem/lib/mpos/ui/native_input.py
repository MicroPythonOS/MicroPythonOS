"""Input helpers for native-game activities.

Both patterns exist because the same game has to work on a keyboard, a touch
panel and a badge keypad, and the events those produce differ in one important
way: a keypad reports presses (and repeats) but **no releases**, while a
pointer reports both edges. A game that wants "hold left to turn" therefore
needs two different rules for the same key, which is what ``KeyHolds`` encodes.

``ThumbZones`` is the handheld layout: a joystick anchored under the left thumb
and action bands under the right. The zones are in the *game's* frame, not the
panel's, so they still work when the engine rotated the picture for a portrait
panel - see ``NativeActivity.to_game()``. Every finger keeps its own state, so a
left thumb can hold a direction while the right thumb fires.

``TouchFingers`` is what makes that possible on a panel that reports more than
one point: LVGL's pointer device only ever shows one of them, so a game that
wants both thumbs reads the driver's own points instead.
"""

import time

from .multitouch import (
    MultiTouchGesture, find_touch_indev, read_touches)

# A keypad press is released after this long unless the input repeats it.
HOLD_MS = 180
# The shortest time a key may stay down when the hardware reports its real
# state. A tap has to outlive one engine tic or the engine drains the press and
# the release before it builds the tic's input, so a very quick tap would do
# nothing. One frame is ~50 ms at Doom's measured rate; 60 ms covers a tic at
# the 35 fps the loop asks for.
MIN_HOLD_MS = 60
# A pointer that lands on the joystick and lifts within this window has not
# dragged anywhere; a caller can use that as a tap.
TAP_MS = 450
# How far a finger may move between two polls and still be the same finger.
# The GT911 and FT6x36 drivers report their slot number, so this only applies
# to a driver that reports no point number at all; a poll is one frame
# (28-33 ms) and a thumb covers a few tens of pixels in that time.
MATCH_DISTANCE = 60


class KeyHolds:
    """Presses with lifetimes, for engines that want both edges.

    ``send(code, pressed)`` is the app's key sink. A key is either *held* (a
    pointer is still down) or *timed* (a keypad press that has to be released
    after a deadline because no release will ever arrive). LVGL never delivers
    a key release, so the deadline is what a keypad-only board has.

    ``source`` is the escape hatch from timers: a callable returning the keys
    the hardware says are down right now, or None when no device can report it
    (``InputManager.held_keys``). A held key that carries its physical key as
    ``source_key`` is then refreshed while it is in that container and released
    one frame after it leaves, instead of living on a 180 ms deadline that ends
    before the keypad's first repeat arrives.
    """

    def __init__(self, send, hold_ms=HOLD_MS, source=None):
        self._send = send
        self.hold_ms = hold_ms
        self.min_hold_ms = MIN_HOLD_MS
        self.source = source
        self._held = {}

    def held(self):
        return self._held

    def is_held(self, code):
        return code in self._held

    def hold(self, code, source_key=None):
        """Press for ``hold_ms`` unless refreshed: a keypad reports presses only.

        ``source_key`` is the key as the hardware reports it, when that differs
        from the engine code (``ord("B")`` fires, ``KEY_FIRE`` is the engine's
        name for it). It is what :attr:`source` is asked about.
        """
        entry = self._held.get(code)
        now = time.ticks_ms()
        deadline = time.ticks_add(now, self.hold_ms)
        if entry is None:
            self._send(code, True)
            self._held[code] = [deadline, source_key, now]
        else:
            entry[0] = deadline
            if source_key is not None:
                entry[1] = source_key

    def press(self, code):
        """Press and keep down until :meth:`release`: a pointer reports both edges."""
        if code not in self._held:
            self._send(code, True)
        self._held[code] = [None, None, time.ticks_ms()]

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
        down = self.source() if self.source is not None else None
        for code, entry in list(self._held.items()):
            deadline, source_key, pressed_at = entry
            if source_key is not None and down is not None:
                if source_key in down:
                    entry[0] = time.ticks_add(now, self.hold_ms)
                    continue
                # The hardware says it is up. Keep it just long enough for an
                # engine tic to see it, then let the deadline below release it.
                deadline = time.ticks_add(pressed_at, self.min_hold_ms)
                entry[0] = deadline
                if time.ticks_diff(now, deadline) < 0:
                    continue
            if deadline is not None and time.ticks_diff(now, deadline) >= 0:
                self._send(code, False)
                del self._held[code]


class TouchFingers:
    """Every finger a multi-point panel reports, as press/move/release events.

    LVGL's pointer device is single-point on purpose: when a second finger
    lands, the driver reports the whole panel as released so that a pinch
    cannot click the widget under it. That is the right rule for the UI, but it
    means a game cannot wait for LVGL events if it wants two thumbs at once.
    This reads the driver's own points instead.

    ``poll()`` returns ``[(finger, phase, x, y), ...]`` where the phase is
    ``PRESSED``, ``MOVING`` or ``RELEASED`` and the point is in logical panel
    coordinates. A finger number stays the same for as long as the finger is
    down, which is what lets a caller keep one control state per thumb.
    """

    PRESSED = "pressed"
    MOVING = "moving"
    RELEASED = "released"

    def __init__(self, indev=None, match_distance=MATCH_DISTANCE):
        self.indev = indev if indev is not None else find_touch_indev()
        self.match_distance = match_distance
        self._down = {}
        self._next_finger = 0

    @property
    def available(self):
        """True when the panel can report more than one point."""
        return self.indev is not None

    def reset(self):
        """Forget the fingers that were down; the next poll starts clean."""
        self._down = {}
        self._next_finger = 0

    def poll(self, points=None):
        if self.indev is None:
            return []
        if points is None:
            points = read_touches(self.indev)

        events = []
        free = dict(self._down)
        down = {}
        for point_id, x, y in points:
            if point_id is not None:
                finger = point_id
                previous = self._down.get(finger)
                free.pop(finger, None)
            else:
                finger = self._nearest(free, x, y)
                previous = None
                if finger is not None:
                    previous = free.pop(finger)
            if finger is None:
                # A number that is neither down nor being released in this
                # poll, so the press and its release never collide.
                finger = self._allocate(down, free)
            if previous is None:
                events.append((finger, self.PRESSED, x, y))
            elif (x, y) != previous:
                events.append((finger, self.MOVING, x, y))
            down[finger] = (x, y)

        for finger, (x, y) in free.items():
            events.append((finger, self.RELEASED, x, y))

        self._down = down
        return events

    def _nearest(self, free, x, y):
        """The finger already down closest to a point, if it is still the same one."""
        limit = self.match_distance * self.match_distance
        best = None
        best_distance = limit
        for finger, (old_x, old_y) in free.items():
            distance = (x - old_x) * (x - old_x) + (y - old_y) * (y - old_y)
            if distance <= best_distance:
                best = finger
                best_distance = distance
        return best

    def _allocate(self, down, free):
        finger = self._next_finger
        while finger in down or finger in free:
            finger += 1
        self._next_finger = finger + 1
        return finger


class TouchMonitor:
    """One activity's view of a multi-point panel: fingers and gesture.

    Both views come from the same poll, so an app that wants a pinch zoom *and*
    two thumbs does not run two pollers over one device at different rates. An
    activity with a frame loop polls this there (``NativeActivity`` does); one
    without drives it from a timer (Image View does).
    """

    def __init__(self, indev=None):
        self.fingers = TouchFingers(indev)
        self.gesture = MultiTouchGesture(self.fingers.indev)
        self.events = []

    @property
    def indev(self):
        return self.fingers.indev

    @property
    def available(self):
        return self.fingers.available

    def poll(self):
        """Read the panel once; returns the finger events of this poll."""
        if self.fingers.indev is None:
            return []
        points = read_touches(self.fingers.indev)
        self.events = self.fingers.poll(points)
        self.gesture.poll(points)
        return self.events

    def reset(self):
        self.fingers.reset()
        self.gesture.reset()
        self.events = []


class _FingerState:
    """Where one finger is and which direction keys it holds."""

    __slots__ = ("zone", "anchor", "horizontal", "vertical")

    def __init__(self):
        self.zone = None
        self.anchor = None
        self.horizontal = 0
        self.vertical = 0


class ThumbZones:
    """A joystick under the left thumb and three action bands under the right.

    The layout is in the game's frame (``game_width`` x ``game_height``): the
    left half is the joystick, anchored where the thumb lands, and the right
    half is split into menu / use / fire bands. Coordinates go through
    ``NativeActivity.to_game()`` first.

    Each finger keeps its own state, so the two thumbs are independent: the
    left one can hold a direction while the right one holds fire. Only one
    finger can own the joystick (two would fight over the same two keys).

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
        self._fingers = {}
        self._band_fingers = {}

    def zone(self, finger=0):
        """The zone ``finger`` is in, or None."""
        state = self._fingers.get(finger)
        return state.zone if state is not None else None

    def pressed(self, sx, sy, finger=0):
        """A finger went down at a point in the game's frame.

        Returns the zone it landed in, or None when it is ignored (a second
        finger on a zone that already has an owner).
        """
        hold = self.hold
        state = self._fingers.get(finger)
        if state is None:
            state = self._fingers[finger] = _FingerState()
        if sx < self.stick_width:
            if not self._claim("stick", finger):
                state.zone = None
                return None
            # Anchored, not a fixed pad: any touch on the left half starts a
            # turn, so the thumb does not have to hit a target.
            state.zone = "stick"
            state.anchor = (sx, sy)
        elif sy < self.menu_bottom:
            if not self._claim("menu", finger):
                state.zone = None
                return None
            state.zone = "menu"
            hold.tap(self.keys["menu"])
        elif sy < self.use_bottom:
            if not self._claim("use", finger):
                state.zone = None
                return None
            state.zone = "use"
            hold.press(self.keys["use"])
        else:
            if not self._claim("fire", finger):
                state.zone = None
                return None
            state.zone = "fire"
            hold.press(self.keys["fire"])
        return state.zone

    def moving(self, sx, sy, finger=0):
        """A finger moved while down."""
        state = self._fingers.get(finger)
        if state is None or state.zone != "stick" or state.anchor is None:
            return
        horizontal = 0
        if sx < state.anchor[0] - self.deadzone:
            horizontal = self.keys["left"]
        elif sx > state.anchor[0] + self.deadzone:
            horizontal = self.keys["right"]
        vertical = 0
        if sy < state.anchor[1] - self.deadzone:
            vertical = self.keys["up"]
        elif sy > state.anchor[1] + self.deadzone:
            vertical = self.keys["down"]
        self._apply(state, horizontal, vertical)

    def released(self, sx, sy, finger=0):
        """A finger lifted; returns the zone it was in, or None."""
        state = self._fingers.pop(finger, None)
        if state is None:
            return None
        if state.zone is not None and self._band_fingers.get(state.zone) == finger:
            del self._band_fingers[state.zone]
        if state.zone == "stick":
            self._apply(state, 0, 0)
        elif state.zone == "use":
            self.hold.release(self.keys["use"])
        elif state.zone == "fire":
            self.hold.release(self.keys["fire"])
        return state.zone

    def reset(self):
        """Let go of every zone and forget the fingers that owned them."""
        for finger in list(self._fingers):
            self.released(None, None, finger)
        self._fingers = {}
        self._band_fingers = {}

    def _claim(self, zone, finger):
        """Give a zone to the first finger that landed in it.

        Two fingers in one band would otherwise share a key: the first one to
        lift would release it for both. The joystick has the same rule, and it
        is also what stops a second finger from turning the same stick.
        """
        owner = self._band_fingers.get(zone)
        if owner is not None and owner != finger:
            return False
        self._band_fingers[zone] = finger
        return True

    def _apply(self, state, horizontal, vertical):
        hold = self.hold
        for code in (state.horizontal, state.vertical):
            if code and code != horizontal and code != vertical:
                hold.release(code)
        if horizontal and horizontal != state.horizontal:
            hold.press(horizontal)
        if vertical and vertical != state.vertical:
            hold.press(vertical)
        state.horizontal = horizontal
        state.vertical = vertical
