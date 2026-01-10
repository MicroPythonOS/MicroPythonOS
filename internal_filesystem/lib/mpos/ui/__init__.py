from .view import (
    setContentView, back_screen,
    screen_stack, remove_and_stop_current_activity, remove_and_stop_all_activities
)
from .gesture_navigation import handle_back_swipe, handle_top_swipe
from .theme import set_theme
from .topmenu import open_bar, close_bar, open_drawer, drawer_open, NOTIFICATION_BAR_HEIGHT
from .focus import save_and_clear_current_focusgroup
from .display import (
    get_display_width, get_display_height,
    pct_of_display_width, pct_of_display_height,
    min_resolution, max_resolution,
    get_pointer_xy   # ← now correct
)
from .event import get_event_name, print_event
from .util import shutdown, set_foreground_app, get_foreground_app
from .setting_activity import SettingActivity

__all__ = [
    "setContentView", "back_screen", "remove_and_stop_current_activity", "remove_and_stop_all_activities"
    "handle_back_swipe", "handle_top_swipe",
    "set_theme",
    "open_bar", "close_bar", "open_drawer", "drawer_open", "NOTIFICATION_BAR_HEIGHT",
    "save_and_clear_current_focusgroup",
    "get_display_width", "get_display_height",
    "pct_of_display_width", "pct_of_display_height",
    "min_resolution", "max_resolution",
    "get_pointer_xy",
    "get_event_name", "print_event",
    "shutdown", "set_foreground_app", "get_foreground_app",
    "SettingActivity"
]
