import lvgl as lv


# Focus borders highlight which widget directional (keypad/joystick) focus is
# on. They must stay invisible until the user actually navigates by direction,
# so a touch-only UI — where widgets are focused by tapping — never shows a
# stray highlight, and a hybrid touch+keypad device only shows it once the
# joystick is used. move_focus_direction() flips this on first use via
# enable_focus_borders().
_focus_nav_active = False


def enable_focus_borders():
    """Mark that the user has navigated by direction (joystick/keypad). From
    then on, focused widgets draw their focus border."""
    global _focus_nav_active
    _focus_nav_active = True


def _focus_border_handler(event, width, color, opacity, radius, bg_color, bg_color_unfocused):
    if not _focus_nav_active:
        # No directional navigation yet (e.g. touch-only use): no highlight.
        return
    target = event.get_target_obj()
    target.set_style_border_color(color, lv.PART.MAIN)
    target.set_style_border_width(width, lv.PART.MAIN)
    if opacity is not None:
        target.set_style_border_opa(opacity, lv.PART.MAIN)
    if radius is not None:
        target.set_style_radius(radius, lv.PART.MAIN)
    if bg_color is not None:
        target.set_style_bg_color(bg_color, lv.PART.MAIN)
    target.scroll_to_view(True)


def _defocus_border_handler(event, bg_color_unfocused):
    target = event.get_target_obj()
    target.set_style_border_width(0, lv.PART.MAIN)
    if bg_color_unfocused is not None:
        target.set_style_bg_color(bg_color_unfocused, lv.PART.MAIN)


def add_focus_border(widget, width=1, color=None, bg_color=None, bg_color_unfocused=None, opacity=None, radius=None):
    """Register focus/defocus callbacks that draw a border around a widget.

    If bg_color is given, the widget's background is set to that color when
    focused. If bg_color_unfocused is given, the background is restored to that
    color when focus moves away.

    The widget is always added to the focus group, but the highlight stays
    invisible until the user navigates by direction (see enable_focus_borders
    / move_focus_direction) — keeping the highlight off touch-only UIs while
    preserving it for keypad/encoder navigation."""
    if color is None:
        color = lv.theme_get_color_primary(None)
    widget.add_event_cb(
        lambda e, w=width, c=color, o=opacity, r=radius, bc=bg_color, bu=bg_color_unfocused: _focus_border_handler(e, w, c, o, r, bc, bu),
        lv.EVENT.FOCUSED,
        None,
    )
    widget.add_event_cb(
        lambda e, bu=bg_color_unfocused: _defocus_border_handler(e, bu),
        lv.EVENT.DEFOCUSED,
        None,
    )
    focusgroup = lv.group_get_default()
    if focusgroup:
        focusgroup.add_obj(widget)


def move_focusgroup_objects(fromgroup, togroup):
    for _ in range(fromgroup.get_obj_count()):
        obj = fromgroup.get_obj_by_index(0)
        if obj:
            togroup.add_obj(obj)


def focus_coordinates(x, y):
    """Move the default input-group focus to the object nearest to (x, y).

    The actual implementation lives in mpos.ui.focus_direction; this is a thin
    wrapper so callers can import it from mpos.ui.focus.
    """
    from . import focus_direction
    focus_direction.focus_coordinates(x, y)


def save_and_clear_current_focusgroup():
    from .view import screen_stack as s
    d = lv.group_get_default()
    if d and s:
        a, scr, fg, fo = s.pop()
        move_focusgroup_objects(d, fg)
        s.append((a, scr, fg, d.get_focused()))
