import lvgl as lv


def _focus_border_handler(event, width, color, opacity, radius):
    target = event.get_target_obj()
    target.set_style_border_color(color, lv.PART.MAIN)
    target.set_style_border_width(width, lv.PART.MAIN)
    if opacity is not None:
        target.set_style_border_opa(opacity, lv.PART.MAIN)
    if radius is not None:
        target.set_style_radius(radius, lv.PART.MAIN)
    target.scroll_to_view(True)


def _defocus_border_handler(event):
    target = event.get_target_obj()
    target.set_style_border_width(0, lv.PART.MAIN)


def add_focus_border(widget, width=1, color=None, opacity=None, radius=None):
    """Register focus/defocus callbacks that draw a border around a widget."""
    if color is None:
        color = lv.theme_get_color_primary(None)
    widget.add_event_cb(
        lambda e, w=width, c=color, o=opacity, r=radius: _focus_border_handler(e, w, c, o, r),
        lv.EVENT.FOCUSED,
        None,
    )
    widget.add_event_cb(_defocus_border_handler, lv.EVENT.DEFOCUSED, None)
    focusgroup = lv.group_get_default()
    if focusgroup:
        focusgroup.add_obj(widget)


def move_focusgroup_objects(fromgroup, togroup):
    for _ in range(fromgroup.get_obj_count()):
        obj = fromgroup.get_obj_by_index(0)
        if obj:
            togroup.add_obj(obj)


def save_and_clear_current_focusgroup():
    from .view import screen_stack as s
    d = lv.group_get_default()
    if d and s:
        a, scr, fg, fo = s.pop()
        move_focusgroup_objects(d, fg)
        s.append((a, scr, fg, d.get_focused()))
