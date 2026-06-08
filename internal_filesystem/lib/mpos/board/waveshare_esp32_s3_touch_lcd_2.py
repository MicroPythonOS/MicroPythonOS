import logging
logger = logging.getLogger(__name__)

# Hardware initialization for ESP32-S3-Touch-LCD-2
# Manufacturer's website at https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-2

import time

import drivers.display.st7789 as st7789
import drivers.indev.cst816s as cst816s
import i2c
import lcd_bus
import lvgl as lv
import machine
import mpos.ui
from mpos import InputManager

# Pin configuration
SPI_BUS = 2
SPI_FREQ = 40000000
LCD_SCLK = 39
LCD_MOSI = 38
LCD_MISO = 40
LCD_DC = 42
LCD_CS = 45
LCD_BL = 1

if __debug__: logger.debug("machine.SPI.Bus() initialization")
try:
    spi_bus = machine.SPI.Bus(host=SPI_BUS, mosi=LCD_MOSI, miso=LCD_MISO, sck=LCD_SCLK)
except Exception as e:
    logger.error("Error initializing SPI bus: %s", e)
    logger.error("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()


display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus,
    freq=SPI_FREQ,
    dc=LCD_DC,
    cs=LCD_CS,
)

_BUFFER_SIZE = const(320 * 45 * 2) # 28800
fb1 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)

mpos.ui.main_display = st7789.ST7789(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=240,
    display_height=320,
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
i2c_bus = i2c.I2C.Bus(host=0, scl=47, sda=48, freq=400000, use_locks=False)
touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=0x15, reg_bits=8)
indev = cst816s.CST816S(touch_dev, startup_rotation=lv.DISPLAY_ROTATION._180)
InputManager.register_indev(indev)

mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._90)

# Battery voltage ADC measuring
from mpos import BatteryManager

def adc_to_voltage(adc_value):
    return adc_value * 0.00262

BatteryManager.init_adc(5, adc_to_voltage)

# On the Waveshare ESP32-S3-Touch-LCD-2, the camera is hard-wired to power on,
# so it needs a software power off to prevent it from staying hot all the time and quickly draining the battery.
try:
    from machine import Pin, I2C
    i2c = I2C(1, scl=Pin(16), sda=Pin(21))
    camera_addr = 0x3C # for OV5640
    reg_addr = 0x3008
    reg_high = (reg_addr >> 8) & 0xFF
    reg_low = reg_addr & 0xFF
    power_off_command = 0x42
    i2c.writeto(camera_addr, bytes([reg_high, reg_low, power_off_command]))
except Exception as e:
    logger.warning("powering off camera got exception: %s", e)

# === SENSOR HARDWARE ===
from mpos import SensorManager

# IMU is on I2C0 (same bus as touch): SDA=48, SCL=47, addr=0x6B
SensorManager.init(i2c_bus, address=0x6B, mounted_position=SensorManager.FACING_EARTH)

# === CAMERA HARDWARE ===
from mpos import CameraManager

def init_cam(width, height, colormode):
    toreturn = None
    try:
        from camera import Camera, GrabMode, PixelFormat

        frame_size = CameraManager.resolution_to_framesize(width, height)
        if __debug__: logger.debug("init_internal_cam: Using FrameSize %s for %sx%s", frame_size, width, height)

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                cam = Camera(
                        data_pins=[12,13,15,11,14,10,7,2],
                        vsync_pin=6,
                        href_pin=4,
                        sda_pin=21,
                        scl_pin=16,
                        pclk_pin=9,
                        xclk_pin=8,
                        xclk_freq=20000000,
                        powerdown_pin=-1,
                        reset_pin=-1,
                        pixel_format=PixelFormat.RGB565 if colormode else PixelFormat.GRAYSCALE,
                        frame_size=frame_size,
                        grab_mode=GrabMode.LATEST,
                        fb_count=1
                    )
                cam.set_vflip(True)
                toreturn=cam
                break
            except Exception as e:
                if attempt < max_attempts-1:
                    if __debug__: logger.debug("init_cam attempt %s failed: %s, retrying...", attempt, e)
                else:
                    logger.error("init_cam final exception: %s", e)
                    break
    except Exception as e:
        logger.error("init_cam exception: %s", e)

    return toreturn

def deinit_cam(cam):
    cam.deinit()
    try:
        from machine import Pin, I2C
        i2c = I2C(1, scl=Pin(16), sda=Pin(21))
        camera_addr = 0x3C
        reg_addr = 0x3008
        reg_high = (reg_addr >> 8) & 0xFF
        reg_low = reg_addr & 0xFF
        power_off_command = 0x42
        i2c.writeto(camera_addr, bytes([reg_high, reg_low, power_off_command]))
    except Exception as e:
        logger.warning("powering off camera got exception: %s", e)
    import time
    time.sleep_ms(100)

def capture_cam(cam_obj, colormode):
    return cam_obj.capture()

def apply_cam_settings(cam_obj, prefs):
    return CameraManager.ov_apply_camera_settings(cam_obj, prefs)

CameraManager.add_camera(CameraManager.Camera(
    lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
    name="OV5640",
    vendor="OmniVision",
    init=init_cam,
    deinit=deinit_cam,
    capture=capture_cam,
    apply_settings=apply_cam_settings,
    rotation_degrees=-90
))

if __debug__: logger.debug("finished")
