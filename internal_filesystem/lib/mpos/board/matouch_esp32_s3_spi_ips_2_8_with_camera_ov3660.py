import logging
logger = logging.getLogger(__name__)

# Hardware initialization for Makerfabs MaTouch ESP32-S3 SPI 2.8" with Camera
# Manufacturer's website: https://www.makerfabs.com/matouch-esp32-s3-spi-ips-2-8-with-camera-ov3660.html
# Hardware Specifications:
# - MCU: ESP32-S3 with 16MB Flash, 8MB Octal PSRAM
# - Display: 2.8" IPS LCD, 320x240 resolution, ST7789 driver, SPI interface
# - Touch: GT911 capacitive touch controller (5-point), I2C interface
# - Camera: OV3660 (3MP, up to 2048x1536)
# - No IMU sensor (unlike Fri3d and Waveshare boards)
# - No NeoPixel LEDs
# - No buzzer or I2S audio

from micropython import const
import drivers.display.st7789 as st7789
import lcd_bus
import machine

import lvgl as lv

import mpos.ui

# Pin configuration for Display (SPI)
SPI_BUS = 1
SPI_FREQ = 40000000
LCD_SCLK = 14
LCD_MOSI = 13
LCD_MISO = 12
LCD_DC = 21
LCD_CS = 15
LCD_BL = 48

I2C_FREQ = 400000

TFT_HOR_RES = 320
TFT_VER_RES = 240

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

# Touch handling
def init_touch():
    try:
        import i2c
        i2c_bus = i2c.I2C.Bus(host=0, scl=38, sda=39, freq=I2C_FREQ, use_locks=False)
        import drivers.indev.gt911 as gt911
        touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=gt911.I2C_ADDR, reg_bits=gt911.BITS)
        indev = gt911.GT911(touch_dev, reset_pin=1, interrupt_pin=40, debug=False)
        from mpos import InputManager
        InputManager.register_indev(indev)
    except Exception as e:
        logger.error("Touch init got exception: %s", e)
init_touch()

# IO0 Button interrupt handler
def io0_interrupt_handler(pin):
    if __debug__: logger.debug("IO0 button pressed!")
    from mpos import back_screen
    back_screen()

io0_pin = machine.Pin(0, machine.Pin.IN, machine.Pin.PULL_UP)
io0_pin.irq(trigger=machine.Pin.IRQ_FALLING, handler=io0_interrupt_handler)

lv.init()

# Initialize SD card in SDIO mode
from mpos import sdcard
sdcard.init(cmd_pin=2,clk_pin=42,d0_pin=41)

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
                    data_pins=[7,5,4,6,16,8,3,46],
                    vsync_pin=11,
                    href_pin=10,
                    sda_pin=39,
                    scl_pin=38,
                    pclk_pin=17,
                    xclk_pin=9,
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

        if toreturn:
            try:
                from mpos import InputManager
                indev = InputManager.list_indevs()[0]
                indev.enable(False)
                InputManager.unregister_indev(indev)
                if __debug__: logger.debug("input disabled")
            except Exception as e:
                logger.error("init_cam: disabling indev got exception: %s", e)
            init_touch()

    except Exception as e:
        logger.error("init_cam exception: %s", e)

    return toreturn

def deinit_cam(cam):
    cam.deinit()
    try:
        from machine import Pin, I2C
        i2c = I2C(1, scl=Pin(38), sda=Pin(39))
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
    init_touch()

def capture_cam(cam_obj, colormode):
    return cam_obj.capture()

def apply_cam_settings(cam_obj, prefs):
    return CameraManager.ov_apply_camera_settings(cam_obj, prefs)

CameraManager.add_camera(CameraManager.Camera(
    lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_FRONT,
    name="OV3660",
    vendor="OmniVision",
    init=init_cam,
    deinit=deinit_cam,
    capture=capture_cam,
    apply_settings=apply_cam_settings
))

if __debug__: logger.debug("finished")
if __debug__: logger.debug("Board capabilities:")
if __debug__: logger.debug("  - Display: 320x240 ST7789 with GT911 touch")
if __debug__: logger.debug("  - Camera: OV3660 (3MP)")
if __debug__: logger.debug("  - No LEDs")
