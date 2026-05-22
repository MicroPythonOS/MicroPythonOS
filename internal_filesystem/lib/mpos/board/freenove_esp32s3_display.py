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
# - Battery ADC: GPIO 9 (200K/200K voltage divider → V_bat = raw_adc × 4.06/2398, calibrated at raw=2398 → 4.06V)
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
TOUCH_RST = const(18)  # FT6336G reset pin (active low)

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
    backlight_on_state=ili9341.STATE_PWM,
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

# Hardware reset of FT6336G via RST pin (GPIO18, active low).
# Freenove's official FT6336U library drives RST low for 10ms then waits
# for the chip to stabilize before any I2C communication.
touch_rst = Pin(TOUCH_RST, Pin.OUT)
touch_rst.value(0)
time.sleep_ms(10)
touch_rst.value(1)
time.sleep_ms(200)  # chip needs time to fully initialize after reset

# Use a plain machine.I2C and override _bus in the LVGL I2C.Bus wrapper.
# This avoids an IDF I2C driver conflict: fail_save_i2c() in board detection
# leaves machine.I2C(0) open on the same pins, and creating i2c.I2C.Bus(host=0)
# on top of it can leave subsequent write_readinto calls returning ENODEV.
# This is the same pattern used by m5stack_core2 (also FT6x36 touch).
machine_i2c = machine.I2C(0, sda=Pin(TOUCH_SDA), scl=Pin(TOUCH_SCL), freq=TOUCH_I2C_FREQ)
i2c_bus = i2c.I2C.Bus(host=0, sda=TOUCH_SDA, scl=TOUCH_SCL, freq=TOUCH_I2C_FREQ, use_locks=False)
i2c_bus._bus = machine_i2c

touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=ft6x36.I2C_ADDR, reg_bits=ft6x36.BITS)
try:
    indev = ft6x36.FT6x36(touch_dev, startup_rotation=pointer_framework.lv.DISPLAY_ROTATION._180)
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

def adc_to_voltage(raw_adc):
    # Schematic uses equal 200K/200K resistor divider (1:2), so V_bat = V_pin * 2.
    # ATTN_11DB on the ESP32-S3 allows reading up to ~3.5V (used as reference here).
    # TODO: switch to adc.read_uv() for per-chip factory calibration.
    return raw_adc * (3.5 / 4095) * 2

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
# Step 7: Audio (ES8311 codec + FM8002E amplifier)
# I2S pins (confirmed from Freenove Sketch_07.1_Music and schematic):
#   MCK=4  (MCLK to codec — driven by PWM during playback/recording)
#   BCK=5  (BCLK, I2S bit clock)
#   WS=7   (LRCK, I2S word select)
#   sd=8   (ESP32 I2S TX → ES8311 SDIN → DAC → speaker)
#   sd_in=6 (ES8311 SDOUT → ADC → ESP32 I2S RX → recording)
# I2C addr 0x18, shared bus with touch (SDA=16, SCL=15)
# ==============================
print("freenove_esp32s3_display.py: init audio (ES8311 + FM8002E)")

# Initialise the ES8311 codec over the shared I2C bus.
# machine_i2c is already open on SDA=16, SCL=15 from the touch init above.
_es8311 = None
try:
    import drivers.codec.es8311 as es8311_drv
    _es8311 = es8311_drv.ES8311(machine_i2c)
except Exception as e:
    print(f"ES8311 init failed: {e}")

# FM8002E speaker amplifier enable pin (GPIO1: LOW=enabled, HIGH=disabled).
# Start disabled at boot — enabled only around active playback to prevent ring noise.
_amp_enable = Pin(1, Pin.OUT, value=1)  # HIGH = FM8002E amplifier disabled


def _audio_on_open():
    """Called after MCLK starts and before I2S init. Enables amp and unmutes DAC."""
    _amp_enable.value(0)          # LOW = enable FM8002E amplifier
    if _es8311:
        time.sleep_ms(10)         # let amp rail settle before unmuting
        _es8311.dac_mute(False)   # release DAC soft-mute


def _audio_on_close():
    """Called before I2S deinit. Mutes DAC then disables amp to suppress pops."""
    if _es8311:
        _es8311.dac_mute(True)    # soft-mute DAC first (ramp prevents click)
        time.sleep_ms(20)         # wait for ramp to complete
    _amp_enable.value(1)          # HIGH = disable FM8002E amplifier


# Register I2S audio devices with AudioManager.
# Both output and input share MCLK (GPIO4), BCLK (GPIO5), and WS (GPIO7).
# Only one I2S session can be active at a time; AudioManager handles conflicts.
from mpos import AudioManager

AudioManager.add(
    AudioManager.Output(
        name="Speaker",
        kind="i2s",
        channels=1,
        i2s_pins={
            'mck': 4,   # MCLK — PWM-driven at 256 × sample_rate during playback
            'sck': 5,   # BCLK
            'ws':  7,   # LRCK
            'sd':  8,   # I2S TX (ESP32 → ES8311 DAC)
        },
        on_open=_audio_on_open,
        on_close=_audio_on_close,
    )
)

AudioManager.add(
    AudioManager.Input(
        name="Microphone",
        kind="i2s",
        channels=1,
        i2s_pins={
            'mck':   4,  # MCLK — PWM-driven at 256 × sample_rate during recording
            'sck':   5,  # BCLK
            'ws':    7,  # LRCK
            'sd_in': 6,  # I2S RX (ES8311 ADC → ESP32)
        },
        preferred_sample_rate=16000,
    )
)

# IMU: not present on this board — SensorManager not initialized

print("freenove_esp32s3_display.py finished")
