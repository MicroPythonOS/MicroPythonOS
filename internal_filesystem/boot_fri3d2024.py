# Hardware initialization for Fri3d Camp 2024 Badge

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
#SPI_FREQ = 40000000
#SPI_BUS = 1
SPI_FREQ = 20000000
LCD_SCLK = 7
LCD_MOSI = 6
LCD_MISO = 8
LCD_DC = 4
LCD_CS = 5
#LCD_BL = 1
LCD_RST = 48

#I2C_BUS = 0
#I2C_FREQ = 100000
#TP_SDA = 48
#TP_SCL = 47
#TP_ADDR = 0x15
#TP_REGBITS = 8

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

#rs=LCD_RST
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

print("boot.py finished")
