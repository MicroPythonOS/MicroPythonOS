import logging

logger = logging.getLogger(__name__)

if __debug__: logger.debug("waveshare_esp32_s3_touch_lcd_3_5.py initialization")
# Hardware initialization for the Waveshare ESP32-S3-Touch-LCD-3.5:
# 3.5" 320x480 IPS (ST7796 over SPI), FT6336 capacitive touch, QMI8658 IMU,
# PCF85063 RTC, AXP2101 power management, ES8311 audio codec, TF card slot,
# camera connector (OV5640/OV2640 supported but NOT included with the board).
#
# Manufacturer's wiki: https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-3.5
# Schematic: https://files.waveshare.com/wiki/ESP32-S3-Touch-LCD-3.5/ESP32-S3-Touch-LCD-3.5-Schematic.pdf
#
# Unlike the ESP32-S3-Touch-LCD-2, the LCD's reset and chip-select lines are
# NOT on ESP32 GPIOs: they sit behind a PCA9554 I2C IO expander (EXIO1 = LCD
# reset, EXIO2 = LCD chip select). Since the display is the only device on
# the SPI bus, CS is simply driven low once at init and left there, and the
# SPI bus is created without a CS pin.

import time

import drivers.display.st7796 as st7796
import drivers.indev.ft6x36 as ft6x36
import i2c
import lcd_bus
import lvgl as lv
import machine
import mpos.ui
from drivers.io_expander.pca9554 import PCA9554
from mpos import InputManager

# Pin configuration (from the Waveshare demo code / schematic)
SPI_BUS = 2
SPI_FREQ = 40000000
LCD_SCLK = 5
LCD_MOSI = 1
LCD_MISO = 2
LCD_DC = 3
LCD_BL = 6

I2C_SDA = 8
I2C_SCL = 7

EXPANDER_ADDR = 0x20   # PCA9554
EXIO_LCD_RESET = 1     # EXIO1
EXIO_LCD_CS = 2        # EXIO2

TOUCH_ADDR = 0x38      # FT6336
PMU_ADDR = 0x34        # AXP2101
IMU_ADDR = 0x6B        # QMI8658

# Shared I2C bus: PCA9554 expander, FT6336 touch, AXP2101 PMU, QMI8658 IMU,
# PCF85063 RTC (0x51), ES8311 codec.
i2c_bus = i2c.I2C.Bus(host=0, scl=I2C_SCL, sda=I2C_SDA, freq=400000, use_locks=False)

# Bring the LCD out of reset and assert its chip select via the expander,
# BEFORE initializing the display controller over SPI.
expander = PCA9554(i2c_bus, EXPANDER_ADDR)
expander.set_output(EXIO_LCD_CS, False)    # CS low = selected (sole SPI device)
expander.set_output(EXIO_LCD_RESET, False) # pulse reset
time.sleep_ms(10)
expander.set_output(EXIO_LCD_RESET, True)
time.sleep_ms(120)                         # ST7796 needs ~120ms after reset

if __debug__: logger.debug("waveshare_esp32_s3_touch_lcd_3_5.py machine.SPI.Bus() initialization")
try:
    spi_bus = machine.SPI.Bus(host=SPI_BUS, mosi=LCD_MOSI, miso=LCD_MISO, sck=LCD_SCLK)
except Exception as e:
    logger.error("Error initializing SPI bus: %s" % (e))
    if __debug__: logger.debug("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()

display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus,
    freq=SPI_FREQ,
    dc=LCD_DC,
    cs=-1,  # chip select is on the PCA9554 expander, held low above
)

# 320*480*2 = 307200 bytes full frame; use a DMA-capable strip like the
# LCD-2 board does (320*45*2=28800 there). 320*48*2=30720 is a round strip
# of 1/10th of this taller panel; tune once hardware timing is measured.
_BUFFER_SIZE = const(320 * 48 * 2)  # 30720
fb1 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)

mpos.ui.main_display = st7796.ST7796(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=320,
    display_height=480,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=st7796.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
    backlight_pin=LCD_BL,
    backlight_on_state=st7796.STATE_PWM,
)  # triggers lv.init()
mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(100)

# Touch handling:
touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=TOUCH_ADDR, reg_bits=8)
indev = ft6x36.FT6x36(touch_dev)
InputManager.register_indev(indev)

# Landscape, like the other MPOS boards; must be done after initializing the
# display and creating the touch driver so both agree on the orientation.
mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._90)

# === POWER MANAGEMENT (AXP2101) ===
# Battery charge/percentage via the PMU instead of a raw ADC pin.
# Same approach as lilygo_t_watch_s3_plus.
try:
    from drivers.power.AXP2101 import AXP2101

    from mpos import BatteryManager
    pmu = AXP2101(i2c_bus, addr=PMU_ADDR)
    BatteryManager.read_raw_adc = lambda *args: 0
    BatteryManager.has_battery = lambda *args: True
    BatteryManager.get_battery_percentage = pmu.getBatteryPercent
except Exception as e:
    logger.error("AXP2101 init failed: %s" % (e))

# === SENSOR HARDWARE ===
# QMI8658 IMU on the shared I2C bus. Mounted position needs on-hardware
# verification; FACING_EARTH matches the LCD-2 which uses the same IMU.
from mpos import SensorManager

SensorManager.init(i2c_bus, address=IMU_ADDR, mounted_position=SensorManager.FACING_EARTH)

# === CAMERA ===
# The board has a camera CONNECTOR (OV5640/OV2640 supported) but no camera is
# included. Camera init is intentionally not set up here; if you attach one,
# see waveshare_esp32_s3_touch_lcd_2.py for the CameraManager pattern (the
# connector pinout is in the schematic linked above).

if __debug__: logger.debug("waveshare_esp32_s3_touch_lcd_3_5.py finished")
