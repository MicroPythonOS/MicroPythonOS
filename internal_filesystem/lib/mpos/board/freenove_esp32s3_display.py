print("freenove_esp32s3_display.py initialization")
# Hardware initialization for Freenove ESP32-S3 Display (FNK0104)
# Manufacturer's website: https://github.com/Freenove/Freenove_ESP32_S3_Display
# Hardware Specifications (confirmed from TFT_eSPI_Setups/FNK0104A_2.8_240x320_ILI9341.h
# and official Freenove sketches, and ES3C28P_ES2N28P_Specification_V1.0.pdf):
# - MCU: ESP32-S3 (ES3C28P), 16MB Flash, 8MB PSRAM
# - Display: 2.8" ILI9341V 320x240, SPI (ILI9341_2 variant), BGR, inversion on
# - Touch: FT6336G capacitive touch, I2C addr 0x38, SDA=16, SCL=15
# - NeoPixel: WS2812B, 1 LED, GPIO 42
# - Button: GPIO 0 (INPUT_PULLUP)
# - Battery ADC: GPIO 9 (voltage divider 2:1 → volts = adcMillivolts × 2.0 / 1000)
# - SD Card: SDMMC 4-bit (CLK=38, CMD=40, D0=39, D1=41, D2=48, D3=47)
# - Audio: ES8311 codec (I2C SDA=16/SCL=15, I2S MCK=4/BCK=5/DOUT=8/DIN=6/WS=7)
#          FM8002E amplifier (enable pin GPIO 1, LOW=enabled)
# - No IMU

import time

import drivers.display.ili9341 as ili9341
import i2c
import lcd_bus
import lvgl as lv
import machine
import mpos.ui
import pointer_framework
from machine import Pin
from micropython import const
from mpos import BatteryManager, InputManager

# Display SPI pins (confirmed from official FNK0104 TFT_eSPI setup file)
SPI_BUS  = const(1)
SPI_FREQ = const(40000000)
LCD_MOSI = const(11)
LCD_MISO = const(13)
LCD_SCLK = const(12)
LCD_CS   = const(10)
LCD_DC   = const(46)
LCD_BL   = const(45)
# LCD_RST = -1 (tied to 3.3V / board RST, no software reset needed)

# Touch I2C pins (confirmed from official FT6336U sketch)
TOUCH_SDA = const(16)
TOUCH_SCL = const(15)
TOUCH_I2C_FREQ = const(400000)

# Display resolution
TFT_WIDTH  = const(240)
TFT_HEIGHT = const(320)

# ==============================
# Step 1: Display (ILI9341V, SPI)
# ==============================
print("freenove_esp32s3_display.py: init SPI display")
try:
    spi_bus = machine.SPI.Bus(host=SPI_BUS, mosi=LCD_MOSI, miso=LCD_MISO, sck=LCD_SCLK)
except Exception as e:
    print(f"Error initializing SPI bus: {e}")
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()

display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus,
    freq=SPI_FREQ,
    dc=LCD_DC,
    cs=LCD_CS,
)

_BUFFER_SIZE = const(28800)  # 240 * 60 * 2 bytes (RGB565)
fb1 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)

mpos.ui.main_display = ili9341.ILI9341(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=TFT_WIDTH,
    display_height=TFT_HEIGHT,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=ili9341.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
    backlight_pin=LCD_BL,
    backlight_on_state=ili9341.STATE_HIGH,
)

mpos.ui.main_display.init(2)  # ILI9341_2 (alternative) init sequence, same as M5Stack
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(100)
mpos.ui.main_display.set_color_inversion(True)  # TFT_INVERSION_ON in official setup

# ==============================
# Step 2: Touch (FT6336G)
# ==============================
print("freenove_esp32s3_display.py: init touch (FT6336G)")
import drivers.indev.ft6x36 as ft6x36

i2c_bus = i2c.I2C.Bus(host=0, sda=TOUCH_SDA, scl=TOUCH_SCL, freq=TOUCH_I2C_FREQ, use_locks=False)
touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=ft6x36.I2C_ADDR, reg_bits=ft6x36.BITS)
try:
    indev = ft6x36.FT6x36(touch_dev, startup_rotation=pointer_framework.lv.DISPLAY_ROTATION._0)
    InputManager.register_indev(indev)
except Exception as e:
    print(f"Touch init got exception: {e}")

mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._270)  # landscape

# ==============================
# Step 3: Button (GPIO 0)
# ==============================
print("freenove_esp32s3_display.py: init button")

btn_boot = Pin(0, Pin.IN, Pin.PULL_UP)

REPEAT_INITIAL_DELAY_MS = 300
REPEAT_RATE_MS = 100
last_key = None
last_state = lv.INDEV_STATE.RELEASED
key_press_start = 0
last_repeat_time = 0

# Warning: This gets called several times per second, and if it outputs continuous debugging
# on the serial line, that will break tools like mpremote from working properly to upload
# new files over the serial line, thus needing a reflash.
def keypad_read_cb(indev, data):
    global last_key, last_state, key_press_start, last_repeat_time

    current_time = time.ticks_ms()
    current_key = lv.KEY.ESC if btn_boot.value() == 0 else None

    if current_key is None:
        data.key = last_key if last_key else lv.KEY.ESC
        data.state = lv.INDEV_STATE.RELEASED
        last_key = None
        last_state = lv.INDEV_STATE.RELEASED
        key_press_start = 0
        last_repeat_time = 0
    elif last_key is None or current_key != last_key:
        data.key = current_key
        data.state = lv.INDEV_STATE.PRESSED
        last_key = current_key
        last_state = lv.INDEV_STATE.PRESSED
        key_press_start = current_time
        last_repeat_time = current_time
    else:
        elapsed = time.ticks_diff(current_time, key_press_start)
        since_last_repeat = time.ticks_diff(current_time, last_repeat_time)
        if elapsed >= REPEAT_INITIAL_DELAY_MS and since_last_repeat >= REPEAT_RATE_MS:
            data.key = current_key
            data.state = lv.INDEV_STATE.PRESSED if last_state == lv.INDEV_STATE.RELEASED else lv.INDEV_STATE.RELEASED
            last_state = data.state
            last_repeat_time = current_time
        else:
            data.state = lv.INDEV_STATE.RELEASED
            last_state = lv.INDEV_STATE.RELEASED

    if last_state == lv.INDEV_STATE.PRESSED and current_key == lv.KEY.ESC:
        mpos.ui.back_screen()

group = lv.group_create()
group.set_default()

btn_indev = lv.indev_create()
btn_indev.set_type(lv.INDEV_TYPE.KEYPAD)
btn_indev.set_read_cb(keypad_read_cb)
btn_indev.set_group(group)
disp = lv.display_get_default()
btn_indev.set_display(disp)
btn_indev.enable(True)
InputManager.register_indev(btn_indev)

# ==============================
# Step 4: Battery (GPIO 9, 2:1 voltage divider)
# ==============================
print("freenove_esp32s3_display.py: init battery")

def adc_to_voltage(adc_millivolts):
    # Schematic uses a 2:1 resistor divider; multiply by 2 and convert mV → V
    return adc_millivolts * 2.0 / 1000.0

BatteryManager.init_adc(9, adc_to_voltage)

# ==============================
# Step 5: SD Card (SDMMC 4-bit)
# ==============================
print("freenove_esp32s3_display.py: init SD card (SDMMC 4-bit)")
import mpos.sdcard
mpos.sdcard.init(cmd_pin=40, clk_pin=38, d0_pin=39, d1_pin=41, d2_pin=48, d3_pin=47)

# ==============================
# Step 6: NeoPixel (WS2812B, 1 LED, GPIO 42)
# ==============================
print("freenove_esp32s3_display.py: init NeoPixel")
import mpos.lights as LightsManager
LightsManager.init(neopixel_pin=42, num_leds=1)

# ==============================
# Step 7: Audio (ES8311 codec)
# TODO: The ES8311 codec requires a non-trivial I2C initialization sequence
# (PLL config, sample rate, bit depth, I2S format) that has no existing driver
# in this codebase. Audio support is deferred to a follow-up.
# For now, keep the FM8002E amplifier disabled (HIGH = off) to save power.
# I2S pins when audio is implemented (confirmed from Sketch_07.1_Music and schematic):
#   MCK=4, BCK=5, WS=7
#   sd=8    (ESP32 TX → codec DAC, playback; schematic labels this "input" from codec's view)
#   sd_in=6 (ESP32 RX ← codec ADC, recording; schematic labels this "output" from codec's view)
# I2C (shared with touch): SDA=16, SCL=15, ES8311 addr=0x18
# ==============================
print("freenove_esp32s3_display.py: amplifier disabled (audio TODO)")
amp_enable = Pin(1, Pin.OUT, value=1)  # HIGH = FM8002E amplifier disabled

# IMU: not present on this board — SensorManager not initialized

print("freenove_esp32s3_display.py finished")
