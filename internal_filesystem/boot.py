# Hardware initialization for ESP32-S3-Touch-LCD-2
# Manufacturer's website at https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-2
current_hardware = "waveshare-esp32-s3-touch-lcd-2"

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
SPI_FREQ = 40000000
LCD_SCLK = 39
LCD_MOSI = 38
LCD_MISO = 40
LCD_DC = 42
LCD_CS = 45
LCD_BL = 1

I2C_BUS = 0
I2C_FREQ = 100000
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

display = st7789.ST7789(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=TFT_VER_RES,
    display_height=TFT_HOR_RES,
    backlight_pin=LCD_BL,
    backlight_on_state=st7789.STATE_PWM,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=st7789.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
)
display.init()
display.set_power(True)
display.set_backlight(100)

# Touch handling:
i2c_bus = i2c.I2C.Bus(host=I2C_BUS, scl=TP_SCL, sda=TP_SDA, freq=I2C_FREQ, use_locks=False)
touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=TP_ADDR, reg_bits=TP_REGBITS)
indev=cst816s.CST816S(touch_dev,startup_rotation=lv.DISPLAY_ROTATION._180) # button in top left, good

lv.init()
display.set_rotation(lv.DISPLAY_ROTATION._90) # must be done after initializing display and creating the touch drivers, to ensure proper handling

print("boot.py finished")
