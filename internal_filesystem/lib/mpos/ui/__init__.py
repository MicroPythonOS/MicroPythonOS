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
from .setting_activity import SettingActivity
from .settings_activity import SettingsActivity
from .widget_animator import WidgetAnimator
from . import focus_direction

# Ordered list of additional symbols, see ../lvgl_micropython/lib_lvgl_src_font/README.md
# See Show Fonts app to display them all
SEARCH_SYMBOL = "\uf002"
HEART_SYMBOL = "\uf004"
STAR_SYMBOL = "\uf005"
SEARCH_PLUS_SYMBOL = "\uf00e" # also useful for "zoom in"
SEARCH_MINUS_SYMBOL = "\uf010" # also useful for "zoom out"
QR_SYMBOL = "\uf029"
CAMERA_SYMBOL = "\uf030"
THUMBS_UP_SYMBOL = "\uf164"
THUMBS_DOWN_SYMBOL = "\uf165"
SHARE_ALT_SYMBOL = "\uf1e0"
UNDO_ALT_SYMBOL = "\uf2ea"
HEADPHONES_ALT_SYMBOL = "\uf58f"

# Currency symbols
BITCOIN_B = "\u20bf" # ₿: a simple plain B with 2 vertical lines
BITCOIN_SYMBOL = "\uf15a" # official Bitcoin logo without circle
BITCOIN_LOGO = "\uf379" # official Bitcoin logo in a circle
SATOSHI_ITALIC_SYMBOL = "\u4e2f" # 丯
SATOSHI_SYMBOL = "\u4e30" # 丰

# main_display is assigned by board-specific initialization code
main_display = None


def get_foreground_app():
    from ..activity_navigator import get_foreground_app as _get_foreground_app
    return _get_foreground_app()


__all__ = [
    "setContentView", "back_screen", "remove_and_stop_current_activity", "remove_and_stop_all_activities",
    "handle_back_swipe", "handle_top_swipe",
    "AppearanceManager",
    "open_bar", "close_bar", "open_drawer", "drawer_open",
    "save_and_clear_current_focusgroup",
    "DisplayMetrics",
    "get_event_name", "print_event",
    "get_foreground_app",
    "SettingActivity",
    "SettingsActivity",
    "WidgetAnimator",
    "focus_direction",
    "SEARCH_SYMBOL",
    "HEART_SYMBOL",
    "STAR_SYMBOL",
    "SEARCH_PLUS_SYMBOL",
    "SEARCH_MINUS_SYMBOL",
    "QR_SYMBOL",
    "CAMERA_SYMBOL",
    "BTC_SYMBOL",
    "BITCOIN_B_SYMBOL",
    "SATOSHI_ITALIC_SYMBOL",
    "SATOSHI_SYMBOL",
    "THUMBS_UP_SYMBOL",
    "THUMBS_DOWN_SYMBOL",
    "SHARE_ALT_SYMBOL",
    "UNDO_ALT_SYMBOL",
    "BITCOIN_SYMBOL",
    "HEADPHONES_ALT_SYMBOL",
]
