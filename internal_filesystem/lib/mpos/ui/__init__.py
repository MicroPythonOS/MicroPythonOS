from .view import (
    setContentView, back_screen,
    screen_stack, remove_and_stop_current_activity, remove_and_stop_all_activities
)
from .gesture_navigation import handle_back_swipe, handle_top_swipe
from .appearance_manager import AppearanceManager
from .topmenu import open_bar, close_bar, open_drawer, drawer_open
from .focus import save_and_clear_current_focusgroup
from .display_metrics import DisplayMetrics
from .event import get_event_name, print_event
from .util import shutdown, set_foreground_app, get_foreground_app
from .setting_activity import SettingActivity
from .settings_activity import SettingsActivity
from .widget_animator import WidgetAnimator
from . import focus_direction

# main_display is assigned by board-specific initialization code
main_display = None

__all__ = [
    "setContentView", "back_screen", "remove_and_stop_current_activity", "remove_and_stop_all_activities",
    "handle_back_swipe", "handle_top_swipe",
    "AppearanceManager",
    "open_bar", "close_bar", "open_drawer", "drawer_open",
    "save_and_clear_current_focusgroup",
    "DisplayMetrics",
    "get_event_name", "print_event",
    "shutdown", "set_foreground_app", "get_foreground_app",
    "SettingActivity",
    "SettingsActivity",
    "WidgetAnimator",
    "focus_direction"
]
