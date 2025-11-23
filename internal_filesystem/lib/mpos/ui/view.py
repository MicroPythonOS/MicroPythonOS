import lvgl as lv
from ..apps import restart_launcher
from .focus import save_and_clear_current_focusgroup
from .topmenu import open_bar

screen_stack = []

def setContentView(new_activity, new_screen):
    global screen_stack
    if screen_stack:
        current_activity, current_screen, current_focusgroup, _ = screen_stack[-1]
        current_activity.onPause(current_screen)
        current_activity.onStop(current_screen)

    from .util import close_top_layer_msgboxes
    close_top_layer_msgboxes()

    screen_stack.append((new_activity, new_screen, lv.group_create(), None))

    if new_activity:
        new_activity.onStart(new_screen)
    lv.screen_load_anim(new_screen, lv.SCREEN_LOAD_ANIM.OVER_LEFT, 500, 0, False)
    if new_activity:
        new_activity.onResume(new_screen)

def remove_and_stop_all_activities():
    global screen_stack
    while len(screen_stack):
        remove_and_stop_current_activity()

def remove_and_stop_current_activity():
    current_activity, current_screen, current_focusgroup, _ = screen_stack.pop()
    if current_activity:
        current_activity.onPause(current_screen)
        current_activity.onStop(current_screen)
        current_activity.onDestroy(current_screen)
        if current_screen:
            current_screen.clean()

def back_screen():
    global screen_stack
    if len(screen_stack) <= 1:
        print("Warning: can't go back — stack empty")
        return False

    from .util import close_top_layer_msgboxes
    close_top_layer_msgboxes()

    remove_and_stop_current_activity()

    # Load previous
    prev_activity, prev_screen, prev_focusgroup, prev_focused = screen_stack[-1]
    lv.screen_load_anim(prev_screen, lv.SCREEN_LOAD_ANIM.OVER_RIGHT, 500, 0, True)

    default_group = lv.group_get_default()
    if default_group:
        from .focus import move_focusgroup_objects
        move_focusgroup_objects(prev_focusgroup, default_group)
        from .focus_direction import emulate_focus_obj
        emulate_focus_obj(default_group, prev_focused)

    if prev_activity:
        prev_activity.onResume(prev_screen)

    if len(screen_stack) == 1:
        open_bar()

    return True
