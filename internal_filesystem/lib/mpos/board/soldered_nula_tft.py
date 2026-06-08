print("soldered_nula_tft.py initialization")

# DIY device with components from Soldered Electronics: https://soldered.com
#
# * ESP32-S3
#   - NULA DeepSleep: https://solde.red/333352
#   - 512 KB SRAM + 8MB PSRAM and 8 MB Flash
#
# * 2.4" TFT display 240 x 320
#   - https://solde.red/333211
#   - Display controller: ILI9341 (SPI interface, up to 32 MHz)
#   - Touch controller: XPT2046
#
#
# Because it has only 8MB flash:
#   The normal MPOS build target "esp32s3" doesn't work!
#   Use "unphone" target instead!
#
#
# Wiring ESP32S3 <-> Touchscreen
#
# | ESP32S3 Pin         | ESP32S3 GPIO | TFT Pin | Notes                         |
# |---------------------|--------------|---------|-------------------------------|
# | VCC (5 V via USB-C) | VCC          | VCC     | TFT supports both: 3.3V or 5V |
# | GND                 | GND          | GND     | Ground                        |
# | -                   | -            | PEN     | Touch interrupt (not used)    |
# | -                   | -            | RST     | Reset (not used)              |
# | GPIO (Digital)      | GPIO 8       | DC      | Data/Command                  |
# | GPIO (PWM)          | GPIO 42      | BL      | Brightness control            |
# | SPI SCK             | GPIO 12      | CLK     | Clock line                    |
# | SPI MISO            | GPIO 13      | DO      | MISO, SPI Data Input          |
# | SPI MOSI            | GPIO 11      | DI      | MOSI, SPI Data Output         |
# | GPIO (Digital)      | GPIO 10      | CSL     | Chip Select for TFT           |
# | GPIO (Digital)      | GPIO 9       | CST     | Chip Select for Touch         |
# | -                   | -            | BSY     | Busy Touchscreen (not used)   |
# | -                   | -            | OE      | Output Enable (not used)      |
# | 3V3                 | -            | -       | 3,3V unused                   |
#
#
# Original author: https://github.com/jedie


import time

import drivers.display.ili9341 as ili9341
import lcd_bus
import lvgl as lv
import machine
import mpos.ui
from drivers.indev.xpt2046 import XPT2046
from micropython import const


# Display settings:
SPI_HOST = const(1)
SPI_FREQ = const(32_000_000)
TOUCH_SPI_FREQ = const(1_000_000)

LCD_SCLK = const(12)  # SPI Clock line
LCD_MOSI = const(11)
LCD_DC = const(8)
LCD_CSL = const(10)  # Chip Select for TFT
TOUCH_CS = const(9)  # Chip Select for Touch
LCD_BL = const(42)  # Backlight control
# LCD_RST = const(33)

TFT_VER_RES = const(320)
TFT_HOR_RES = const(240)


print("soldered_nula_tft.py machine.SPI.Bus() initialization")
try:
    spi_bus = machine.SPI.Bus(host=SPI_HOST, mosi=LCD_MOSI, sck=LCD_SCLK)
except Exception as e:
    print(f"Error initializing SPI bus: {e}")
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()

print("soldered_nula_tft.py lcd_bus.SPIBus() initialization")
display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus,
    freq=SPI_FREQ,
    dc=LCD_DC,
    cs=LCD_CSL,
)

print("soldered_nula_tft.py ili9341.ILI9341() initialization")
try:
    mpos.ui.main_display = ili9341.ILI9341(
        data_bus=display_bus,
        display_width=TFT_HOR_RES,
        display_height=TFT_VER_RES,
        color_space=lv.COLOR_FORMAT.RGB565,
        color_byte_order=ili9341.BYTE_ORDER_BGR,
        rgb565_byte_swap=True,
        # reset_pin=LCD_RST,
        reset_state=ili9341.STATE_LOW,
        backlight_pin=LCD_BL,
        backlight_on_state=ili9341.STATE_PWM,
    )
except Exception as e:
    print(f"Error initializing ILI9341: {e}")
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()

touch_dev = machine.SPI.Device(spi_bus=spi_bus, freq=TOUCH_SPI_FREQ, cs=TOUCH_CS)

indev = XPT2046(
    touch_dev,
    lcd_cs=LCD_CSL,
    touch_cs=TOUCH_CS,
    display_width=TFT_HOR_RES,
    display_height=TFT_VER_RES,
    startup_rotation=lv.DISPLAY_ROTATION._0,
)

print("soldered_nula_tft.py display.init()")
mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_color_inversion(False)
mpos.ui.main_display.set_backlight(25)
mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._270)

print("soldered_nula_tft.py lv.init() initialization")
lv.init()


print("soldered_nula_tft.py finished")
