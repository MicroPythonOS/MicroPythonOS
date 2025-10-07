# Hardware initialization for Fri3d Camp 2024 Badge
current_hardware = "fri3d-2024"

from machine import Pin, SPI
import st7789 
import lcd_bus
import machine
import cst816s
import i2c

import lvgl as lv
import task_handler

import mpos.ui

# Pin configuration
SPI_BUS = 2
SPI_FREQ = 40000000
#SPI_FREQ = 20000000 # also works but I guess higher is better
LCD_SCLK = 7
LCD_MOSI = 6
LCD_MISO = 8
LCD_DC = 4
LCD_CS = 5
#LCD_BL = 1 # backlight can't be controlled on this hardware
LCD_RST = 48

TFT_HOR_RES=296
TFT_VER_RES=240

spi_bus = machine.SPI.Bus(
    host=SPI_BUS,
    mosi=LCD_MOSI,
    miso=LCD_MISO,
    sck=LCD_SCLK
)
display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus,
    freq=SPI_FREQ,
    dc=LCD_DC,
    cs=LCD_CS
)

# lv.color_format_get_size(lv.COLOR_FORMAT.RGB565) = 2 bytes per pixel * 320 * 240 px = 153600 bytes
# The default was /10 so 15360 bytes.
# /2 = 76800 shows something on display and then hangs the board
# /2 = 38400 works and pretty high framerate but camera gets ESP_FAIL
# /2 = 19200 works, including camera at 9FPS
# 28800 is between the two and still works with camera!
# 30720 is /5 and is already too much
#_BUFFER_SIZE = const(28800)
buffersize = const(28800)
fb1 = display_bus.allocate_framebuffer(buffersize, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(buffersize, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)

STATE_HIGH = 1
STATE_LOW = 0

# see ./lvgl_micropython/api_drivers/py_api_drivers/frozen/display/display_driver_framework.py
display = st7789.ST7789(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=TFT_VER_RES,
    display_height=TFT_HOR_RES,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=st7789.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
    reset_pin=LCD_RST,
    reset_state=STATE_LOW
)

display.init()
display.set_power(True)
display.set_backlight(100)

display.set_color_inversion(False)

lv.init()
display.set_rotation(lv.DISPLAY_ROTATION._270) # must be done after initializing display and creating the touch drivers, to ensure proper handling
display.set_params(0x36, bytearray([0x28]))

# Button and joystick handling code:
from machine import ADC, Pin

btn_x = Pin(38, Pin.IN, Pin.PULL_UP) # X
btn_y = Pin(41, Pin.IN, Pin.PULL_UP) # Y
btn_a = Pin(39, Pin.IN, Pin.PULL_UP) # A
btn_b = Pin(40, Pin.IN, Pin.PULL_UP) # B
btn_start = Pin(0, Pin.IN, Pin.PULL_UP) # START
btn_menu = Pin(45, Pin.IN, Pin.PULL_UP) # START

ADC_KEY_MAP = [
    {'key': 'UP', 'unit': 1, 'channel': 2, 'min': 3072, 'max': 4096},
    {'key': 'DOWN', 'unit': 1, 'channel': 2, 'min': 0, 'max': 1024},
    {'key': 'RIGHT', 'unit': 1, 'channel': 0, 'min': 3072, 'max': 4096},
    {'key': 'LEFT', 'unit': 1, 'channel': 0, 'min': 0, 'max': 1024},
]

# Initialize ADC for the two channels
adc_up_down = ADC(Pin(3))  # ADC1_CHANNEL_2 (GPIO 33)
adc_up_down.atten(ADC.ATTN_11DB)  # 0-3.3V range
adc_left_right = ADC(Pin(1))  # ADC1_CHANNEL_0 (GPIO 36)
adc_left_right.atten(ADC.ATTN_11DB)  # 0-3.3V range

def read_joystick():
    # Read ADC values
    val_up_down = adc_up_down.read()
    val_left_right = adc_left_right.read()

    # Check each key's range
    for mapping in ADC_KEY_MAP:
        adc_val = val_up_down if mapping['channel'] == 2 else val_left_right
        if mapping['min'] <= adc_val <= mapping['max']:
            return mapping['key']
    return None  # No key triggered


# Read callback
# Warning: This gets called several times per second, and if it outputs continuous debugging on the serial line,
# that will break tools like mpremote from working properly to upload new files over the serial line, thus needing a reflash.
def keypad_read_cb(indev, data):
    data.continue_reading = False  # No more data to read
    # Check GPIOs and set key/state (only one key at a time)
    if btn_x.value() == 0:
        data.key = lv.KEY.ESC
        data.state = lv.INDEV_STATE.PRESSED
        mpos.ui.back_screen()
    elif btn_y.value() == 0:
        data.key = lv.KEY.ESC
        data.state = lv.INDEV_STATE.PRESSED
        mpos.ui.back_screen()
    elif btn_a.value() == 0:
        #print("A pressed")
        data.key = lv.KEY.ENTER
        data.state = lv.INDEV_STATE.PRESSED
    elif btn_b.value() == 0:
        #print("B pressed")
        data.key = lv.KEY.ENTER
        data.state = lv.INDEV_STATE.PRESSED
    elif btn_menu.value() == 0:
        data.key = lv.KEY.HOME
        data.state = lv.INDEV_STATE.PRESSED
    elif btn_start.value() == 0:
        data.key = lv.KEY.END
        data.state = lv.INDEV_STATE.PRESSED
    else:
        data.state = lv.INDEV_STATE.RELEASED
    if data.state == lv.INDEV_STATE.RELEASED:
        joystick = read_joystick()
        if joystick == "LEFT":
            data.key = lv.KEY.PREV
            data.state = lv.INDEV_STATE.PRESSED
        elif joystick == "RIGHT":
            data.key = lv.KEY.NEXT
            data.state = lv.INDEV_STATE.PRESSED
        elif joystick == "UP":
            data.key = lv.KEY.UP
            data.state = lv.INDEV_STATE.PRESSED
        elif joystick == "DOWN":
            data.key = lv.KEY.DOWN
            data.state = lv.INDEV_STATE.PRESSED
        else:
            data.state = lv.INDEV_STATE.RELEASED


group = lv.group_create()
group.set_default()

# Create and set up the input device
indev = lv.indev_create()
indev.set_type(lv.INDEV_TYPE.KEYPAD)
indev.set_read_cb(keypad_read_cb)
indev.set_group(group)
disp = lv.display_get_default()  # NOQA
indev.set_display(disp)  # different from display
indev.enable(True)  # NOQA

print("boot.py finished")
