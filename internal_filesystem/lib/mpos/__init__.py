# Core framework
from .app.app import App
from .app.activity import Activity
from .content.intent import Intent
from .activity_navigator import ActivityNavigator

from .content.package_manager import PackageManager
from .config import SharedPreferences
from .net.connectivity_manager import ConnectivityManager
from .net.wifi_service import WifiService
from .audio.audioflinger import AudioFlinger
from .net.download_manager import DownloadManager
from .task_manager import TaskManager
from .camera_manager import CameraManager
from .sensor_manager import SensorManager

# Common activities
from .app.activities.chooser import ChooserActivity
from .app.activities.view import ViewActivity
from .app.activities.share import ShareActivity

from .ui.setting_activity import SettingActivity
from .ui.settings_activity import SettingsActivity
from .ui.camera_activity import CameraActivity
from .ui.keyboard import MposKeyboard
from .ui.testing import (
    wait_for_render, capture_screenshot, simulate_click, get_widget_coords,
    find_label_with_text, verify_text_present, print_screen_labels, find_text_on_screen,
    click_button, click_label, click_keyboard_button, find_button_with_text,
    get_all_widgets_with_text
)

# UI utility functions
from .ui.display_metrics import DisplayMetrics
from .ui.event import get_event_name, print_event
from .ui.view import setContentView, back_screen
from .ui.theme import set_theme
from .ui.topmenu import open_bar, close_bar, open_drawer, drawer_open, NOTIFICATION_BAR_HEIGHT
from .ui.focus import save_and_clear_current_focusgroup
from .ui.gesture_navigation import handle_back_swipe, handle_top_swipe
from .ui.util import shutdown, set_foreground_app, get_foreground_app
from .ui.anim import smooth_show, smooth_hide
from .ui import focus_direction

# Utility modules
from . import apps
from . import bootloader
from . import ui
from . import config
from . import net
from . import content
from . import time
from . import sensor_manager
from . import camera_manager
from . import sdcard
from . import battery_voltage
from . import audio
from . import hardware

__all__ = [
    # Core framework
    "App",
    "Activity",
    "SharedPreferences",
    "ConnectivityManager", "DownloadManager", "WifiService", "AudioFlinger", "Intent",
    "ActivityNavigator", "PackageManager", "TaskManager", "CameraManager",
    # Common activities
    "ChooserActivity", "ViewActivity", "ShareActivity",
    "SettingActivity", "SettingsActivity", "CameraActivity",
    # UI components
    "MposKeyboard",
    # UI utility - DisplayMetrics
    "DisplayMetrics",
    "get_event_name", "print_event",
    "setContentView", "back_screen",
    "set_theme",
    "open_bar", "close_bar", "open_drawer", "drawer_open", "NOTIFICATION_BAR_HEIGHT",
    "save_and_clear_current_focusgroup",
    "handle_back_swipe", "handle_top_swipe",
    "shutdown", "set_foreground_app", "get_foreground_app",
    "smooth_show", "smooth_hide",
    "focus_direction",
    # Testing utilities
    "wait_for_render", "capture_screenshot", "simulate_click", "get_widget_coords",
    "find_label_with_text", "verify_text_present", "print_screen_labels", "find_text_on_screen",
    "click_button", "click_label", "click_keyboard_button", "find_button_with_text",
    "get_all_widgets_with_text",
    # Submodules
    "apps", "ui", "config", "net", "content", "time", "sensor_manager",
    "camera_manager", "sdcard", "battery_voltage", "audio", "hardware", "bootloader"
]
