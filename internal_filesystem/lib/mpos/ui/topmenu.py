import lvgl as lv

import mpos.ui
import mpos.battery_voltage
from .display import (get_display_width, get_display_height)
from .util import (get_foreground_app)

from mpos.ui.anim import WidgetAnimator

NOTIFICATION_BAR_HEIGHT=24

CLOCK_UPDATE_INTERVAL = 1000 # 10 or even 1 ms doesn't seem to change the framerate but 100ms is enough
WIFI_ICON_UPDATE_INTERVAL = 1500
BATTERY_ICON_UPDATE_INTERVAL = 15000 # not too often, but not too short, otherwise it takes a while to appear
TEMPERATURE_UPDATE_INTERVAL = 2000
MEMFREE_UPDATE_INTERVAL = 5000 # not too frequent because there's a forced gc.collect() to give it a reliable value

DRAWER_ANIM_DURATION=300


hide_bar_animation = None
show_bar_animation = None
show_bar_animation_start_value = -NOTIFICATION_BAR_HEIGHT
show_bar_animation_end_value = 0
hide_bar_animation_start_value = show_bar_animation_end_value
hide_bar_animation_end_value = show_bar_animation_start_value

drawer=None
drawer_open=False
bar_open=False

scroll_start_y = None

# Widgets:
notification_bar = None

def open_drawer():
    global drawer_open, drawer
    if not drawer_open:
        open_bar()
        drawer_open=True
        WidgetAnimator.show_widget(drawer, anim_type="slide_down", duration=1000, delay=0)
        drawer.scroll_to(0,0,False) # make sure it's at the top, not scrolled down

def close_drawer(to_launcher=False):
    global drawer_open, drawer
    if drawer_open:
        drawer_open=False
        if not to_launcher and not "launcher" in get_foreground_app():
            print(f"close_drawer: also closing bar because to_launcher is {to_launcher} and foreground_app_name is {get_foreground_app()}")
            close_bar(False)
        WidgetAnimator.hide_widget(drawer, anim_type="slide_up", duration=1000, delay=0)

def open_bar():
    print("opening bar...")
    global bar_open, show_bar_animation, hide_bar_animation, notification_bar
    if not bar_open:
        #print("not open so opening...")
        bar_open=True
        hide_bar_animation.current_value = hide_bar_animation_end_value
        show_bar_animation.start()
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




def create_notification_bar():
    global notification_bar
    # Create notification bar
    notification_bar = lv.obj(lv.layer_top())
    notification_bar.set_size(lv.pct(100), NOTIFICATION_BAR_HEIGHT)
    notification_bar.set_pos(0, show_bar_animation_start_value)
    notification_bar.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    notification_bar.set_scroll_dir(lv.DIR.NONE)
    notification_bar.set_style_border_width(0, 0)
    notification_bar.set_style_radius(0, 0)
    # Time label
    time_label = lv.label(notification_bar)
    time_label.set_text("00:00:00")
    time_label.align(lv.ALIGN.LEFT_MID, mpos.ui.pct_of_display_width(10), 0)
    temp_label = lv.label(notification_bar)
    temp_label.set_text("00°C")
    temp_label.align_to(time_label, lv.ALIGN.OUT_RIGHT_MID, mpos.ui.pct_of_display_width(7)	, 0)
    if False:
        memfree_label = lv.label(notification_bar)
        memfree_label.set_text("")
        memfree_label.align_to(temp_label, lv.ALIGN.OUT_RIGHT_MID, mpos.ui.pct_of_display_width(7), 0)
    #style = lv.style_t()
    #style.init()
    #style.set_text_font(lv.font_montserrat_8)  # tiny font
    #memfree_label.add_style(style, 0)
    # Notification icon (bell)
    #notif_icon = lv.label(notification_bar)
    #notif_icon.set_text(lv.SYMBOL.BELL)
    #notif_icon.align_to(time_label, lv.ALIGN.OUT_RIGHT_MID, PADDING_TINY, 0)
    # Battery percentage
    #battery_label = lv.label(notification_bar)
    #battery_label.set_text("100%")
    #battery_label.align(lv.ALIGN.RIGHT_MID, 0, 0)
    #battery_label.add_flag(lv.obj.FLAG.HIDDEN)
    # Battery icon
    battery_icon = lv.label(notification_bar)
    battery_icon.set_text(lv.SYMBOL.BATTERY_FULL)
    #battery_icon.align_to(battery_label, lv.ALIGN.OUT_LEFT_MID, 0, 0)
    battery_icon.align(lv.ALIGN.RIGHT_MID, -mpos.ui.pct_of_display_width(10), 0)
    battery_icon.add_flag(lv.obj.FLAG.HIDDEN) # keep it hidden until it has a correct value
    # WiFi icon
    wifi_icon = lv.label(notification_bar)
    wifi_icon.set_text(lv.SYMBOL.WIFI)
    wifi_icon.align_to(battery_icon, lv.ALIGN.OUT_LEFT_MID, -mpos.ui.pct_of_display_width(1), 0)
    wifi_icon.add_flag(lv.obj.FLAG.HIDDEN)
    # Update time
    def update_time(timer):
        hours = mpos.time.localtime()[3]
        minutes = mpos.time.localtime()[4]
        seconds = mpos.time.localtime()[5]
        time_label.set_text(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
    
    can_check_network = False
    try:
        import network
        can_check_network = True
    except Exception as e:
        print("Warning: could not check WLAN status:", str(e))
    
    def update_battery_icon(timer=None):
        try:
            percent = mpos.battery_voltage.get_battery_percentage()
        except Exception as e:
            print(f"battery_voltage.get_battery_percentage got exception, not updating battery_icon: {e}")
            return
        if percent > 80: # 4.1V
            battery_icon.set_text(lv.SYMBOL.BATTERY_FULL)
        elif percent > 60: # 4.0V
            battery_icon.set_text(lv.SYMBOL.BATTERY_3)
        elif percent > 40: # 3.9V
            battery_icon.set_text(lv.SYMBOL.BATTERY_2)
        elif percent > 20: # 3.8V
            battery_icon.set_text(lv.SYMBOL.BATTERY_1)
        else: # > 3.7V
            battery_icon.set_text(lv.SYMBOL.BATTERY_EMPTY)
        battery_icon.remove_flag(lv.obj.FLAG.HIDDEN)
        # Percentage is not shown for now:
        #battery_label.set_text(f"{round(percent)}%")
        #battery_label.remove_flag(lv.obj.FLAG.HIDDEN)
    update_battery_icon() # run it immediately instead of waiting for the timer

    def update_wifi_icon(timer):
        from mpos.net.wifi_service import WifiService
        if WifiService.is_connected():
            wifi_icon.remove_flag(lv.obj.FLAG.HIDDEN)
        else:
            wifi_icon.add_flag(lv.obj.FLAG.HIDDEN)
    
    can_check_temperature = False
    try:
        import esp32
        can_check_temperature = True
    except Exception as e:
        print("Warning: can't check temperature sensor:", str(e))
    
    def update_temperature(timer):
        if can_check_temperature:
            temp_label.set_text(f"{esp32.mcu_temperature()}°C")
        else:
            temp_label.set_text("42°C")
    
    def update_memfree(timer):
        import gc
        gc.collect() # otherwise it goes down to 10% before shooting back up to 70%
        free = gc.mem_free()
        used = gc.mem_alloc()
        total_memory = gc.mem_free() + gc.mem_alloc()
        percentage = round(free * 100 / (free + used))
        memfree_label.set_text(f"{percentage}%")
    
    lv.timer_create(update_time, CLOCK_UPDATE_INTERVAL, None)
    lv.timer_create(update_temperature, TEMPERATURE_UPDATE_INTERVAL, None)
    #lv.timer_create(update_memfree, MEMFREE_UPDATE_INTERVAL, None)
    lv.timer_create(update_wifi_icon, WIFI_ICON_UPDATE_INTERVAL, None)
    lv.timer_create(update_battery_icon, BATTERY_ICON_UPDATE_INTERVAL, None)
    
    # hide bar animation
    global hide_bar_animation
    hide_bar_animation = lv.anim_t()
    hide_bar_animation.init()
    hide_bar_animation.set_var(notification_bar)
    hide_bar_animation.set_values(0, -NOTIFICATION_BAR_HEIGHT)
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
    


def create_drawer(display=None):
    global drawer
    drawer=lv.obj(lv.layer_top())
    drawer.set_size(lv.pct(100),lv.pct(90))
    drawer.set_pos(0,NOTIFICATION_BAR_HEIGHT)
    drawer.set_scroll_dir(lv.DIR.VER)
    drawer.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    drawer.set_style_pad_all(15, 0)
    drawer.set_style_border_width(0, 0)
    drawer.set_style_radius(0, 0)
    drawer.add_flag(lv.obj.FLAG.HIDDEN)
    drawer.add_event_cb(drawer_scroll_callback, lv.EVENT.SCROLL_BEGIN, None)
    drawer.add_event_cb(drawer_scroll_callback, lv.EVENT.SCROLL, None)
    drawer.add_event_cb(drawer_scroll_callback, lv.EVENT.SCROLL_END, None)
    slider_label=lv.label(drawer)
    prefs = mpos.config.SharedPreferences("com.micropythonos.settings")
    brightness_int = prefs.get_int("display_brightness", 100)
    if mpos.ui.main_display:
        mpos.ui.main_display.set_backlight(brightness_int)
    slider_label.set_text(f"Brightness: {brightness_int}%")
    slider_label.align(lv.ALIGN.TOP_MID,0,lv.pct(4))
    slider=lv.slider(drawer)
    slider.set_range(1,100)
    slider.set_value(int(brightness_int),False)
    slider.set_width(lv.pct(80))
    slider.align_to(slider_label,lv.ALIGN.OUT_BOTTOM_MID,0,10)
    def brightness_slider_changed(e):
        brightness_int = slider.get_value()
        slider_label.set_text(f"Brightness: {brightness_int}%")
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
    slider.add_event_cb(brightness_slider_changed,lv.EVENT.VALUE_CHANGED,None)
    slider.add_event_cb(brightness_slider_released,lv.EVENT.RELEASED,None)
    drawer_button_pct = 31
    wifi_btn=lv.button(drawer)
    wifi_btn.set_size(lv.pct(drawer_button_pct),lv.pct(20))
    wifi_btn.align(lv.ALIGN.LEFT_MID,0,0)
    wifi_label=lv.label(wifi_btn)
    wifi_label.set_text(lv.SYMBOL.WIFI+" WiFi")
    wifi_label.center()
    def wifi_event(e):
        close_drawer()
        mpos.apps.start_app("com.micropythonos.wifi")
    wifi_btn.add_event_cb(wifi_event,lv.EVENT.CLICKED,None)
    settings_btn=lv.button(drawer)
    settings_btn.set_size(lv.pct(drawer_button_pct),lv.pct(20))
    settings_btn.align(lv.ALIGN.RIGHT_MID,0,0)
    settings_label=lv.label(settings_btn)
    settings_label.set_text(lv.SYMBOL.SETTINGS+" Settings")
    settings_label.center()
    def settings_event(e):
        close_drawer()
        mpos.apps.start_app("com.micropythonos.settings")
    settings_btn.add_event_cb(settings_event,lv.EVENT.CLICKED,None)
    launcher_btn=lv.button(drawer)
    launcher_btn.set_size(lv.pct(drawer_button_pct),lv.pct(20))
    launcher_btn.align(lv.ALIGN.CENTER,0,0)
    launcher_label=lv.label(launcher_btn)
    launcher_label.set_text(lv.SYMBOL.HOME+" Launch")
    launcher_label.center()
    def launcher_event(e):
        print("Launch button pressed!")
        close_drawer(True)
        mpos.apps.restart_launcher()
    launcher_btn.add_event_cb(launcher_event,lv.EVENT.CLICKED,None)
    '''
    sleep_btn=lv.button(drawer)
    sleep_btn.set_size(lv.pct(drawer_button_pct),lv.pct(20))
    sleep_btn.align(lv.ALIGN.BOTTOM_LEFT,0,0)
    sleep_label=lv.label(sleep_btn)
    sleep_label.set_text("Zz Sleep")
    sleep_label.center()
    def sleep_event(e):
        print("Sleep button pressed!")
        import sys
        if sys.platform == "esp32":
            #On ESP32, there's no power off but there's a hundred-year deepsleep.
            import machine
            machine.deepsleep(10000) # TODO: make it wakeup when it receives an interrupt from the accelerometer or a button press
        else: # assume unix:
            # maybe do a system suspend here? or at least show a popup toast "not supported"
            close_drawer(True)
            mpos.apps.restart_launcher()
    sleep_btn.add_event_cb(sleep_event,lv.EVENT.CLICKED,None)
    '''
    restart_btn=lv.button(drawer)
    restart_btn.set_size(lv.pct(45),lv.pct(20))
    restart_btn.align(lv.ALIGN.BOTTOM_LEFT,0,0)
    restart_label=lv.label(restart_btn)
    restart_label.set_text(lv.SYMBOL.REFRESH+" Reset")
    restart_label.center()
    def reset_cb(e):
        from .view import remove_and_stop_current_activity
        remove_and_stop_current_activity() # make sure current app, like camera, does cleanup, saves progress, stops hardware etc.
        import machine
        if hasattr(machine, 'reset'):
            machine.reset()
        elif hasattr(machine, 'soft_reset'):
            machine.soft_reset() # this causes a SystemExit exception on desktop
        else:
            print("Warning: machine has no reset or soft_reset method available")
    restart_btn.add_event_cb(reset_cb,lv.EVENT.CLICKED,None)
    poweroff_btn=lv.button(drawer)
    poweroff_btn.set_size(lv.pct(45),lv.pct(20))
    poweroff_btn.align(lv.ALIGN.BOTTOM_RIGHT,0,0)
    poweroff_label=lv.label(poweroff_btn)
    poweroff_label.set_text(lv.SYMBOL.POWER+" Off")
    poweroff_label.center()
    def poweroff_cb(e):
        print("Power off action...")
        from .view import remove_and_stop_current_activity
        remove_and_stop_current_activity() # make sure current app, like camera, does cleanup, saves progress, stops hardware etc.
        import sys
        if sys.platform == "esp32":
            #On ESP32, there's no power off but there is a forever sleep
            import machine
            # DON'T configure BOOT button (Pin 0) as wake-up source because it wakes up immediately.
            # Luckily, the RESET button can be used to wake it up.
            #wake_pin = machine.Pin(0, machine.Pin.IN, machine.Pin.PULL_UP)  # Pull-up enabled, active low
            #import esp32
            #esp32.wake_on_ext0(pin=wake_pin, level=esp32.WAKEUP_ALL_LOW)
            print("Entering deep sleep...")
            machine.deepsleep() # sleep forever
        else: # assume unix:
            lv.deinit() # Deinitialize LVGL (if supported)
            sys.exit(0)
    poweroff_btn.add_event_cb(poweroff_cb,lv.EVENT.CLICKED,None)
    # Add invisible padding at the bottom to make the drawer scrollable
    l2 = lv.label(drawer)
    l2.set_text("\n")
    l2.set_pos(0,get_display_height())


def drawer_scroll_callback(event):
    global scroll_start_y
    event_code=event.get_code()
    x, y = mpos.ui.get_pointer_xy()
    #name = mpos.ui.get_event_name(event_code)
    #print(f"drawer_scroll: code={event_code}, name={name}, ({x},{y})")
    if event_code == lv.EVENT.SCROLL_BEGIN and scroll_start_y == None:
        scroll_start_y = y
        #print(f"scroll_starts at: {x},{y}")
    elif event_code == lv.EVENT.SCROLL and scroll_start_y != None:
        diff = y - scroll_start_y
        #print(f"scroll distance: {diff}")
        if diff < -NOTIFICATION_BAR_HEIGHT:
            close_drawer()
    elif event_code == lv.EVENT.SCROLL_END:
        scroll_start_y = None
