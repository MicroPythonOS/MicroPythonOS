import lvgl as lv


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
