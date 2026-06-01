import lvgl as lv

import mpos.time
import mpos.config
from ..battery_manager import BatteryManager
from .display_metrics import DisplayMetrics
from .appearance_manager import AppearanceManager
from .input_manager import InputManager
from . import focus_direction
from .widget_animator import WidgetAnimator
from mpos.content.app_manager import AppManager
from mpos.notification_manager import NotificationManager

CLOCK_UPDATE_INTERVAL = 1000 # 10 or even 1 ms doesn't seem to change the framerate but 100ms is enough
WIFI_ICON_UPDATE_INTERVAL = 1500
BATTERY_ICON_UPDATE_INTERVAL = 15000 # not too often, but not too short, otherwise it takes a while to appear
TEMPERATURE_UPDATE_INTERVAL = 2000
MEMFREE_UPDATE_INTERVAL = 5000 # not too frequent because there's a forced gc.collect() to give it a reliable value

DRAWER_ANIM_DURATION=300


hide_bar_animation = None
show_bar_animation = None
show_bar_animation_start_value = -AppearanceManager.NOTIFICATION_BAR_HEIGHT
show_bar_animation_end_value = 0
hide_bar_animation_start_value = show_bar_animation_end_value
hide_bar_animation_end_value = show_bar_animation_start_value

drawer=None
drawer_open=False
bar_open=False

scroll_start_y = None

# Widgets:
notification_bar = None
notification_icon_label = None   # bell indicator in the top bar (label only – no image in the bar)
drawer_notifications_title = None
drawer_notifications_container = None

_notifications_listener_registered = False

_drawer_slider = None     # brightness slider; receives focus when the drawer opens
_drawer_focusables = []   # widgets added to / removed from the focus group when drawer opens/closes
_bar_focusables = []      # widgets added to / removed from the focus group when bar opens/closes


def _focus_topmenu_obj(event):
    """Visual feedback: draw a 1-px primary-colour border on focus."""
    target = event.get_target_obj()
    target.set_style_border_color(lv.theme_get_color_primary(None), lv.PART.MAIN)
    target.set_style_border_width(1, lv.PART.MAIN)


def _defocus_topmenu_obj(event):
    """Remove the focus border on defocus."""
    target = event.get_target_obj()
    target.set_style_border_width(0, lv.PART.MAIN)


def _register_focus_callbacks(widget):
    """
    Register focus/defocus visual-feedback callbacks on *widget*.
    Returns the widget for convenience.
    """
    widget.add_event_cb(_focus_topmenu_obj, lv.EVENT.FOCUSED, None)
    widget.add_event_cb(_defocus_topmenu_obj, lv.EVENT.DEFOCUSED, None)
    return widget


def _add_focusables_to_group(focusables):
    group = lv.group_get_default()
    if group:
        for w in focusables:
            group.add_obj(w)


def _remove_focusables_from_group(focusables):
    group = lv.group_get_default()
    if group:
        for w in focusables:
            try:
                group.remove_obj(w)
            except Exception:
                pass


def _icon_is_image_path(icon):
    """Return True if icon is a string that should be loaded as an image file."""
    if not isinstance(icon, str):
        return False
    return "." in icon or icon.startswith("M:") or icon.startswith("/")


def _set_notification_icon(notification):
    """Update the bell indicator in the top notification bar (label widget only)."""
    if notification_icon_label is None:
        return
    if notification is None:
        notification_icon_label.add_flag(lv.obj.FLAG.HIDDEN)
    else:
        notification_icon_label.remove_flag(lv.obj.FLAG.HIDDEN)



def _notification_pressed(event, notification_id):
    close_drawer()
    NotificationManager.trigger(notification_id)


def _build_drawer_notification_item(parent, notification):
    # The parent is a flex-column container, so no manual positioning needed.
    item_button = lv.button(parent)
    item_button.set_width(lv.pct(100))
    item_button.set_height(lv.SIZE_CONTENT)
    item_button.set_style_pad_all(8, lv.PART.MAIN)
    item_button.add_event_cb(
        lambda e, nid=notification.notification_id: _notification_pressed(e, nid),
        lv.EVENT.CLICKED,
        None,
    )

    icon = notification.icon
    icon_width = 0

    if _icon_is_image_path(icon) or (icon is not None and not isinstance(icon, str)):
        try:
            icon_size = DisplayMetrics.pct_of_width(8)
            icon_widget = lv.image(item_button)
            icon_widget.set_src(icon)
            icon_widget.set_size(icon_size, icon_size)
            icon_widget.align(lv.ALIGN.LEFT_MID, 0, 0)
            icon_width = icon_size + 6
        except Exception:
            icon = None  # fall through to symbol label
    if isinstance(icon, str) and not _icon_is_image_path(icon):
        icon_label = lv.label(item_button)
        icon_label.set_text(icon)
        icon_label.align(lv.ALIGN.LEFT_MID, 0, 0)
        icon_width = DisplayMetrics.pct_of_width(8)

    title_label = lv.label(item_button)
    title_label.set_text(notification.title)
    title_label.set_width(lv.pct(100) - icon_width - 16)
    title_label.set_long_mode(lv.label.LONG_MODE.WRAP)
    title_label.align(lv.ALIGN.TOP_LEFT, icon_width, 0)

    if notification.text:
        text_label = lv.label(item_button)
        text_label.set_text(notification.text)
        text_label.set_width(lv.pct(100) - icon_width - 16)
        text_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        text_label.align_to(title_label, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 4)


def _refresh_drawer_notifications():
    if drawer_notifications_container is None or drawer_notifications_title is None:
        return

    notifications = NotificationManager.get_notifications()
    drawer_notifications_container.clean()

    if not notifications:
        drawer_notifications_title.set_text(lv.SYMBOL.BELL + " Notifications")
        empty_label = lv.label(drawer_notifications_container)
        empty_label.set_text("No notifications")
        empty_label.align(lv.ALIGN.TOP_LEFT, 0, 0)
        return

    drawer_notifications_title.set_text(
        lv.SYMBOL.BELL + " Notifications (" + str(len(notifications)) + ")"
    )

    for notification in notifications:
        _build_drawer_notification_item(drawer_notifications_container, notification)


def _refresh_notification_widgets():
    notifications = NotificationManager.get_notifications()
    top_notification = notifications[0] if notifications else None
    _set_notification_icon(top_notification)
    _refresh_drawer_notifications()


def _register_notifications_listener():
    global _notifications_listener_registered
    if _notifications_listener_registered:
        return
    NotificationManager.register_listener(_refresh_notification_widgets, notify_immediately=False)
    _notifications_listener_registered = True

def toggle_drawer():
    if drawer_open:
        close_drawer()
    else:
        open_drawer()

def open_drawer():
    global drawer_open, drawer
    if not drawer_open:
        open_bar()
        drawer_open=True
        WidgetAnimator.show_widget(drawer, anim_type="slide_down", duration=1000, delay=0)
        drawer.scroll_to(0,0,False) # make sure it's at the top, not scrolled down
        _add_focusables_to_group(_drawer_focusables)
        if _drawer_slider:
            lv.group_focus_obj(_drawer_slider)

def close_drawer(to_launcher=False):
    global drawer_open, drawer
    if drawer_open:
        from mpos.activity_navigator import get_foreground_app
        drawer_open=False
        fg = get_foreground_app()
        print(f"topmenu.py foreground app: {fg}")
        if not to_launcher and fg is not None and not "launcher" in fg:
            print(f"close_drawer: also closing bar because to_launcher is {to_launcher} and foreground_app_name is {get_foreground_app()}")
            close_bar(False)
        WidgetAnimator.hide_widget(drawer, anim_type="slide_up", duration=1000, delay=0)
        _remove_focusables_from_group(_drawer_focusables)

def open_bar():
    print("opening bar...")
    global bar_open, show_bar_animation, hide_bar_animation, notification_bar
    if not bar_open:
        bar_open=True
        hide_bar_animation.current_value = hide_bar_animation_end_value
        show_bar_animation.start()
        _add_focusables_to_group(_bar_focusables)
    else:
        print("bar already open")

def close_bar(animate=True):
    global bar_open, show_bar_animation, hide_bar_animation
    if bar_open:
        bar_open=False
        show_bar_animation.current_value = show_bar_animation_end_value
        if animate:
            hide_bar_animation.start()
        else:
            notification_bar.set_y(hide_bar_animation_end_value)
        _remove_focusables_from_group(_bar_focusables)




def create_notification_bar():
    global notification_bar, notification_icon_label
    # Create notification bar
    notification_bar = lv.obj(lv.layer_top())
    notification_bar.set_size(lv.pct(100), AppearanceManager.NOTIFICATION_BAR_HEIGHT)
    notification_bar.set_pos(0, show_bar_animation_start_value)
    notification_bar.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    notification_bar.set_scroll_dir(lv.DIR.NONE)
    notification_bar.set_style_border_width(0, lv.PART.MAIN)
    notification_bar.set_style_radius(0, lv.PART.MAIN)
    notification_bar.add_flag(lv.obj.FLAG.CLICKABLE)
    # Focus/defocus visual feedback + ENTER opens the drawer.
    _register_focus_callbacks(notification_bar)
    _bar_focusables.append(notification_bar)
    # Pressing ENTER (click) on the focused notification bar opens the drawer.
    notification_bar.add_event_cb(lambda e: open_drawer(), lv.EVENT.CLICKED, None)
    # Time label
    time_label = lv.label(notification_bar)
    time_label.set_text("00:00:00")
    time_label.align(lv.ALIGN.LEFT_MID, DisplayMetrics.pct_of_width(10), 0)

    notification_icon_label = lv.label(notification_bar)
    notification_icon_label.set_text(lv.SYMBOL.BELL)
    notification_icon_label.align_to(time_label, lv.ALIGN.OUT_RIGHT_MID, DisplayMetrics.pct_of_width(2), 0)
    notification_icon_label.add_flag(lv.obj.FLAG.HIDDEN)

    temp_label = lv.label(notification_bar)
    temp_label.set_text("00°C")
    temp_label.align_to(time_label, lv.ALIGN.OUT_RIGHT_MID, DisplayMetrics.pct_of_width(10), 0)
    if False:
        memfree_label = lv.label(notification_bar)
        memfree_label.set_text("")
        memfree_label.align_to(temp_label, lv.ALIGN.OUT_RIGHT_MID, DisplayMetrics.pct_of_width(7), 0)
    #style = lv.style_t()
    #style.init()
    #style.set_text_font(lv.font_montserrat_8)  # tiny font
    #memfree_label.add_style(style, 0)
    # Notification icon (bell)
    #notif_icon = lv.label(notification_bar)
    #notif_icon.set_text(lv.SYMBOL.BELL)
    #notif_icon.align_to(time_label, lv.ALIGN.OUT_RIGHT_MID, PADDING_TINY, 0)

    # WiFi icon
    wifi_icon = lv.label(notification_bar)
    wifi_icon.set_text(lv.SYMBOL.WIFI)
    wifi_icon.add_flag(lv.obj.FLAG.HIDDEN)
    wifi_icon.align(lv.ALIGN.RIGHT_MID, -DisplayMetrics.pct_of_width(10), 0)

    # Battery percentage
    if BatteryManager.has_battery():
        #battery_label = lv.label(notification_bar)
        #battery_label.set_text("100%")
        #battery_label.align(lv.ALIGN.RIGHT_MID, 0, 0)
        #battery_label.add_flag(lv.obj.FLAG.HIDDEN)
        # Battery icon
        battery_icon = lv.label(notification_bar)
        battery_icon.set_text(lv.SYMBOL.BATTERY_FULL)
        #battery_icon.align_to(battery_label, lv.ALIGN.OUT_LEFT_MID, 0, 0)
        battery_icon.align(lv.ALIGN.RIGHT_MID, -DisplayMetrics.pct_of_width(10), 0)
        wifi_icon.align_to(battery_icon, lv.ALIGN.OUT_LEFT_MID, -DisplayMetrics.pct_of_width(1), 0)
        battery_icon.add_flag(lv.obj.FLAG.HIDDEN) # keep it hidden until it has a correct value
        def update_battery_icon(timer=None):
            try:
                percent = BatteryManager.get_battery_percentage()
            except Exception as e:
                print(f"BatteryManager.get_battery_percentage got exception, not updating battery_icon: {e}")
                return
            if percent > 80:
                battery_icon.set_text(lv.SYMBOL.BATTERY_FULL)
            elif percent > 60:
                battery_icon.set_text(lv.SYMBOL.BATTERY_3)
            elif percent > 40:
                battery_icon.set_text(lv.SYMBOL.BATTERY_2)
            elif percent > 20:
                battery_icon.set_text(lv.SYMBOL.BATTERY_1)
            else:
                battery_icon.set_text(lv.SYMBOL.BATTERY_EMPTY)
            battery_icon.align(lv.ALIGN.RIGHT_MID, -DisplayMetrics.pct_of_width(10), 0)
            wifi_icon.align_to(battery_icon, lv.ALIGN.OUT_LEFT_MID, -DisplayMetrics.pct_of_width(1), 0)
            battery_icon.remove_flag(lv.obj.FLAG.HIDDEN)
            # Percentage is not shown for now:
            #battery_label.set_text(f"{round(percent)}%")
            #battery_label.remove_flag(lv.obj.FLAG.HIDDEN)
        update_battery_icon() # run it immediately instead of waiting for the timer
        lv.timer_create(update_battery_icon, BATTERY_ICON_UPDATE_INTERVAL, None)

    # Update time
    def update_time(timer):
        hours = mpos.time.localtime()[3]
        minutes = mpos.time.localtime()[4]
        seconds = mpos.time.localtime()[5]
        time_label.set_text(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
    
    def update_wifi_icon(timer):
        from mpos import WifiService
        if WifiService.is_connected():
            wifi_icon.remove_flag(lv.obj.FLAG.HIDDEN)
        else:
            wifi_icon.add_flag(lv.obj.FLAG.HIDDEN)
    
    # Get temperature sensor via SensorManager
    from mpos import SensorManager
    temp_sensor = None
    if SensorManager.is_available():
        # Prefer MCU temperature (more stable) over IMU temperature
        temp_sensor = SensorManager.get_default_sensor(SensorManager.TYPE_SOC_TEMPERATURE)
        if not temp_sensor:
            temp_sensor = SensorManager.get_default_sensor(SensorManager.TYPE_IMU_TEMPERATURE)

    def update_temperature(timer):
        if temp_sensor:
            temp = SensorManager.read_sensor(temp_sensor)
            if temp is not None:
                temp_label.set_text(f"{round(temp)}°C")
            else:
                temp_label.set_text("--°C")
        else:
            temp_label.set_text("42°C")
    
    lv.timer_create(update_time, CLOCK_UPDATE_INTERVAL, None)
    lv.timer_create(update_temperature, TEMPERATURE_UPDATE_INTERVAL, None)
    #lv.timer_create(update_memfree, MEMFREE_UPDATE_INTERVAL, None)
    lv.timer_create(update_wifi_icon, WIFI_ICON_UPDATE_INTERVAL, None)
    
    # hide bar animation
    global hide_bar_animation
    hide_bar_animation = lv.anim_t()
    hide_bar_animation.init()
    hide_bar_animation.set_var(notification_bar)
    hide_bar_animation.set_values(0, -AppearanceManager.NOTIFICATION_BAR_HEIGHT)
    hide_bar_animation.set_duration(2000)
    hide_bar_animation.set_custom_exec_cb(lambda not_used, value : notification_bar.set_y(value))
    
    # show bar animation
    global show_bar_animation
    show_bar_animation = lv.anim_t()
    show_bar_animation.init()
    show_bar_animation.set_var(notification_bar)
    show_bar_animation.set_values(show_bar_animation_start_value, show_bar_animation_end_value)
    show_bar_animation.set_duration(1000)
    show_bar_animation.set_custom_exec_cb(lambda not_used, value : notification_bar.set_y(value))

    _register_notifications_listener()
    _refresh_notification_widgets()
    


def create_drawer():
    global drawer, drawer_notifications_title, drawer_notifications_container
    drawer=lv.obj(lv.layer_top())
    drawer.set_size(lv.pct(100),lv.pct(90))
    drawer.set_pos(0,AppearanceManager.NOTIFICATION_BAR_HEIGHT)
    drawer.set_scroll_dir(lv.DIR.VER)
    drawer.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    drawer.set_style_pad_all(2, lv.PART.MAIN)
    drawer.set_style_border_width(0, lv.PART.MAIN)
    drawer.set_style_radius(0, lv.PART.MAIN)
    drawer.add_flag(lv.obj.FLAG.HIDDEN)
    drawer.add_event_cb(drawer_scroll_callback, lv.EVENT.SCROLL_BEGIN, None)
    drawer.add_event_cb(drawer_scroll_callback, lv.EVENT.SCROLL, None)
    drawer.add_event_cb(drawer_scroll_callback, lv.EVENT.SCROLL_END, None)

    # ── Outer flex-column: stacks top_group + notifications section ──────────
    outer = lv.obj(drawer)
    outer.set_width(lv.pct(100))
    outer.set_height(lv.SIZE_CONTENT)
    outer.align(lv.ALIGN.TOP_LEFT, 0, 0)
    outer.set_style_pad_all(0, lv.PART.MAIN)
    outer.set_style_pad_row(8, lv.PART.MAIN)
    outer.set_style_border_width(0, lv.PART.MAIN)
    outer.set_style_radius(0, lv.PART.MAIN)
    outer.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
    outer.remove_flag(lv.obj.FLAG.SCROLLABLE)
    outer.set_layout(lv.LAYOUT.FLEX)
    outer.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    outer.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.START)

    # ── Top section: FLOW COLUMN container (brightness + icon row) ──────────
    top_group = lv.obj(outer)
    top_group.set_width(lv.pct(100))
    top_group.set_height(lv.SIZE_CONTENT)
    top_group.align(lv.ALIGN.TOP_MID, 0, 0)
    top_group.set_style_pad_all(0, lv.PART.MAIN)
    top_group.set_style_pad_row(2, lv.PART.MAIN)
    top_group.set_style_border_width(0, lv.PART.MAIN)
    top_group.set_style_radius(0, lv.PART.MAIN)
    top_group.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
    top_group.remove_flag(lv.obj.FLAG.SCROLLABLE)
    top_group.set_layout(lv.LAYOUT.FLEX)
    top_group.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    top_group.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

    # ── Brightness row ───────────────────────────────────────────────────────
    brightness_row = lv.obj(top_group)
    brightness_row.set_width(lv.pct(100))
    brightness_row.set_height(lv.SIZE_CONTENT)
    brightness_row.set_style_pad_all(0, lv.PART.MAIN)
    brightness_row.set_style_pad_row(2, lv.PART.MAIN)
    brightness_row.set_style_border_width(0, lv.PART.MAIN)
    brightness_row.set_style_radius(0, lv.PART.MAIN)
    brightness_row.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
    brightness_row.remove_flag(lv.obj.FLAG.SCROLLABLE)
    brightness_row.set_layout(lv.LAYOUT.FLEX)
    brightness_row.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    brightness_row.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

    prefs = mpos.config.SharedPreferences("com.micropythonos.settings")
    brightness_int = prefs.get_int("display_brightness", 100)
    if mpos.ui.main_display:
        mpos.ui.main_display.set_backlight(brightness_int)

    global _drawer_slider
    slider = lv.slider(brightness_row)
    slider.set_range(1, 100)
    slider.set_value(int(brightness_int), False)
    slider.set_width(lv.pct(92))
    slider.set_style_pad_all(5, lv.PART.MAIN)
    slider.set_style_margin_top(DisplayMetrics.pct_of_height(3), lv.PART.MAIN)
    slider.set_style_margin_bottom(DisplayMetrics.pct_of_height(6), lv.PART.MAIN)
    _drawer_slider = slider
    _register_focus_callbacks(_drawer_slider)
    _drawer_focusables.append(slider)

    def brightness_slider_changed(e):
        brightness_int = slider.get_value()
        if mpos.ui.main_display:
            mpos.ui.main_display.set_backlight(brightness_int)
    def brightness_slider_released(e):
        brightness_int = slider.get_value()
        prefs = mpos.config.SharedPreferences("com.micropythonos.settings")
        old_brightness_int = prefs.get_int("display_brightness")
        if old_brightness_int != brightness_int:
            editor = prefs.edit()
            editor.put_int("display_brightness", brightness_int)
            editor.commit()
    slider.add_event_cb(brightness_slider_changed, lv.EVENT.VALUE_CHANGED, None)
    slider.add_event_cb(brightness_slider_released, lv.EVENT.RELEASED, None)

    # ── Icon-only button row ─────────────────────────────────────────────────
    icon_row = lv.obj(top_group)
    icon_row.set_width(lv.pct(100))
    icon_row.set_height(lv.SIZE_CONTENT)
    icon_row.set_style_pad_all(0, lv.PART.MAIN)
    icon_row.set_style_pad_column(6, lv.PART.MAIN)
    icon_row.set_style_border_width(0, lv.PART.MAIN)
    icon_row.set_style_radius(0, lv.PART.MAIN)
    icon_row.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
    icon_row.remove_flag(lv.obj.FLAG.SCROLLABLE)
    icon_row.set_layout(lv.LAYOUT.FLEX)
    icon_row.set_flex_flow(lv.FLEX_FLOW.ROW)
    icon_row.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

    icon_btn_size = DisplayMetrics.pct_of_width(17)

    # WiFi button
    wifi_btn = lv.button(icon_row)
    wifi_btn.set_size(icon_btn_size, icon_btn_size)
    wifi_btn.set_style_pad_all(4, lv.PART.MAIN)
    wifi_label = lv.label(wifi_btn)
    wifi_label.set_text(lv.SYMBOL.WIFI)
    wifi_label.center()
    def wifi_event(e):
        close_drawer()
        AppManager.start_app("com.micropythonos.settings.wifi")
    wifi_btn.add_event_cb(wifi_event, lv.EVENT.CLICKED, None)
    _register_focus_callbacks(wifi_btn)
    _drawer_focusables.append(wifi_btn)

    # Settings button
    settings_btn = lv.button(icon_row)
    settings_btn.set_size(icon_btn_size, icon_btn_size)
    settings_btn.set_style_pad_all(4, lv.PART.MAIN)
    settings_label = lv.label(settings_btn)
    settings_label.set_text(lv.SYMBOL.SETTINGS)
    settings_label.center()
    def settings_event(e):
        close_drawer()
        AppManager.start_app("com.micropythonos.settings")
    settings_btn.add_event_cb(settings_event, lv.EVENT.CLICKED, None)
    _drawer_focusables.append(settings_btn)

    # Launcher (Home) button
    launcher_btn = lv.button(icon_row)
    launcher_btn.set_size(icon_btn_size, icon_btn_size)
    launcher_btn.set_style_pad_all(4, lv.PART.MAIN)
    launcher_label = lv.label(launcher_btn)
    launcher_label.set_text(lv.SYMBOL.HOME)
    launcher_label.center()
    def launcher_event(e):
        print("Launch button pressed!")
        close_drawer(True)
        AppManager.refresh_apps()
        AppManager.restart_launcher()
    launcher_btn.add_event_cb(launcher_event, lv.EVENT.CLICKED, None)
    _register_focus_callbacks(launcher_btn)
    _drawer_focusables.append(launcher_btn)

    # Reset button
    restart_btn = lv.button(icon_row)
    restart_btn.set_size(icon_btn_size, icon_btn_size)
    restart_btn.set_style_pad_all(4, lv.PART.MAIN)
    restart_label = lv.label(restart_btn)
    restart_label.set_text(lv.SYMBOL.REFRESH)
    restart_label.center()
    def reset_cb(e):
        from .view import remove_and_stop_current_activity
        remove_and_stop_current_activity()
        import machine
        if hasattr(machine, 'reset'):
            machine.reset()
        elif hasattr(machine, 'soft_reset'):
            machine.soft_reset()
        else:
            print("Warning: machine has no reset or soft_reset method available")
    restart_btn.add_event_cb(reset_cb, lv.EVENT.CLICKED, None)
    _drawer_focusables.append(restart_btn)

    # Power-off button
    poweroff_btn = lv.button(icon_row)
    poweroff_btn.set_size(icon_btn_size, icon_btn_size)
    poweroff_btn.set_style_pad_all(4, lv.PART.MAIN)
    poweroff_label = lv.label(poweroff_btn)
    poweroff_label.set_text(lv.SYMBOL.POWER)
    poweroff_label.center()
    def poweroff_cb(e):
        print("Power off action...")
        from .view import remove_and_stop_current_activity
        remove_and_stop_current_activity()
        import sys
        if sys.platform == "esp32":
            import machine
            print("Entering deep sleep...")
            machine.deepsleep()
        else:
            import mpos ; mpos.TaskManager.stop()
            lv.deinit()
            import os
            os.system("kill $PPID")
    poweroff_btn.add_event_cb(poweroff_cb, lv.EVENT.CLICKED, None)
    _drawer_focusables.append(poweroff_btn)

    # ── Notifications section ────────────────────────────────────────────────
    # notif_section is a flex child of outer, so it stacks automatically below top_group
    notif_section = lv.obj(outer)
    notif_section.set_width(lv.pct(100))
    notif_section.set_height(lv.SIZE_CONTENT)
    notif_section.set_style_pad_all(0, lv.PART.MAIN)
    notif_section.set_style_pad_row(4, lv.PART.MAIN)
    notif_section.set_style_border_width(0, lv.PART.MAIN)
    notif_section.set_style_radius(0, lv.PART.MAIN)
    notif_section.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
    notif_section.remove_flag(lv.obj.FLAG.SCROLLABLE)
    notif_section.set_layout(lv.LAYOUT.FLEX)
    notif_section.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    notif_section.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.START)

    drawer_notifications_title = lv.label(notif_section)
    drawer_notifications_title.set_text(lv.SYMBOL.BELL + " Notifications")
    drawer_notifications_title.set_width(lv.pct(100))
    _register_focus_callbacks(drawer_notifications_title)

    drawer_notifications_container = lv.obj(notif_section)
    drawer_notifications_container.set_width(lv.pct(100))
    drawer_notifications_container.set_height(lv.SIZE_CONTENT)
    drawer_notifications_container.set_style_pad_all(0, lv.PART.MAIN)
    drawer_notifications_container.set_style_pad_row(4, lv.PART.MAIN)
    drawer_notifications_container.set_style_border_width(0, lv.PART.MAIN)
    drawer_notifications_container.set_style_radius(0, lv.PART.MAIN)
    drawer_notifications_container.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
    drawer_notifications_container.remove_flag(lv.obj.FLAG.SCROLLABLE)
    drawer_notifications_container.set_layout(lv.LAYOUT.FLEX)
    drawer_notifications_container.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    drawer_notifications_container.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.START)

    # Populate notifications now that the container exists
    _refresh_notification_widgets()

    # Invisible spacer at the bottom of the outer flex column — makes the drawer
    # content taller than the viewport so LVGL scroll events fire, which is what
    # drawer_scroll_callback uses to detect the swipe-up-to-close gesture.
    spacer = lv.label(outer)
    spacer.set_text("")
    spacer.set_height(DisplayMetrics.pct_of_height(40))


def drawer_scroll_callback(event):
    global scroll_start_y
    event_code=event.get_code()
    x, y = InputManager.pointer_xy()
    #name = mpos.ui.get_event_name(event_code)
    #print(f"drawer_scroll: code={event_code}, name={name}, ({x},{y})")
    if event_code == lv.EVENT.SCROLL_BEGIN and scroll_start_y == None:
        scroll_start_y = y
        #print(f"scroll_starts at: {x},{y}")
    elif event_code == lv.EVENT.SCROLL and scroll_start_y != None:
        diff = y - scroll_start_y
        #print(f"scroll distance: {diff}")
        if diff < -AppearanceManager.NOTIFICATION_BAR_HEIGHT:
            close_drawer()
    elif event_code == lv.EVENT.SCROLL_END:
        scroll_start_y = None
