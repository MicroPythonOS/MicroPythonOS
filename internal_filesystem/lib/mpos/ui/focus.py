# lib/mpos/ui/focus.py
import lvgl as lv

def move_focusgroup_objects(fromgroup, togroup):
    for i in range(fromgroup.get_obj_count()):
        obj = fromgroup.get_obj_by_index(0)
        if obj:
            togroup.add_obj(obj)

def save_and_clear_current_focusgroup():
    from .view import screen_stack
    default = lv.group_get_default()
    if default and screen_stack:
        activity, screen, focusgroup, focused = screen_stack.pop()
        move_focusgroup_objects(default, focusgroup)
        screen_stack.append((activity, screen, focusgroup, default.get_focused()))
