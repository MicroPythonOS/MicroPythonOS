# Hardware initialization for M5Stack Core2
# Manufacturer's website at https://docs.m5stack.com/en/core/core2
# ESP32-D0WDQ6-V3, 16MB Flash, 8MB PSRAM
# Display: ILI9342C 320x240 SPI
# Touch: FT6336U (I2C 0x38)
# Power: AXP192 (I2C 0x34)
# Speaker: NS4168 (I2S)
# Mic: SPM1423 (PDM, CLK=0, DATA=34)
# IMU: MPU6886 (I2C 0x68)

import time

import drivers.display.ili9341 as ili9341
import lcd_bus
import lvgl as lv
import machine
import mpos.ui
from machine import I2C, Pin
from micropython import const
from mpos import AudioManager, InputManager, SensorManager

# I2C bus (shared: AXP192, Touch, IMU, RTC)
I2C_SDA = const(21)
I2C_SCL = const(22)
I2C_FREQ = const(400000)

# Display settings (SPI)
SPI_BUS = const(1)  # SPI2
SPI_FREQ = const(40000000)
LCD_SCLK = const(18)
LCD_MOSI = const(23)
LCD_DC = const(15)
LCD_CS = const(5)
LCD_TYPE = const(2)  # ILI9341 type 2

TFT_HOR_RES = const(320)
TFT_VER_RES = const(240)

# I2S Speaker (NS4168)
I2S_BCLK = const(12)
I2S_LRCK = const(0)
I2S_DATA_OUT = const(2)

# Mic (SPM1423 PDM)
MIC_CLK = const(0)
MIC_DATA = const(34)

# IMU
MPU6886_ADDR = const(0x68)

# ==============================
# Step 1: AXP192 Power Management
# ==============================
print("m5stack_core2.py init AXP192 power management")
# All I2C devices (AXP192, Touch, IMU) share one bus on host 0
i2c_bus = I2C(0, scl=Pin(I2C_SCL), sda=Pin(I2C_SDA), freq=I2C_FREQ)

from drivers.power.axp192 import AXP192
axp = AXP192(i2c_bus)
axp.init_core2()

# ==============================
# Step 2: Display (ILI9342C via SPI)
# ==============================
print("m5stack_core2.py init SPI display")
try:
    spi_bus = machine.SPI.Bus(host=SPI_BUS, mosi=LCD_MOSI, sck=LCD_SCLK)
except Exception as e:
    print(f"Error initializing SPI bus: {e}")
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()

display_bus = lcd_bus.SPIBus(spi_bus=spi_bus, freq=SPI_FREQ, dc=LCD_DC, cs=LCD_CS)


# M5Stack Core2 uses ILI9342C with same orientation table as Fire
class ILI9341(ili9341.ILI9341):
    _ORIENTATION_TABLE = (
        0x00,
        0x40 | 0x20,  # _MADCTL_MX | _MADCTL_MV
        0x80 | 0x40,  # _MADCTL_MY | _MADCTL_MX
        0x80 | 0x20,  # _MADCTL_MY | _MADCTL_MV
    )


# Note: LCD reset and backlight are handled by AXP192 (GPIO4=reset, DCDC3=backlight)
# No reset_pin or backlight_pin needed here
mpos.ui.main_display = ILI9341(
    data_bus=display_bus,
    display_width=TFT_HOR_RES,
    display_height=TFT_VER_RES,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=ili9341.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
)
mpos.ui.main_display.init(LCD_TYPE)
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_color_inversion(True)

lv.init()

# ==============================
# Step 3: Touch (FT6336U)
# ==============================
print("m5stack_core2.py init touch (FT6336U)")
import i2c as i2c_lvgl
import drivers.indev.ft6x36 as ft6x36
import pointer_framework

# Create LVGL I2C bus wrapper, then replace its internal bus with our shared I2C(0)
# instance so all devices (AXP192, touch, IMU) share the same hardware I2C controller.
touch_i2c_bus = i2c_lvgl.I2C.Bus(host=0, sda=I2C_SDA, scl=I2C_SCL, freq=I2C_FREQ, use_locks=False)
touch_i2c_bus._bus = i2c_bus

touch_dev = i2c_lvgl.I2C.Device(bus=touch_i2c_bus, dev_id=ft6x36.I2C_ADDR, reg_bits=ft6x36.BITS)
indev = ft6x36.FT6x36(touch_dev, startup_rotation=pointer_framework.lv.DISPLAY_ROTATION._0)
InputManager.register_indev(indev)

# ==============================
# Step 4: Audio (I2S Speaker + PDM Mic)
# ==============================
print("m5stack_core2.py init audio")

# I2S speaker output (NS4168, enabled via AXP192 GPIO2)
i2s_output_pins = {
    'ws': I2S_LRCK,
    'sck': I2S_BCLK,
    'sd': I2S_DATA_OUT,
}
AudioManager.add(
    AudioManager.Output(
        name="speaker",
        kind="i2s",
        i2s_pins=i2s_output_pins,
    )
)
AudioManager.set_volume(40)

# PDM microphone input (SPM1423)
i2s_input_pins = {
    'ws': MIC_CLK,
    'sd_in': MIC_DATA,
}
AudioManager.add(
    AudioManager.Input(
        name="mic",
        kind="i2s",
        i2s_pins=i2s_input_pins,
    )
)

# TODO: add startup sound (RTTTL not supported via I2S, needs WAV file)

# ==============================
# Step 5: IMU (MPU6886)
# ==============================
print("m5stack_core2.py init IMU")
SensorManager.init(
    i2c_bus=i2c_bus,
    address=MPU6886_ADDR,
    mounted_position=SensorManager.FACING_EARTH,
)

# ==============================
# Step 6: Battery (via AXP192)
# ==============================
print("m5stack_core2.py init battery monitoring")
from mpos import BatteryManager

def axp_adc_to_voltage(adc_value):
    """Read battery voltage from AXP192 instead of ADC pin."""
    return axp.get_battery_voltage()

# Use a dummy pin (35) - the actual reading comes from axp via the conversion function
BatteryManager.init_adc(35, axp_adc_to_voltage)

print("m5stack_core2.py finished")
