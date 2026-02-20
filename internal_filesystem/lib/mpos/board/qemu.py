print("qemu.py running")

import lcd_bus
import lvgl as lv
import machine
import time

import mpos.ui

print("qemu.py display bus initialization")
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
        reverse_color_bits=False # doesnt seem to do anything?
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
# 320x200 => make 320x240 screenshot => it's 240x200 (but the display shows more than 200)
mpos.ui.main_display = st7789.ST7789(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=170,
    display_height=320,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=st7789.BYTE_ORDER_RGB,
    # rgb565_byte_swap=False, # always False is data_bus.get_lane_count() == 8
    reset_pin=5,
    backlight_pin=38,
    backlight_on_state=st7789.STATE_PWM,
)
mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(100)

lv.init()
#mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._90) # must be done after initializing display and creating the touch drivers, to ensure proper handling
mpos.ui.main_display.set_color_inversion(True) # doesnt seem to do anything?

# Button handling code:
from machine import Pin
btn_a = Pin(0, Pin.IN, Pin.PULL_UP)  # 1
btn_b = Pin(14, Pin.IN, Pin.PULL_UP)  # 2
btn_c = Pin(3, Pin.IN, Pin.PULL_UP)  # 3

# Key repeat configuration
# This whole debounce logic is only necessary because LVGL 9.2.2 seems to have an issue where
# the lv_keyboard widget doesn't handle PRESSING (long presses) properly, it loses focus.
REPEAT_INITIAL_DELAY_MS = 300  # Delay before first repeat
REPEAT_RATE_MS = 100  # Interval between repeats
last_key = None
last_state = lv.INDEV_STATE.RELEASED
#key_press_start = 0  # Time when key was first pressed
#last_repeat_time = 0  # Time of last repeat event

# Read callback
# Warning: This gets called several times per second, and if it outputs continuous debugging on the serial line,
# that will break tools like mpremote from working properly to upload new files over the serial line, thus needing a reflash.
def keypad_read_cb(indev, data):
    global last_key, last_state #, key_press_start, last_repeat_time
    since_last_repeat = 0

    # Check buttons
    current_key = None
    current_time = time.ticks_ms()
    if btn_a.value() == 0:
        current_key = lv.KEY.PREV
    elif btn_b.value() == 0:
        current_key = lv.KEY.ENTER
    elif btn_c.value() == 0:
        current_key = lv.KEY.NEXT

    if (btn_a.value() == 0) and (btn_c.value() == 0):
        current_key = lv.KEY.ESC

    if current_key:
        if current_key != last_key:
            # New key press
            data.key = current_key
            data.state = lv.INDEV_STATE.PRESSED
            last_key = data.key
            last_state = data.state
            #key_press_start = current_time
            #last_repeat_time = current_time
        else:
            print(f"should {current_key} be repeated?")
    else:
        # No key pressed
        data.key = last_key if last_key else lv.KEY.ENTER
        data.state = lv.INDEV_STATE.RELEASED
        last_key = None
        last_state = data.state
        #key_press_start = 0
        #last_repeat_time = 0

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

print("qemu.py finished")
