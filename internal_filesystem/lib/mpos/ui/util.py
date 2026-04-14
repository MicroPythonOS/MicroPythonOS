# lib/mpos/ui/util.py
import sys


def get_foreground_app():
    from . import view
    if view.screen_stack:
        current_activity, _, _, _ = view.screen_stack[-1]
        if current_activity:
            return getattr(current_activity, "appFullName", None)
    return None
