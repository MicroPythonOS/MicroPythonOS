import logging
import lvgl as lv
import sys

from .topmenu import open_bar, close_drawer

logger = logging.getLogger(__name__)

screen_stack = []


def close_top_layer_msgboxes():
    top = lv.layer_top()
    if not top:
        return
    i = 0
    while i < top.get_child_count_by_type(lv.msgbox_backdrop_class):
        child = top.get_child_by_type(i, lv.msgbox_backdrop_class)
        msgbox = child.get_child_by_type(0, lv.msgbox_class)
        if msgbox:
            msgbox.close()
        i += 1

def setContentView(new_activity, new_screen):
    global screen_stack
    if screen_stack:
        current_activity, current_screen, current_focusgroup, _ = screen_stack[-1]
        try:
            current_activity.onPause(current_screen)
        except Exception as e:
            logger.error("onPause caught exception:")
            sys.print_exception(e)
        try:
            current_activity.onStop(current_screen)
        except Exception as e:
            logger.error("onStop caught exception:")
            sys.print_exception(e)

    close_top_layer_msgboxes()

    screen_stack.append((new_activity, new_screen, lv.group_create(), None))

    if new_activity:
        try:
            new_activity.onStart(new_screen)
        except Exception as e:
            logger.error("onStart caught exception:")
            sys.print_exception(e)
            from mpos.ui.errordialog import show_app_error_dialog
            show_app_error_dialog(
                new_activity.appFullName, e, is_lifecycle=True
            )
    lv.screen_load_anim(new_screen, lv.SCREEN_LOAD_ANIM.OVER_LEFT, 500, 0, False)
    if new_activity:
        try:
            new_activity.onResume(new_screen)
        except Exception as e:
            logger.error("onResume caught exception:")
            sys.print_exception(e)
            from mpos.ui.errordialog import show_app_error_dialog
            show_app_error_dialog(
                new_activity.appFullName, e, is_lifecycle=True
            )

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
            logger.error("onPause caught exception:")
            sys.print_exception(e)
        try:
            current_activity.onStop(current_screen)
        except Exception as e:
            logger.error("onStop caught exception:")
            sys.print_exception(e)
        try:
            current_activity.onDestroy(current_screen)
        except Exception as e:
            logger.error("onDestroy caught exception:")
            sys.print_exception(e)
        if current_screen:
            current_screen.clean()

def finish_current_activity():
    """Remove the current activity and resume the one below it.

    This is the direct "finish" path; it does not ask onBackPressed().
    """
    global screen_stack

    if len(screen_stack) <= 1:
        logger.warning("Can't finish — stack empty")
        return False

    close_top_layer_msgboxes()

    remove_and_stop_current_activity()

    # Load previous
    prev_activity, prev_screen, prev_focusgroup, prev_focused = screen_stack[-1]
    if __debug__: logger.debug("finish_current_activity got %s, %s, %s, %s", prev_activity, prev_screen, prev_focusgroup, prev_focused)
    lv.screen_load_anim(prev_screen, lv.SCREEN_LOAD_ANIM.OVER_RIGHT, 500, 0, True)

    default_group = lv.group_get_default()
    if default_group:
        from .focus import move_focusgroup_objects
        move_focusgroup_objects(prev_focusgroup, default_group)
        lv.group_focus_obj(prev_focused)

    if prev_activity:
        prev_activity.onResume(prev_screen)

    if len(screen_stack) == 1:
        open_bar()

    return True


def back_screen():
    global screen_stack

    from . import topmenu
    if topmenu.drawer_open:
        close_drawer()
        return True

    if len(screen_stack) <= 1:
        logger.warning("Can't go back — stack empty")
        return False

    current_activity, current_screen, _, _ = screen_stack[-1]
    if current_activity and current_activity.onBackPressed(current_screen):
        return True

    return finish_current_activity()
