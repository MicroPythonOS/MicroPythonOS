
print("matouch_esp32_s3_2_8.py initialization")
# Hardware initialization for Makerfabs MaTouch ESP32-S3 SPI 2.8" with Camera
# Manufacturer's website: https://www.makerfabs.com/matouch-esp32-s3.html
# Hardware Specifications:
# - MCU: ESP32-S3 with 16MB Flash, 8MB Octal PSRAM
# - Display: 2.8" IPS LCD, 320x240 resolution, ST7789 driver, SPI interface
# - Touch: GT911 capacitive touch controller (5-point), I2C interface
# - Camera: OV3660 (3MP, up to 2048x1536)
# - No IMU sensor (unlike Fri3d and Waveshare boards)
# - No NeoPixel LEDs
# - No buzzer or I2S audio

from micropython import const
import st7789
import lcd_bus
import machine
import gt911
import i2c

import lvgl as lv
import task_handler

import mpos.ui

# Pin configuration for Display (SPI)
# Correct pins from hardware schematic
SPI_BUS = 1
SPI_FREQ = 40000000
LCD_SCLK = 14
LCD_MOSI = 13
LCD_MISO = 12
LCD_DC = 21
LCD_CS = 15
LCD_RST = -1
LCD_BL = 48

# Pin configuration for Touch (I2C)
# Correct pins from hardware schematic:
# TOUCH_SDA = 39, TOUCH_SCL = 38, TOUCH_INT = 40, TOUCH_RST = 1
I2C_BUS = 0
I2C_FREQ = 400000
TP_SDA = 39
TP_SCL = 38
TP_INT = 40
TP_RST = 1

# Display resolution
TFT_HOR_RES = 320
TFT_VER_RES = 240

# Initialize SPI bus for display
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
    cs=LCD_CS,
)

# Allocate frame buffers
# Buffer size calculation: 2 bytes per pixel (RGB565) * width * height / divisor
# Using 28800 bytes (same as Waveshare and Fri3d) for good performance
_BUFFER_SIZE = const(28800)
fb1 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)

# Initialize ST7789 display
mpos.ui.main_display = st7789.ST7789(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=TFT_HOR_RES,
    display_height=TFT_VER_RES,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=st7789.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
    reset_pin=LCD_RST,
    backlight_pin=LCD_BL,
    backlight_on_state=st7789.STATE_PWM,
)

mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(100)

# Touch handling:
i2c_bus = i2c.I2C.Bus(host=I2C_BUS, scl=TP_SCL, sda=TP_SDA, freq=I2C_FREQ, use_locks=False)
touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=gt911.I2C_ADDR, reg_bits=gt911.BITS)
indev = gt911.GT911(touch_dev)

# Initialize LVGL
lv.init()

# Set display rotation if needed (adjust based on physical orientation)
# mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._0)

# === BATTERY VOLTAGE MONITORING ===
# Note: MaTouch ESP32-S3 battery monitoring configuration may vary
# This is a placeholder - adjust ADC pin and conversion formula based on actual hardware
from mpos import BatteryManager

def adc_to_voltage(adc_value):
    """
    Convert raw ADC value to battery voltage.
    Currently uses simple linear scaling: voltage = adc * 0.00262
    
    This should be calibrated with actual battery voltages and ADC readings.
    To calibrate: measure actual battery voltages and corresponding ADC readings,
    then fit a linear or polynomial function.
    """
    return adc_value * 0.00262

# Note: Adjust ADC pin number based on actual hardware schematic
# BatteryManager.init_adc(5, adc_to_voltage)

# === AUDIO HARDWARE ===
# Note: MaTouch ESP32-S3 has no buzzer or I2S audio hardware
# AudioManager will not be initialized

# === LED HARDWARE ===
# Note: MaTouch ESP32-S3 has no NeoPixel LEDs
# LightsManager will not be initialized (functions will return False)

# === SENSOR HARDWARE ===
# Note: MaTouch ESP32-S3 has no IMU sensor
# SensorManager will not be initialized

# === CAMERA HARDWARE ===
from mpos import CameraManager

# MaTouch ESP32-S3 has OV3660 camera (3MP, up to 2048x1536)
# Camera pins are available but initialization is handled by the camera driver
CameraManager.add_camera(CameraManager.Camera(
    lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
    name="OV3660",
    vendor="OmniVision"
))

print("matouch_esp32_s3_2_8.py finished")
print("Board capabilities:")
print("  - Display: 320x240 ST7789 with GT911 touch")
print("  - Camera: OV3660 (3MP)")
print("  - No IMU sensor")
print("  - No LEDs")
print("  - No audio hardware")
