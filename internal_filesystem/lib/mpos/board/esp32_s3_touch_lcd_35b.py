import logging

logger = logging.getLogger(__name__)

if __debug__: logger.debug("esp32_s3_touch_lcd_35b.py initialization")

import time
from micropython import const

import lcd_bus
import lvgl as lv
import machine

import drivers.display.axs15231b as axs15231b
import drivers.indev.axs15231b_touch as axs_touch
import i2c

import mpos.ui
from mpos import InputManager, BatteryManager, SensorManager, CameraManager

WIDTH = const(320)
HEIGHT = const(480)

# --- I2C Bus (shared by touch, PMU, IMU, RTC, audio, IO expander) ---
# SDA=8, SCL=7, 400kHz Fast Mode
if __debug__: logger.debug("Initializing I2C bus on SDA=8, SCL=7")
machine_i2c = machine.I2C(0, sda=machine.Pin(8), scl=machine.Pin(7), freq=400000)

# i2c.I2C.Bus is required by the touch driver (i2c.I2C.Device).
# We create it then override _bus with the machine.I2C instance to avoid an IDF
# driver conflict from initializing the same HW I2C peripheral twice.
i2c_bus = i2c.I2C.Bus(host=0, scl=7, sda=8, freq=400000, use_locks=False)
i2c_bus._bus = machine_i2c

# --- IO Expander TCA9554 (address 0x20) - display reset via pin 1 ---
if __debug__: logger.debug("Resetting display via TCA9554 pin 1")
try:
    # TCA9554 register: 0x06 = configuration (0 = output, 1 = input)
    machine_i2c.writeto_mem(0x20, 0x06, bytes([0xFD]))  # pin 1 = output
    # TCA9554 register: 0x02 = output port
    # Reset sequence: HIGH -> LOW -> HIGH
    machine_i2c.writeto_mem(0x20, 0x02, bytes([0x02]))  # pin 1 HIGH
    time.sleep_ms(10)
    machine_i2c.writeto_mem(0x20, 0x02, bytes([0x00]))  # pin 1 LOW
    time.sleep_ms(10)
    machine_i2c.writeto_mem(0x20, 0x02, bytes([0x02]))  # pin 1 HIGH
    time.sleep_ms(200)
except Exception as e:
    logger.warning("TCA9554 display reset failed: %s", e)

# --- Display: AXS15231B via QSPI ---
if __debug__: logger.debug("Initializing QSPI display bus")
_BL_PIN = const(6)
_CS = const(12)
_SCLK = const(5)
_D0 = const(1)
_D1 = const(2)
_D2 = const(3)
_D3 = const(4)

display_bus = lcd_bus.QSPIBus(
    host=2,
    cs=_CS,
    sck=_SCLK,
    d0=_D0,
    d1=_D1,
    d2=_D2,
    d3=_D3,
    freq=40000000
)

_BUFFER_SIZE = const(WIDTH * 45 * 2)
fb1 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)

mpos.ui.main_display = axs15231b.AXS15231B(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=WIDTH,
    display_height=HEIGHT,
    color_space=lv.COLOR_FORMAT.RGB565,
    backlight_pin=_BL_PIN,
    backlight_on_state=axs15231b.STATE_PWM,
)
mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(100)

# --- Touch: AXS5106L / AXS15231B via I2C at 0x3B ---
if __debug__: logger.debug("Initializing touch controller")
touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=0x3B, reg_bits=8)
indev = axs_touch.AXS15231BTouch(
    touch_dev,
    startup_rotation=lv.DISPLAY_ROTATION._0,
)
InputManager.register_indev(indev)

# --- Battery / Power Management (AXP2101 PMU at 0x34) ---
if __debug__: logger.debug("Initializing AXP2101 PMU")
try:
    from drivers.power.AXP2101 import AXP2101
    pmu = AXP2101(machine_i2c)
    pmu.begin()

    def adc_to_voltage(raw):
        return pmu.getBatteryVoltage() / 1000.0

    BatteryManager.init_pmu(pmu, adc_to_voltage, charge_callback=None)
except Exception as e:
    logger.warning("AXP2101 init failed: %s", e)

# --- SD Card (SDMMC 1-bit: CLK=11, CMD=10, D0=9) ---
if __debug__: logger.debug("Initializing SD card (SDMMC 1-bit)")
from mpos import sdcard
sdcard.init(cmd_pin=10, clk_pin=11, d0_pin=9)

# --- IMU (QMI8658 on I2C 0x6B) ---
if __debug__: logger.debug("Initializing QMI8658 IMU")
SensorManager.init(machine_i2c, address=0x6B, mounted_position=SensorManager.FACING_EARTH)

# --- RTC (PCF85063 on I2C 0x51) ---
if __debug__: logger.debug("Initializing PCF85063 RTC")
try:
    from drivers.rtc.pcf8563 import PCF8563
    rtc = PCF8563(machine_i2c)
except Exception as e:
    logger.warning("RTC init failed: %s", e)

# --- Audio (ES8311 codec via I2C at 0x18 + I2S) ---
if __debug__: logger.debug("Initializing ES8311 audio codec")
try:
    from drivers.codec.es8311 import ES8311
    codec = ES8311(machine_i2c)
except Exception as e:
    logger.warning("ES8311 init failed: %s", e)

# --- Camera (parallel DVP 8-bit) ---
if __debug__: logger.debug("Initializing camera pins")

def init_cam(width, height, colormode):
    toreturn = None
    try:
        from camera import Camera, GrabMode, PixelFormat
        frame_size = CameraManager.resolution_to_framesize(width, height)
        if __debug__: logger.debug("init_cam: FrameSize %s for %sx%s", frame_size, width, height)
        for attempt in range(3):
            try:
                cam = Camera(
                    data_pins=[45, 47, 48, 46, 42, 40, 39, 21],
                    vsync_pin=17,
                    href_pin=18,
                    sda_pin=8,
                    scl_pin=7,
                    pclk_pin=41,
                    xclk_pin=38,
                    xclk_freq=20000000,
                    powerdown_pin=-1,
                    reset_pin=-1,
                    pixel_format=PixelFormat.RGB565 if colormode else PixelFormat.GRAYSCALE,
                    frame_size=frame_size,
                    grab_mode=GrabMode.LATEST,
                    fb_count=1,
                )
                cam.set_vflip(True)
                toreturn = cam
                break
            except Exception as e:
                if attempt < 2:
                    logger.warning("init_cam attempt %s failed: %s, retrying...", attempt, e)
                else:
                    logger.error("init_cam final exception: %s", e)
    except Exception as e:
        logger.error("init_cam exception: %s", e)
    return toreturn

def deinit_cam(cam):
    cam.deinit()

def capture_cam(cam_obj, colormode):
    return cam_obj.capture()

def apply_cam_settings(cam_obj, prefs):
    return CameraManager.ov_apply_camera_settings(cam_obj, prefs)

CameraManager.add_camera(CameraManager.Camera(
    lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
    name="OV2640",
    vendor="OmniVision",
    init=init_cam,
    deinit=deinit_cam,
    capture=capture_cam,
    apply_settings=apply_cam_settings,
    rotation_degrees=0,
))

# --- BOOT Button (GPIO 0) ---
if __debug__: logger.debug("Initializing BOOT button")
try:
    from mpos import InputManager as IM
    from mpos.ui.input_devices import DigitalInput
    boot_btn = DigitalInput(machine.Pin(0, machine.Pin.IN, machine.Pin.PULL_UP), active_low=True, repeat=False)
    IM.register_indev(boot_btn.indev)
    if __debug__: logger.debug("BOOT button registered as keypad input device")
except Exception as e:
    logger.warning("BOOT button init failed: %s", e)

if __debug__: logger.debug("esp32_s3_touch_lcd_35b.py finished")
