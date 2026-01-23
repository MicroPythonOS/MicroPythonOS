# Hardware initialization for ESP32-S3-Touch-LCD-2
# Manufacturer's website at https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-2
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
LCD_SCLK = 39
LCD_MOSI = 38
LCD_MISO = 40
LCD_DC = 42
LCD_CS = 45
LCD_BL = 1

I2C_BUS = 0
I2C_FREQ = 400000
TP_SDA = 48
TP_SCL = 47
TP_ADDR = 0x15
TP_REGBITS = 8

TFT_HOR_RES=320
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
    cs=LCD_CS,
)

 # lv.color_format_get_size(lv.COLOR_FORMAT.RGB565) = 2 bytes per pixel * 320 * 240 px = 153600 bytes
 # The default was /10 so 15360 bytes.
 # /2 = 76800 shows something on display and then hangs the board
 # /2 = 38400 works and pretty high framerate but camera gets ESP_FAIL
 # /2 = 19200 works, including camera at 9FPS
 # 28800 is between the two and still works with camera!
 # 30720 is /5 and is already too much
_BUFFER_SIZE = const(28800)
fb1 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)

mpos.ui.main_display = st7789.ST7789(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=TFT_VER_RES,
    display_height=TFT_HOR_RES,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=st7789.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
    backlight_pin=LCD_BL,
    backlight_on_state=st7789.STATE_PWM,
)
mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(100)

# Touch handling:
i2c_bus = i2c.I2C.Bus(host=I2C_BUS, scl=TP_SCL, sda=TP_SDA, freq=I2C_FREQ, use_locks=False)
touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=TP_ADDR, reg_bits=TP_REGBITS)
indev=cst816s.CST816S(touch_dev,startup_rotation=lv.DISPLAY_ROTATION._180) # button in top left, good

lv.init()
mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._90) # must be done after initializing display and creating the touch drivers, to ensure proper handling

# Battery voltage ADC measuring
import mpos.battery_voltage

def adc_to_voltage(adc_value):
    """
    Convert raw ADC value to battery voltage.
    Currently uses simple linear scaling: voltage = adc * 0.00262

    This could be improved with calibration data similar to Fri3d board.
    To calibrate: measure actual battery voltages and corresponding ADC readings,
    then fit a linear or polynomial function.
    """
    return adc_value * 0.00262

mpos.battery_voltage.init_adc(5, adc_to_voltage)

# On the Waveshare ESP32-S3-Touch-LCD-2, the camera is hard-wired to power on,
# so it needs a software power off to prevent it from staying hot all the time and quickly draining the battery.
try:
    from machine import Pin, I2C
    i2c = I2C(1, scl=Pin(16), sda=Pin(21))  # Adjust pins and frequency
    # Warning: don't do an i2c scan because it confuses the camera!
    camera_addr = 0x3C # for OV5640
    reg_addr = 0x3008
    reg_high = (reg_addr >> 8) & 0xFF  # 0x30
    reg_low = reg_addr & 0xFF         # 0x08
    power_off_command = 0x42 # Power off command
    i2c.writeto(camera_addr, bytes([reg_high, reg_low, power_off_command]))
except Exception as e:
    print(f"Warning: powering off camera got exception: {e}")

# === AUDIO HARDWARE: Waveshare board has no buzzer or I2S audio so no need to initialize.

# === LED HARDWARE ===
# Note: Waveshare board has no NeoPixel LEDs
# LightsManager will not be initialized (functions will return False)

# === SENSOR HARDWARE ===
from mpos import SensorManager

# IMU is on I2C0 (same bus as touch): SDA=48, SCL=47, addr=0x6B
# i2c_bus was created on line 75 for touch, reuse it for IMU
SensorManager.init(i2c_bus, address=0x6B, mounted_position=SensorManager.FACING_EARTH)

# === CAMERA HARDWARE ===
from mpos import CameraManager

# Waveshare ESP32-S3-Touch-LCD-2 has OV5640 camera
CameraManager.add_camera(CameraManager.Camera(
    lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
    name="OV5640",
    vendor="OmniVision"
))

print("waveshare_esp32_s3_touch_lcd_2.py finished")
