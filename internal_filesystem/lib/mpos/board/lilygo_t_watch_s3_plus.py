print("lilygo_t_watch_s3_plus.py initialization")
# Manufacturer's website at https://lilygo.cc/products/t-watch-s3-plus
from machine import I2C, Pin, SPI
import time

m_i2c = I2C(1, sda=Pin(10), scl=Pin(11), freq=400000)

# AXP2101 PMU settings:
AXP2101_ADDR = 0x34

# ALDO4 enable @ 3.3V for LoRa: reg 0x95 LDO_VOL3_CTRL: bits[4:0] set ALDO4 voltage (500 mV + step*100 mV)
m_i2c.writeto_mem(AXP2101_ADDR,0x95,bytes([(m_i2c.readfrom_mem(AXP2101_ADDR, 0x95, 1)[0] & 0xE0) | 0x1C]))  # 3.3V: (3300 - 500) / 100 = 28 = 0x1C
m_i2c.writeto_mem(AXP2101_ADDR, 0x90, bytes([m_i2c.readfrom_mem(AXP2101_ADDR, 0x90, 1)[0] | (1 << 3)])) # reg 0x90 LDO_ONOFF_CTRL0: bit3 enables ALDO4

# BLDO2 enable @ 3.3V for vibrator: reg 0x97 LDO_VOL5_CTRL: bits[4:0] set BLDO2 voltage (500 mV + step*100 mV)
m_i2c.writeto_mem(AXP2101_ADDR,0x97,bytes([(m_i2c.readfrom_mem(AXP2101_ADDR, 0x97, 1)[0] & 0xE0) | 0x1C]))  # 3.3V: (3300 - 500) / 100 = 28 = 0x1C
m_i2c.writeto_mem(AXP2101_ADDR, 0x90, bytes([m_i2c.readfrom_mem(AXP2101_ADDR, 0x90, 1)[0] | (1 << 5)])) # reg 0x90 LDO_ONOFF_CTRL0: bit5 enables BLDO2

print("AXP2101 status: enabled + voltage setting for ALDO4/BLDO2")
ldo_onoff = m_i2c.readfrom_mem(AXP2101_ADDR, 0x90, 1)[0]
print("ALDO4: {} @ {} mV".format("EN" if (ldo_onoff & (1 << 3)) else "DIS",500 + ((m_i2c.readfrom_mem(AXP2101_ADDR, 0x95, 1)[0] & 0x1F) * 100))) # bits[4:0] voltage steps
print("BLDO2: {} @ {} mV".format("EN" if (ldo_onoff & (1 << 5)) else "DIS",500 + ((m_i2c.readfrom_mem(AXP2101_ADDR, 0x97, 1)[0] & 0x1F) * 100))) # bits[4:0] voltage steps


print("DRV2605L vibrator test")
DRV2605L_ADDR = 0x5A
m_i2c.writeto_mem(DRV2605L_ADDR, 0x01, bytes([0x00])) # reg 0x01 = mode (0x00 = internal trigger)
m_i2c.writeto_mem(DRV2605L_ADDR, 0x03, bytes([0x00])) # reg 0x03 = waveform sequence slot 1 (0 = Library A)
m_i2c.writeto_mem(DRV2605L_ADDR, 0x04, bytes([12])) # Triple Click - 100%
m_i2c.writeto_mem(DRV2605L_ADDR, 0x05, bytes([89])) # Transition Ramp Up Long Sharp 2 – 0 to 100%
m_i2c.writeto_mem(DRV2605L_ADDR, 0x0C, bytes([1])) # reg 0x0C = GO (1 = start, 0 = stop)


print("BMA423 IMU test")
import drivers.imu_sensor.bma423.bma423 as bma423
sensor = bma423.BMA423(m_i2c, address=0x19)
time.sleep_ms(250) # some sleep is needed before reading values
print("temperature: ", sensor.get_temperature())
print("steps: ", sensor.get_steps())
print("(x,y,z): ", sensor.get_xyz())


try:
    # Doesn't work with the new split Bus/Device Hardware SPI driver and drivers.lora.sx1262 yet
    # so use the original drivers.lora.micropySX126X.sx1262 that's patched to fallback to Software SPI
    #lora_spi_bus = SPI.Bus(host=1,mosi=1,miso=4,sck=3)
    #lora_spi_device = SPI.Device(spi_bus=lora_spi_bus, freq=500000, cs=-1, polarity=0, phase=0, firstbit=SPI.Device.MSB, bits=8)
    pass
except Exception as e:
    import sys
    sys.print_exception(e)
else:
    from drivers.lora.micropySX126X.sx1262 import SX1262
    sx = SX1262(spi_bus=1, clk=3, mosi=1, miso=4, cs=5, irq=9, rst=8, gpio=7)
    import mpos
    mpos.sx = sx


spi_bus = SPI.Bus(host=2,mosi=13,sck=18)

import lcd_bus
display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus,
    freq=40000000,
    dc=38,
    cs=12,
)

_BUFFER_SIZE = const(28800)
fb1 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)

import drivers.display.st7789 as st7789
import mpos.ui
import lvgl as lv
mpos.ui.main_display = st7789.ST7789(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=240,
    display_height=240,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=st7789.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
    backlight_pin=45,
    backlight_on_state=st7789.STATE_PWM,
    offset_y=80
) # triggers lv.init()
mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(100)

import i2c
import drivers.indev.ft6x36 as ft6x36
touch_i2c_bus = i2c.I2C.Bus(host=0, sda=39, scl=40, freq=400000, use_locks=False)
touch_dev = i2c.I2C.Device(bus=touch_i2c_bus, dev_id=ft6x36.I2C_ADDR, reg_bits=ft6x36.BITS)
import pointer_framework
indev = ft6x36.FT6x36(touch_dev, startup_rotation=pointer_framework.lv.DISPLAY_ROTATION._180)
from mpos import InputManager
InputManager.register_indev(indev)

mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._180)

# Audio:
from mpos import AudioManager
i2s_output_pins = {
    'ws': 15,       # Word Select / LRCLK shared between DAC and mic (mandatory)
    'sck': 48,      # SCLK or BCLK - Bit Clock for DAC output (mandatory)
    'sd': 46,       # Serial Data OUT (speaker/DAC)
}
speaker_output = AudioManager.add(
    AudioManager.Output(
        name="speaker",
        kind="i2s",
        i2s_pins=i2s_output_pins,
    )
)

i2s_input_pins = {
    'ws': 15,       # Word Select / LRCLK shared between DAC and mic (mandatory)
    'sck_in': 44,   # SCLK - Serial Clock for microphone input
    'sd_in': 47,    # DIN - Serial Data IN (microphone)
}
mic_input = AudioManager.add(
    AudioManager.Input(
        name="mic",
        kind="i2s",
        i2s_pins=i2s_input_pins,
    )
)


# TODO:
# - battery
# - real IMU driver (instead of proof-of-concept above)
# - GPS

print("lilygo_t_watch_s3_plus.py finished")
