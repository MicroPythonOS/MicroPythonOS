import lvgl as lv
import sys

from .focus import save_and_clear_current_focusgroup
from .topmenu import open_bar

screen_stack = []

def setContentView(new_activity, new_screen):
    global screen_stack
    if screen_stack:
        current_activity, current_screen, current_focusgroup, _ = screen_stack[-1]
        try:
            current_activity.onPause(current_screen)
        except Exception as e:
            print(f"onPause caught exception:")
            sys.print_exception(e)
        try:
            current_activity.onStop(current_screen)
        except Exception as e:
            print(f"onStop caught exception:")
            sys.print_exception(e)

    from .util import close_top_layer_msgboxes
    close_top_layer_msgboxes()

    screen_stack.append((new_activity, new_screen, lv.group_create(), None))

    if new_activity:
        try:
            new_activity.onStart(new_screen)
        except Exception as e:
            print(f"onStart caught exception:")
            sys.print_exception(e)
    lv.screen_load_anim(new_screen, lv.SCR_LOAD_ANIM.OVER_LEFT, 500, 0, False)
    if new_activity:
        try:
            new_activity.onResume(new_screen)
        except Exception as e:
            print(f"onResume caught exception:")
            sys.print_exception(e)

def remove_and_stop_all_activities():
    global screen_stack
    while len(screen_stack):
        remove_and_stop_current_activity()

def remove_and_stop_current_activity():
    current_activity, current_screen, current_focusgroup, _ = screen_stack.pop()
    if current_activity:
        try:
            current_activity.onPause(current_screen)
        except Exception as e:
            print(f"onPause caught exception:")
            sys.print_exception(e)
        try:
            current_activity.onStop(current_screen)
        except Exception as e:
            print(f"onStop caught exception:")
            sys.print_exception(e)
        try:
            current_activity.onDestroy(current_screen)
        except Exception as e:
            print(f"onDestroy caught exception:")
            sys.print_exception(e)
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
    print(f"back_screen got {prev_activity}, {prev_screen}, {prev_focusgroup}, {prev_focused}")
    lv.screen_load_anim(prev_screen, lv.SCR_LOAD_ANIM.OVER_RIGHT, 500, 0, True)

    default_group = lv.group_get_default()
    if default_group:
        from .focus import move_focusgroup_objects
        move_focusgroup_objects(prev_focusgroup, default_group)
        from .input_manager import InputManager
        InputManager.emulate_focus_obj(default_group, prev_focused)

    if prev_activity:
        prev_activity.onResume(prev_screen)

    if len(screen_stack) == 1:
        open_bar()

    return True
