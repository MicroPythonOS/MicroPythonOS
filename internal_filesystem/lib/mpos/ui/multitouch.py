import math


_MIN_PAIR_DISTANCE = 12.0


def display_to_logical(rotation, width, height, x, y):
    rotation = int(rotation)
    if rotation == 1:
        return (width - 1 - y, x)
    if rotation == 2:
        return (width - 1 - x, height - 1 - y)
    if rotation == 3:
        return (y, height - 1 - x)
    return (x, y)


def find_touch_indev():
    """The pointer device that can report every finger, or None.

    Only the drivers that implement ``get_touches()`` know more than one
    point; a single-touch controller (CST816S) and the SDL mouse do not.
    """
    from mpos.ui.input_manager import InputManager

    for indev in InputManager.list_indevs():
        if hasattr(indev, "get_touches"):
            return indev
    return None


def read_touches(indev):
    """Every finger the driver reports, as ``(id, x, y)`` in logical points.

    The drivers already applied the touch calibration and their own startup
    rotation; the display rotation is applied here, which is what puts the
    points in the same space as LVGL's own pointer events.
    """
    if indev is None:
        return []
    rotation = indev.get_rotation()
    width = indev.get_width()
    height = indev.get_height()
    points = []
    for touch in indev.get_touches():
        if len(touch) >= 3:
            point_id = touch[0]
            x = touch[1]
            y = touch[2]
        else:
            point_id = None
            x = touch[0]
            y = touch[1]
        logical_x, logical_y = display_to_logical(rotation, width, height, x, y)
        points.append((point_id, logical_x, logical_y))
    return points


class MultiTouchGesture:
    """Tracks pinch, rotation and pan from a pointer indev with get_touches()."""

    def __init__(self, indev=None):
        self.indev = indev if indev is not None else self.find_indev()
        self.fingers = 0
        self.points = []
        self.scale = 1.0
        self.rotation = 0.0
        self.center = None
        self.delta_x = 0
        self.delta_y = 0
        self.active = False
        self.just_started = False
        self.just_ended = False
        self._previous_center = None
        self._start_distance = 0.0
        self._start_angle = 0.0
        self._pair_ids = None

    @staticmethod
    def find_indev():
        return find_touch_indev()

    def reset(self):
        self.fingers = 0
        self.points = []
        self.scale = 1.0
        self.rotation = 0.0
        self.center = None
        self.delta_x = 0
        self.delta_y = 0
        self.active = False
        self.just_started = False
        self.just_ended = False
        self._previous_center = None
        self._start_distance = 0.0
        self._start_angle = 0.0
        self._pair_ids = None

    def poll(self, points=None):
        self.just_started = False
        self.just_ended = False
        self.delta_x = 0
        self.delta_y = 0

        if self.indev is None:
            return self

        points = (read_touches(self.indev)
                  if points is None else points)
        points = [(point_id, x, y) for point_id, x, y in points]

        previous_fingers = self.fingers
        previous_points = self.points
        self.fingers = len(points)
        self.points = [(x, y) for _, x, y in points]

        if self.fingers >= 2:
            pair = self._select_pair(points, previous_points)
            distance = self._distance(pair)
            if not self.active:
                if distance >= _MIN_PAIR_DISTANCE:
                    self._start(pair, distance)
                    self.just_started = True
            else:
                self._update(pair, distance)
        else:
            if previous_fingers >= 2:
                self.just_ended = True
            self.active = False
            self.scale = 1.0
            self.rotation = 0.0
            self._start_distance = 0.0
            self._pair_ids = None
            if self.fingers == 1:
                self.center = self.points[0]
                if self._previous_center is not None:
                    self.delta_x = self.center[0] - self._previous_center[0]
                    self.delta_y = self.center[1] - self._previous_center[1]
                self._previous_center = self.center
            else:
                self.center = None
                self._previous_center = None

        return self

    def _select_pair(self, points, previous_points):
        # With exactly two points there is one finger per point, so keep each
        # one with where it was last poll. The record numbers cannot do that on
        # a panel that shuffles them (the FT6x36 returns its records in touch
        # order), and following them turns a record swap into a half turn.
        if len(points) == 2 and len(previous_points) == 2:
            direct = self._point_distance(points[0], previous_points[0])
            direct += self._point_distance(points[1], previous_points[1])
            swapped = self._point_distance(points[0], previous_points[1])
            swapped += self._point_distance(points[1], previous_points[0])
            if swapped < direct:
                return [points[1], points[0]]
            return points[:2]
        if self._pair_ids is not None:
            first = None
            second = None
            for point in points:
                if point[0] == self._pair_ids[0]:
                    first = point
                elif point[0] == self._pair_ids[1]:
                    second = point
            if first is not None and second is not None:
                return [first, second]
        if points[0][0] is not None and points[1][0] is not None:
            ordered = sorted(points, key=lambda point: point[0])
            return ordered[:2]
        if len(previous_points) == 2:
            direct = self._point_distance(points[0], previous_points[0])
            direct += self._point_distance(points[1], previous_points[1])
            swapped = self._point_distance(points[0], previous_points[1])
            swapped += self._point_distance(points[1], previous_points[0])
            if swapped < direct:
                return [points[1], points[0]]
        return points[:2]

    @staticmethod
    def _point_distance(point, previous):
        dx = point[1] - previous[0]
        dy = point[2] - previous[1]
        return math.sqrt(dx * dx + dy * dy)

    @staticmethod
    def _distance(pair):
        dx = pair[1][1] - pair[0][1]
        dy = pair[1][2] - pair[0][2]
        return math.sqrt(dx * dx + dy * dy)

    def _start(self, pair, distance):
        x = (pair[0][1] + pair[1][1]) / 2.0
        y = (pair[0][2] + pair[1][2]) / 2.0
        if pair[0][0] is not None and pair[1][0] is not None:
            self._pair_ids = (pair[0][0], pair[1][0])
        else:
            self._pair_ids = None
        self._start_distance = distance
        self._start_angle = math.atan2(
            pair[1][2] - pair[0][2], pair[1][1] - pair[0][1]
        )
        self.center = (x, y)
        self._previous_center = self.center
        self.scale = 1.0
        self.rotation = 0.0
        self.active = True

    def _update(self, pair, distance):
        x = (pair[0][1] + pair[1][1]) / 2.0
        y = (pair[0][2] + pair[1][2]) / 2.0

        if distance >= 1.0 and self._start_distance > 0.0:
            self.scale = distance / self._start_distance

        angle = math.atan2(
            pair[1][2] - pair[0][2], pair[1][1] - pair[0][1]
        )
        rotation = angle - self._start_angle
        while rotation > math.pi:
            rotation -= 2.0 * math.pi
        while rotation < -math.pi:
            rotation += 2.0 * math.pi
        self.rotation = rotation

        if self._previous_center is not None:
            self.delta_x = x - self._previous_center[0]
            self.delta_y = y - self._previous_center[1]

        self.center = (x, y)
        self._previous_center = self.center
