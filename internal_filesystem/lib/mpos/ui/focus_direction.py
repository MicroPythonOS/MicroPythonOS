import lvgl as lv
import mpos.util


# ---------------------------------------------------------------------------
# Rectangle helpers
# ---------------------------------------------------------------------------

def _get_rect(obj):
    """Return (x1, y1, x2, y2) absolute coords of obj."""
    area = lv.area_t()
    obj.get_coords(area)
    return area.x1, area.y1, area.x2, area.y2


def _rect_center(x1, y1, x2, y2):
    return (x1 + x2) / 2, (y1 + y2) / 2


# ---------------------------------------------------------------------------
# Android FocusFinder algorithm (ported from AOSP FocusFinder.java)
#
# Direction convention (matches the rest of MicroPythonOS):
#   0   = UP
#   90  = RIGHT
#   180 = DOWN
#   270 = LEFT
# ---------------------------------------------------------------------------

UP    = 0
RIGHT = 90
DOWN  = 180
LEFT  = 270


def is_candidate(src, dest, direction):
    """Return True if dest is a valid focus candidate from src in direction.

    Uses edge-overlap checks (no angle/cone). A candidate must be at least
    partially past the source's leading edge in the travel direction AND must
    have its far edge further in that direction than the source's near edge.

    Equivalent to Android's FocusFinder.isCandidate().
    """
    sx1, sy1, sx2, sy2 = src
    dx1, dy1, dx2, dy2 = dest
    if direction == UP:
        return (sy2 > dy2 or sy1 >= dy2) and sy1 > dy1
    if direction == DOWN:
        return (sy1 < dy1 or sy2 <= dy1) and sy2 < dy2
    if direction == LEFT:
        return (sx2 > dx2 or sx1 >= dx2) and sx1 > dx1
    if direction == RIGHT:
        return (sx1 < dx1 or sx2 <= dx1) and sx2 < dx2
    return False


def beams_overlap(src, dest, direction):
    """Return True if src and dest overlap on the axis perpendicular to direction.

    The "beam" is the infinite strip projected in the travel direction,
    bounded by the source's perpendicular edges.
    Equivalent to Android's FocusFinder.beamsOverlap().
    """
    sx1, sy1, sx2, sy2 = src
    dx1, dy1, dx2, dy2 = dest
    if direction in (LEFT, RIGHT):
        # beam is a horizontal band — check vertical overlap
        return dy2 > sy1 and dy1 < sy2
    else:  # UP, DOWN
        # beam is a vertical band — check horizontal overlap
        return dx2 > sx1 and dx1 < sx2


def major_axis_distance(src, dest, direction):
    """Gap between the trailing edge of src and the leading edge of dest, clamped to 0.

    Equivalent to Android's majorAxisDistance (uses max(raw, 0)).
    """
    sx1, sy1, sx2, sy2 = src
    dx1, dy1, dx2, dy2 = dest
    if direction == UP:
        return max(0, sy1 - dy2)
    if direction == DOWN:
        return max(0, dy1 - sy2)
    if direction == LEFT:
        return max(0, sx1 - dx2)
    if direction == RIGHT:
        return max(0, dx1 - sx2)
    return 0


def major_axis_distance_to_far_edge(src, dest, direction):
    """Gap to the far (trailing) edge of dest, clamped to 0.

    Equivalent to Android's majorAxisDistanceToFarEdge.
    """
    sx1, sy1, sx2, sy2 = src
    dx1, dy1, dx2, dy2 = dest
    if direction == UP:
        return max(0, sy1 - dy1)
    if direction == DOWN:
        return max(0, dy2 - sy2)
    if direction == LEFT:
        return max(0, sx1 - dx1)
    if direction == RIGHT:
        return max(0, dx2 - sx2)
    return 0


def minor_axis_distance(src, dest, direction):
    """Center-to-center offset on the axis perpendicular to direction.

    Equivalent to Android's minorAxisDistance.
    """
    sx1, sy1, sx2, sy2 = src
    dx1, dy1, dx2, dy2 = dest
    src_cx, src_cy = _rect_center(sx1, sy1, sx2, sy2)
    dst_cx, dst_cy = _rect_center(dx1, dy1, dx2, dy2)
    if direction in (LEFT, RIGHT):
        return abs(src_cy - dst_cy)
    else:
        return abs(src_cx - dst_cx)


def weighted_distance(major, minor):
    """Score used to rank candidates when beam-status is equal.

    Equivalent to Android's getWeightedDistanceFor().
    The ×13 weight on major axis means forward distance dominates, but
    lateral misalignment (minor axis) breaks ties.
    """
    return 13 * major * major + minor * minor


def _is_to_direction_of(src, dest, direction):
    """Return True if dest is in the general direction from src (loose check)."""
    sx1, sy1, sx2, sy2 = src
    dx1, dy1, dx2, dy2 = dest
    if direction == UP:
        return dy1 < sy1
    if direction == DOWN:
        return dy2 > sy2
    if direction == LEFT:
        return dx1 < sx1
    if direction == RIGHT:
        return dx2 > sx2
    return False


def beam_beats(src, rect1, rect2, direction):
    """Return True if rect1 should beat rect2 purely based on beam membership.

    Equivalent to Android's beamBeats().
    rect1 wins if it is in the beam and rect2 is not — with the additional
    constraint for UP/DOWN that rect1 must be at least as close as rect2's
    far edge (so an out-of-beam widget that is extremely close can still win).
    """
    rect1_in_beam = beams_overlap(src, rect1, direction)
    rect2_in_beam = beams_overlap(src, rect2, direction)

    # rect1 only wins by beam if it IS in beam and rect2 is NOT
    if rect2_in_beam or not rect1_in_beam:
        return False

    # rect2 is not in beam. If rect2 isn't even in the direction, rect1 wins.
    if not _is_to_direction_of(src, rect2, direction):
        return True

    # For LEFT/RIGHT: being in-beam is an absolute win.
    if direction in (LEFT, RIGHT):
        return True

    # For UP/DOWN: in-beam only wins if rect1's near edge is closer than
    # rect2's far edge (prevents an extremely close out-of-beam widget losing).
    return major_axis_distance(src, rect1, direction) < major_axis_distance_to_far_edge(src, rect2, direction)


def is_better_candidate(src, rect1, rect2, direction):
    """Return True if rect1 is a better focus candidate than rect2 from src.

    5-step hierarchy, equivalent to Android's isBetterCandidate().
    """
    if not is_candidate(src, rect1, direction):
        return False
    if not is_candidate(src, rect2, direction):
        return True
    if beam_beats(src, rect1, rect2, direction):
        return True
    if beam_beats(src, rect2, rect1, direction):
        return False
    return (weighted_distance(major_axis_distance(src, rect1, direction),
                              minor_axis_distance(src, rect1, direction))
            < weighted_distance(major_axis_distance(src, rect2, direction),
                                minor_axis_distance(src, rect2, direction)))


# ---------------------------------------------------------------------------
# Focus group traversal
# ---------------------------------------------------------------------------

def _is_on_layer_top(obj):
    """Return True if obj is a descendant of lv.layer_top()."""
    top = lv.layer_top()
    if not top:
        return False
    parent = obj.get_parent()
    while parent is not None:
        if parent is top:
            return True
        parent = parent.get_parent()
    return False


def is_object_in_focus_group(focus_group, obj):
    """Return True if obj is in the focus group, visible, and has no hidden ancestor."""
    if obj is None:
        return False
    ancestor = obj
    while ancestor is not None:
        if ancestor.has_flag(lv.obj.FLAG.HIDDEN):
            return False
        ancestor = ancestor.get_parent()
    for i in range(focus_group.get_obj_count()):
        if focus_group.get_obj_by_index(i) is obj:
            return True
    return False


def _first_focusable_on_layer_top(focus_group):
    """Return the first non-hidden focus-group member that lives on layer_top, or None.

    This drives the modal-overlay behaviour: when layer_top has any focusable
    content (e.g. a confirmation dialog's Yes/No buttons), focus must stay
    there and must be redirected there if it currently lives elsewhere.
    """
    for i in range(focus_group.get_obj_count()):
        obj = focus_group.get_obj_by_index(i)
        if is_object_in_focus_group(focus_group, obj) and _is_on_layer_top(obj):
            return obj
    return None


def find_closest_obj_in_direction(focus_group, current_focused, direction_degrees,
                                   top_layer_active=False, debug=False):
    """Find the best focus target in direction_degrees from current_focused.

    Uses the Android FocusFinder algorithm:
      1. isCandidate — edge-overlap filter (no angular cone)
      2. beamBeats   — in-beam widgets get priority
      3. weightedDistance — tie-break by 13*major² + minor²

    top_layer_active: when True only layer_top candidates are considered;
                      when False only non-layer_top candidates are considered.

    direction_degrees: 0=UP, 90=RIGHT, 180=DOWN, 270=LEFT
    Returns the winning object, or None.
    """
    if not current_focused:
        print("find_closest_obj_in_direction: no focused object")
        return None

    direction = direction_degrees  # alias for readability

    src = _get_rect(current_focused)

    # Seed best_rect as a ghost rect displaced one pixel PAST the source in
    # the opposite direction, so the first real candidate always beats it.
    # (Equivalent to Android's mBestCandidateRect seeding.)
    sx1, sy1, sx2, sy2 = src
    w = sx2 - sx1
    h = sy2 - sy1
    if direction == UP:
        best_rect = (sx1, sy2 + 1, sx2, sy2 + 1 + h)
    elif direction == DOWN:
        best_rect = (sx1, sy1 - 1 - h, sx2, sy1 - 1)
    elif direction == LEFT:
        best_rect = (sx2 + 1, sy1, sx2 + 1 + w, sy2)
    else:  # RIGHT
        best_rect = (sx1 - 1 - w, sy1, sx1 - 1, sy2)

    best_obj = None

    if debug:
        print("find_closest_obj_in_direction: src=" + str(src) + " dir=" + str(direction)
              + " top_layer_active=" + str(top_layer_active))

    def process_object(obj):
        nonlocal best_rect, best_obj

        if obj is None or obj is current_focused:
            return

        # Enforce layer constraint: only consider candidates in the active layer.
        if _is_on_layer_top(obj) != top_layer_active:
            return

        if is_object_in_focus_group(focus_group, obj):
            dest = _get_rect(obj)
            if is_better_candidate(src, dest, best_rect, direction):
                best_rect = dest
                best_obj = obj
                if debug:
                    print("  new best: " + str(dest))
                    mpos.util.print_lvgl_widget(obj)

        for i in range(obj.get_child_count()):
            process_object(obj.get_child(i))

    for i in range(focus_group.get_obj_count()):
        process_object(focus_group.get_obj_by_index(i))

    return best_obj


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def move_focus_direction(angle):
    focus_group = lv.group_get_default()
    if not focus_group:
        print("move_focus_direction: no default focus_group found, returning...")
        return
    current_focused = focus_group.get_focused()
    if not current_focused:
        print("move_focus_direction: nothing is focused, choosing the next thing")
        focus_group.focus_next()
        current_focused = focus_group.get_focused()
    if not current_focused:
        print("move_focus_direction: could not focus on anything, returning...")
        return
    if isinstance(current_focused, lv.keyboard):
        print("focus is on a keyboard, which has its own move_focus_direction: NOT moving")
        return
    if isinstance(current_focused, lv.dropdown) and current_focused.is_open():
        print("focus is on an open dropdown, which has its own move_focus_direction: NOT moving")
        return

    # Modal-overlay handling: if layer_top has any focusable content (e.g. a
    # confirmation dialog), treat it as a modal — constrain all navigation to
    # that layer.  If current focus is still on the normal screen, redirect it
    # to the first overlay widget on the first keypress (Android-style: focus
    # jumps to the dialog on the first directional key, not proactively).
    first_on_top = _first_focusable_on_layer_top(focus_group)
    top_layer_active = first_on_top is not None

    if top_layer_active and not _is_on_layer_top(current_focused):
        print("move_focus_direction: modal overlay present — redirecting focus to layer_top")
        lv.group_focus_obj(first_on_top)
        return

    o = find_closest_obj_in_direction(focus_group, current_focused, angle,
                                      top_layer_active=top_layer_active)
    if o:
        print("move_focus_direction: moving focus to:")
        mpos.util.print_lvgl_widget(o)
        lv.group_focus_obj(o)
