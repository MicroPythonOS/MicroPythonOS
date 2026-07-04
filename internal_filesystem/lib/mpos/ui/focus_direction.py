import logging
import lvgl as lv
import mpos.util

logger = logging.getLogger(__name__)

# Registered buttonmatrix layouts: matrix -> descriptor dict.
# Descriptor has "rows" (list of per-row button-index lists) and
# "buttons" (button-index -> {"row", "col", "width_unit", "text"}).
_MATRIX_LAYOUTS = {}

# Matrix currently being focused programmatically by move_focus_direction.
# Keyboard event handlers can check this to avoid inserting characters when
# focus_direction moves the selection.
_NAVIGATION_SUPPRESS = None


def suppress_keyboard_event(matrix):
    """Return True if `matrix` is currently being focused programmatically."""
    global _NAVIGATION_SUPPRESS
    return _NAVIGATION_SUPPRESS is matrix


# ---------------------------------------------------------------------------
# Buttonmatrix registration
# ---------------------------------------------------------------------------

def register_buttonmatrix(matrix, map_list, ctrl_map=None):
    """Register a buttonmatrix so its buttons are treated as individual focus candidates."""
    buttons = {}
    rows = []
    current_row = []
    btn_idx = 0
    for i, text in enumerate(map_list):
        if text is None:
            break
        if text == "\n":
            rows.append(current_row)
            current_row = []
            continue
        width_unit = ctrl_map[i] & 0xF if ctrl_map and i < len(ctrl_map) else 10
        if width_unit == 0:
            width_unit = 10
        buttons[btn_idx] = {
            "row": len(rows),
            "col": len(current_row),
            "width_unit": width_unit,
            "text": text,
        }
        current_row.append(btn_idx)
        btn_idx += 1
    if current_row:
        rows.append(current_row)
    _MATRIX_LAYOUTS[matrix] = {"matrix": matrix, "rows": rows, "buttons": buttons}


def unregister_buttonmatrix(matrix):
    """Remove a previously registered buttonmatrix from focus-direction handling."""
    _MATRIX_LAYOUTS.pop(matrix, None)


update_buttonmatrix = register_buttonmatrix


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


def _matrix_layout(matrix):
    return _MATRIX_LAYOUTS.get(matrix)


def _matrix_button_visible(matrix, btn_idx, layout):
    """Return True if a buttonmatrix button is a valid focus candidate."""
    text = layout["buttons"].get(btn_idx, {}).get("text")
    if text is None or text == "\n":
        return False
    return True


def _matrix_button_rect(matrix, btn_idx, layout):
    """Return absolute (x1, y1, x2, y2) coordinates for a buttonmatrix button."""
    mx1, my1, mx2, my2 = _get_rect(matrix)
    total_w = mx2 - mx1 + 1
    total_h = my2 - my1 + 1
    btn = layout["buttons"][btn_idx]
    row = btn["row"]
    col = btn["col"]
    rows = layout["rows"]
    num_rows = len(rows)
    if num_rows == 0:
        return mx1, my1, mx2, my2

    pad_left = matrix.get_style_pad_left(lv.PART.MAIN)
    pad_right = matrix.get_style_pad_right(lv.PART.MAIN)
    pad_top = matrix.get_style_pad_top(lv.PART.MAIN)
    pad_bottom = matrix.get_style_pad_bottom(lv.PART.MAIN)
    pad_row = matrix.get_style_pad_row(lv.PART.MAIN)
    pad_col = matrix.get_style_pad_column(lv.PART.MAIN)

    content_h = total_h - pad_top - pad_bottom - (num_rows - 1) * pad_row
    if content_h < 1:
        content_h = 1
    row_h = content_h // num_rows
    if row_h < 1:
        row_h = 1
    y = my1 + pad_top + row * (row_h + pad_row)

    row_btns = rows[row]
    total_units = sum(layout["buttons"][b]["width_unit"] for b in row_btns) or 1
    content_w = total_w - pad_left - pad_right - (len(row_btns) - 1) * pad_col
    if content_w < 1:
        content_w = 1

    x = mx1 + pad_left
    for b in row_btns:
        width_unit = layout["buttons"][b]["width_unit"]
        btn_w = int(content_w * width_unit / total_units)
        if b == btn_idx:
            return x, y, x + btn_w - 1, y + row_h - 1
        x += btn_w + pad_col
    return mx1, my1, mx2, my2


def get_matrix_button_rect(matrix, btn_idx):
    """Return absolute (x1, y1, x2, y2) of matrix button `btn_idx`, or None."""
    layout = _matrix_layout(matrix)
    if layout is None or btn_idx not in layout["buttons"]:
        return None
    try:
        return _matrix_button_rect(matrix, btn_idx, layout)
    except Exception:
        return None


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


def _point_rect_dist_sq(x, y, rect):
    """Return squared distance from (x, y) to the closest point on a rectangle.

    This gives 0 when (x, y) lies inside the rectangle, and penalises only the
    actual gap to the nearest edge — much better than centre distance for
    widgets with very different widths (e.g. wide mode-switch keys).
    """
    x1, y1, x2, y2 = rect
    dx = 0
    if x < x1:
        dx = x1 - x
    elif x > x2:
        dx = x - x2
    dy = 0
    if y < y1:
        dy = y1 - y
    elif y > y2:
        dy = y - y2
    return dx * dx + dy * dy


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

    Registered buttonmatrices are expanded into individual button rectangles.

    top_layer_active: when True only layer_top candidates are considered;
                      when False only non-layer_top candidates are considered.

    direction_degrees: 0=UP, 90=RIGHT, 180=DOWN, 270=LEFT
    Returns (target_obj, target_button_idx) where target_button_idx is set
    for matrix-button targets and None for normal objects.
    """
    if not current_focused:
        logger.warning("find_closest_obj_in_direction: no focused object")
        return None, None

    direction = direction_degrees  # alias for readability

    source_obj = current_focused
    source_btn = None
    source_layout = _matrix_layout(source_obj)
    if source_layout is not None:
        try:
            cur = source_obj.get_selected_button()
            if cur is not None and cur < 0xFFFF:
                source_btn = cur
        except Exception:
            pass

    if source_btn is not None:
        src = _matrix_button_rect(source_obj, source_btn, source_layout)
    else:
        src = _get_rect(source_obj)

    # Seed best_rect as a ghost rect displaced one pixel PAST the source in
    # the opposite direction, so the first real candidate always beats it.
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

    best_target = (None, None)

    if debug:
        if __debug__: logger.debug("find_closest_obj_in_direction: src=%s dir=%s top_layer_active=%s", src, direction, top_layer_active)

    def consider(rect, obj, btn_idx):
        nonlocal best_rect, best_target
        if rect is None or obj is None:
            return
        if is_better_candidate(src, rect, best_rect, direction):
            best_rect = rect
            best_target = (obj, btn_idx)

    def process_object(obj):
        if obj is None:
            return

        # Enforce layer constraint: only consider candidates in the active layer.
        if _is_on_layer_top(obj) != top_layer_active:
            return

        layout = _matrix_layout(obj)
        if layout is not None:
            if not is_object_in_focus_group(focus_group, obj):
                return
            # Expand matrix into individual button candidates; do not recurse
            # into its label children.
            for btn_idx in layout["buttons"]:
                if obj is source_obj and btn_idx == source_btn:
                    continue
                if not _matrix_button_visible(obj, btn_idx, layout):
                    continue
                consider(_matrix_button_rect(obj, btn_idx, layout), obj, btn_idx)
            return

        if obj is not source_obj and is_object_in_focus_group(focus_group, obj):
            consider(_get_rect(obj), obj, None)

        for i in range(obj.get_child_count()):
            process_object(obj.get_child(i))

    for i in range(focus_group.get_obj_count()):
        process_object(focus_group.get_obj_by_index(i))

    return best_target



# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _focus_matrix_button(matrix, btn_idx, focus_group):
    """Focus a specific button inside a registered buttonmatrix."""
    global _NAVIGATION_SUPPRESS
    if focus_group.get_focused() is not matrix:
        lv.group_focus_obj(matrix)
    _NAVIGATION_SUPPRESS = matrix
    try:
        matrix.set_selected_button(btn_idx)
    except Exception:
        pass
    finally:
        _NAVIGATION_SUPPRESS = None


_MATRIX_KEYS = {UP: lv.KEY.UP, RIGHT: lv.KEY.RIGHT, DOWN: lv.KEY.DOWN, LEFT: lv.KEY.LEFT}


def _navigate_matrix_internal(matrix, focus_group, direction_degrees):
    """Let LVGL's default buttonmatrix handler move the selection.

    Returns True if a key was sent; the caller still uses find_closest_obj_in_direction
    when there is no neighbour inside the matrix.
    """
    key = _MATRIX_KEYS.get(direction_degrees)
    if key is None:
        return False
    if focus_group.get_focused() is not matrix:
        lv.group_focus_obj(matrix)
    global _NAVIGATION_SUPPRESS
    _NAVIGATION_SUPPRESS = matrix
    try:
        focus_group.send_data(key)
    except Exception:
        return False
    finally:
        _NAVIGATION_SUPPRESS = None
    return True



def focus_coordinates(x, y):
    """Move focus to the focus-group object closest to screen coordinate (x, y).

    This is useful when a widget is rebuilt (e.g. switching keyboard layouts)
    and focus should stay near the same on-screen position rather than jumping
    to the first group member.
    """
    from .focus import enable_focus_borders
    enable_focus_borders()
    focus_group = lv.group_get_default()
    if not focus_group:
        logger.warning("focus_coordinates: no default focus_group found, returning...")
        return

    # Keep modal-overlay behaviour consistent with move_focus_direction().
    first_on_top = _first_focusable_on_layer_top(focus_group)
    top_layer_active = first_on_top is not None

    best = None
    best_btn = None
    best_dist = None

    for i in range(focus_group.get_obj_count()):
        obj = focus_group.get_obj_by_index(i)
        if not is_object_in_focus_group(focus_group, obj):
            continue
        if _is_on_layer_top(obj) != top_layer_active:
            continue

        layout = _matrix_layout(obj)
        if layout is not None:
            if not is_object_in_focus_group(focus_group, obj):
                continue
            for btn_idx in layout["buttons"]:
                if not _matrix_button_visible(obj, btn_idx, layout):
                    continue
                rect = _matrix_button_rect(obj, btn_idx, layout)
                d = _point_rect_dist_sq(x, y, rect)
                if best_dist is None or d < best_dist:
                    best_dist = d
                    best = obj
                    best_btn = btn_idx
            continue

        rect = _get_rect(obj)
        d = _point_rect_dist_sq(x, y, rect)
        if best_dist is None or d < best_dist:
            best_dist = d
            best = obj
            best_btn = None

    if best is None:
        return

    if best_btn is not None:
        _focus_matrix_button(best, best_btn, focus_group)
    else:
        lv.group_focus_obj(best)


def move_focus_direction(angle):
    # First directional navigation enables focus borders (see mpos.ui.focus):
    # they stay hidden during touch-only use and appear once the joystick/keypad
    # is actually used, so the highlight follows real navigation rather than
    # device capability.
    from .focus import enable_focus_borders
    enable_focus_borders()
    focus_group = lv.group_get_default()
    if not focus_group:
        logger.warning("move_focus_direction: no default focus_group found, returning...")
        return
    current_focused = focus_group.get_focused()
    if not current_focused:
        if __debug__: logger.debug("move_focus_direction: nothing is focused, choosing the next thing")
        focus_group.focus_next()
        current_focused = focus_group.get_focused()
    if not current_focused:
        logger.warning("move_focus_direction: could not focus on anything, returning...")
        return
    if isinstance(current_focused, lv.dropdown) and current_focused.is_open():
        if __debug__: logger.debug("focus is on an open dropdown, which has its own move_focus_direction: NOT moving")
        return

    # Modal-overlay handling: if layer_top has any focusable content (e.g. a
    # confirmation dialog), treat it as a modal — constrain all navigation to
    # that layer.  If current focus is still on the normal screen, redirect it
    # to the first overlay widget on the first keypress (Android-style: focus
    # jumps to the dialog on the first directional key, not proactively).
    first_on_top = _first_focusable_on_layer_top(focus_group)
    top_layer_active = first_on_top is not None

    if top_layer_active and not _is_on_layer_top(current_focused):
        if __debug__: logger.debug("move_focus_direction: modal overlay present — redirecting focus to layer_top")
        lv.group_focus_obj(first_on_top)
        return

    source_layout = _matrix_layout(current_focused)
    if source_layout is not None:
        # Use the matrix's own KEY handler for movement inside the grid.
        # It handles row lengths, control widths, and hidden buttons exactly
        # like LVGL does everywhere else.
        if _navigate_matrix_internal(current_focused, focus_group, angle):
            return

    o, btn_idx = find_closest_obj_in_direction(focus_group, current_focused, angle,
                                                top_layer_active=top_layer_active)
    if o:
        if __debug__: logger.debug("move_focus_direction: moving focus to:")
        mpos.util.print_lvgl_widget(o)
        if btn_idx is not None:
            _focus_matrix_button(o, btn_idx, focus_group)
        else:
            lv.group_focus_obj(o)

