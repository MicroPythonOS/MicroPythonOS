# LilyGo T-Display non-touch edition

print("lilygo_t_display_s3.py running")

import lcd_bus
import lvgl as lv
import machine
import time

print("lilygo_t_display_s3.py display bus initialization")
try:
    display_bus = lcd_bus.I80Bus(
        dc=7,
        wr=8,
        cs=6,
        data0=39,
        data1=40,
        data2=41,
        data3=42,
        data4=45,
        data5=46,
        data6=47,
        data7=48,
        #reverse_color_bits=False # doesnt seem to do anything?
    )
except Exception as e:
    print(f"Error initializing display bus: {e}")
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()

_BUFFER_SIZE = const(28800)
fb1 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)

import drivers.display.st7789 as st7789
import mpos.ui
mpos.ui.main_display = st7789.ST7789(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=170,
    display_height=320,
    #color_space=lv.COLOR_FORMAT.RGB565, # gives bad colors
    color_space=lv.COLOR_FORMAT.RGB888,
    color_byte_order=st7789.BYTE_ORDER_RGB,
    # rgb565_byte_swap=False, # always False is data_bus.get_lane_count() == 8
    power_pin=9, # Must set RD pin to high, otherwise blank screen as soon as LVGL's task_handler starts
    reset_pin=5,
    reset_state=st7789.STATE_LOW, # needs low: high will not enable the display
    backlight_pin=38, # needed
    backlight_on_state=st7789.STATE_PWM,
    offset_x=0,
    offset_y=35
)
mpos.ui.main_display.set_power(True) # set RD pin to high before the rest, otherwise garbled output
mpos.ui.main_display.init()
mpos.ui.main_display.set_backlight(100) # works

lv.init()
mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._270) # must be done after initializing display and creating the touch drivers, to ensure proper handling
mpos.ui.main_display.set_color_inversion(True)


# Button handling code:
from machine import Pin
btn_a = Pin(0, Pin.IN, Pin.PULL_UP)
btn_b = Pin(14, Pin.IN, Pin.PULL_UP)

# Key repeat configuration
# This whole debounce logic is only necessary because LVGL 9.2.2 seems to have an issue where
# the lv_keyboard widget doesn't handle PRESSING (long presses) properly, it loses focus.
REPEAT_INITIAL_DELAY_MS = 300  # Delay before first repeat
REPEAT_RATE_MS = 100  # Interval between repeats
REPEAT_PREV_BECOMES_BACK = 700 # Long previous press becomes back button
COMBO_GRACE_MS = 60  # Accept near-simultaneous A+B as ENTER
last_key = None
last_state = lv.INDEV_STATE.RELEASED
key_press_start = 0  # Time when key was first pressed
last_repeat_time = 0  # Time of last repeat event
last_a_down_time = 0
last_b_down_time = 0
last_a_pressed = False
last_b_pressed = False

# Read callback
# Warning: This gets called several times per second, and if it outputs continuous debugging on the serial line,
# that will break tools like mpremote from working properly to upload new files over the serial line, thus needing a reflash.
def keypad_read_cb(indev, data):
    global last_key, last_state, key_press_start, last_repeat_time, last_a_down_time, last_b_down_time
    global last_a_pressed, last_b_pressed

    # Check buttons
    current_time = time.ticks_ms()
    btn_a_pressed = btn_a.value() == 0
    btn_b_pressed = btn_b.value() == 0
    if btn_a_pressed and not last_a_pressed:
        last_a_down_time = current_time
    if btn_b_pressed and not last_b_pressed:
        last_b_down_time = current_time
    last_a_pressed = btn_a_pressed
    last_b_pressed = btn_b_pressed

    near_simul = False
    if btn_a_pressed and btn_b_pressed:
        near_simul = True
    elif btn_a_pressed and last_b_down_time and time.ticks_diff(current_time, last_b_down_time) <= COMBO_GRACE_MS:
        near_simul = True
    elif btn_b_pressed and last_a_down_time and time.ticks_diff(current_time, last_a_down_time) <= COMBO_GRACE_MS:
        near_simul = True

    single_press_wait = False
    if btn_a_pressed ^ btn_b_pressed:
        if btn_a_pressed and time.ticks_diff(current_time, last_a_down_time) < COMBO_GRACE_MS:
            single_press_wait = True
        elif btn_b_pressed and time.ticks_diff(current_time, last_b_down_time) < COMBO_GRACE_MS:
            single_press_wait = True

    if near_simul or single_press_wait:
        dt_a = time.ticks_diff(current_time, last_a_down_time) if last_a_down_time else None
        dt_b = time.ticks_diff(current_time, last_b_down_time) if last_b_down_time else None
        print(f"combo guard: a={btn_a_pressed} b={btn_b_pressed} near={near_simul} wait={single_press_wait} dt_a={dt_a} dt_b={dt_b}")

    # While in an on-screen keyboard, PREV button is LEFT and NEXT button is RIGHT
    focus_group = lv.group_get_default()
    focus_keyboard = False
    if focus_group:
        current_focused = focus_group.get_focused()
        if isinstance(current_focused, lv.keyboard):
            #print("focus is on a keyboard")
            focus_keyboard = True

    if near_simul:
        current_key = lv.KEY.ENTER
    elif single_press_wait:
        current_key = None
    elif btn_a_pressed:
        if focus_keyboard:
            current_key = lv.KEY.LEFT
        else:
            current_key = lv.KEY.PREV
    elif btn_b_pressed:
        if focus_keyboard:
            current_key = lv.KEY.RIGHT
        else:
            current_key = lv.KEY.NEXT
    else:
        current_key = None

    if current_key is None:
        # No key pressed
        data.key = last_key if last_key else -1
        data.state = lv.INDEV_STATE.RELEASED
        last_key = None
        last_state = lv.INDEV_STATE.RELEASED
        key_press_start = 0
        last_repeat_time = 0
    elif last_key is None or current_key != last_key:
        print(f"New key press: {current_key}")
        data.key = current_key
        data.state = lv.INDEV_STATE.PRESSED
        last_key = current_key
        last_state = lv.INDEV_STATE.PRESSED
        key_press_start = current_time
        last_repeat_time = current_time
    else:
        print(f"key repeat because current_key {current_key} == last_key {last_key}")
        elapsed = time.ticks_diff(current_time, key_press_start)
        since_last_repeat = time.ticks_diff(current_time, last_repeat_time)
        if elapsed >= REPEAT_INITIAL_DELAY_MS and since_last_repeat >= REPEAT_RATE_MS:
            next_state = lv.INDEV_STATE.PRESSED if last_state == lv.INDEV_STATE.RELEASED else lv.INDEV_STATE.RELEASED
            if current_key == lv.KEY.PREV:
                print("Repeated PREV does not do anything, instead it triggers ESC (back) if long enough")
                if since_last_repeat > REPEAT_PREV_BECOMES_BACK:
                    print("back button trigger!")
                    data.key = lv.KEY.ESC
                    data.state = next_state
                    last_key = current_key
                    last_state = data.state
                    last_repeat_time = current_time
                else:
                    print("repeat PREV ignored because not pressed long enough")
            else:
                print("Send a new PRESSED/RELEASED pair for repeat")
                data.key = current_key
                data.state = next_state
                last_key = current_key
                last_state = data.state
                last_repeat_time = current_time
        else:
            # This doesn't seem to make the key navigation in on-screen keyboards work, unlike on the m5stack_fire...?
            #print("No repeat yet, send RELEASED to avoid PRESSING, which breaks keyboard navigation...")
            data.state = lv.INDEV_STATE.RELEASED
            last_state = lv.INDEV_STATE.RELEASED

    # Handle ESC for back navigation (only on initial PRESSED)
    if data.state == lv.INDEV_STATE.PRESSED and data.key == lv.KEY.ESC:
        mpos.ui.back_screen()


group = lv.group_create()
group.set_default()

# Create and set up the input device
indev = lv.indev_create()
indev.set_type(lv.INDEV_TYPE.KEYPAD)
indev.set_read_cb(keypad_read_cb)
indev.set_group(group) # is this needed? maybe better to move the default group creation to main.py so it's available everywhere...
disp = lv.display_get_default()  # NOQA
indev.set_display(disp)  # different from display
indev.enable(True)  # NOQA
from mpos import InputManager
InputManager.register_indev(indev)

print("lilygo_t_display_s3.py finished")
