# Hardware initialization for Fri3d Camp 2026 Badge

# Overview:
# - Touch screen controller is cst816s
# - IMU (LSM6DSO) is different from fri3d_2024 (and address 0x6A instead of 0x6B) but the API seems the same, except different chip ID (0x6C iso 0x6A)
# - I2S audio (communicator) is the same
# - headphone jack microphone is on ESP.IO1
# - CH32X035GxUx over I2C:
#   - battery voltage measurement
#   - analog joystick
#   - digital buttons (X,Y,A,B, MENU)
#   - buzzer
#       - audio DAC emulation using buzzer might be slow or need specific buffered protocol
# - test it on the Waveshare to make sure no syntax / variable errors

from machine import ADC, I2C, Pin, SPI, SDCard
import lcd_bus
import i2c

import lvgl as lv

import drivers.display.st7789 as st7789

import mpos.ui
import mpos.ui.focus_direction
from mpos import InputManager, IRManager

spi_bus = SPI.Bus(
    host=2,
    mosi=6,
    miso=8,
    sck=7
)

try:
    lora_spi_device = SPI.Device(spi_bus=spi_bus, freq=500000, cs=-1, polarity=0, phase=0, firstbit=SPI.Device.MSB, bits=8)
except Exception as e:
    import sys
    sys.print_exception(e)
else:
    from drivers.lora.sx1262 import SX1262
    rf_sw = Pin(46, Pin.OUT)
    rf_sw.value(1) ; print("RF_SW set to HIGH") # Logic high level means enable receiver mode
    sx = SX1262(lora_spi_device, 40, 11, 41, 45) # reset pin isn't used but driver expects a value so set to 11 (IR receiver) here for now
    from mpos import LoRaManager
    LoRaManager.radioChip = sx

display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus,
    freq=40000000, # 40 Mhz
    dc=4,
    cs=5
)

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

# === LED HARDWARE ===
import mpos.lights as LightsManager
# Initialize 5 NeoPixel LEDs (GPIO 12)
LightsManager.init(neopixel_pin=12, num_leds=5)
# Set left LED red
LightsManager.set_led(4, 255, 0, 0)
LightsManager.write()

# CH32 coprocessor / IO expander
from machine import I2C, Pin
expander_i2c = I2C(1, sda=Pin(39), scl=Pin(42), freq=400000)
from lib.drivers.fri3d.expander import Expander
expander = Expander(i2c_bus=expander_i2c)


# Show progress using the RGB LEDs:
def rainbow_color(value: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, value / 100.0))   # normalized 0.0 to 1.0
    hue = t * 300.0
    h = hue / 60.0
    i = int(h)
    f = h - i                               # fractional part

    if i == 0:
        r, g, b = 1.0, f, 0.0
    elif i == 1:
        r, g, b = 1.0 - f, 1.0, 0.0
    elif i == 2:
        r, g, b = 0.0, 1.0, f
    elif i == 3:
        r, g, b = 0.0, 1.0 - f, 1.0
    elif i == 4:
        r, g, b = f, 0.0, 1.0
    else:  # i == 5
        r, g, b = 1.0, 0.0, 1.0 - f

    return (int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5))

# Avoid excessive prints here because it slows down if the serial connects during printing?!
def progress(msg, pct):
    #print(f"{msg}: {pct}%")
    twentieth = int(pct / 20)
    lednr = max(0,4 - twentieth)
    #color = (int(pct*2.5), int(255-pct*2.5), abs(128-int(pct*2.5)))
    color = rainbow_color(pct)
    #print(f"setting LED {lednr} color {color}")
    LightsManager.set_led(lednr, *color)
    LightsManager.write()

def install_expander_firmware(filename):
    print("Installing latest CH32 firmware")
    expander.config = 0x0B # trigger SWD enable
    import time
    time.sleep(0.2)
    from rvswd import RVSWD
    prog = RVSWD(39, 42)
    # optional check, already halts the MCU
    vendor = prog.read_vendor_bytes()
    if (vendor[1] & 0xffffff0f) != 0x03560601:
        print(f"CH32X035G8U6 not detected, vendor is {vendor} but continuing anyway")
    with open(filename, 'rb') as f:
        fw = f.read()
    f.close()
    progress_margin_end = 21 # 21% left for sleep at the end
    prog.x03x_program(fw, lambda msg, pct: progress(msg, int((100 - progress_margin_end) * pct / 100))) # throws exception if it fails
    for pct in range(100-progress_margin_end,101):
        progress("waiting for CH32 boot", pct)
        time.sleep(4/progress_margin_end) # wait 4 seconds total
    print("Latest CH32 firmware installed.")

# Check expander firmware version and if none or too low: install latest
try:
    current_version = expander.version
    print(f"Current_version of CH32 firmware: {current_version}")
except Exception as e:
    print("Could not check CH32 firmware version, assuming 0.0.0")
    current_version = (0, 0, 0)
latest_version = (1, 2, 1)
if latest_version > current_version:
    print(f"CH32 firmware is lower than latest {latest_version} so updating...")
    try:
        install_expander_firmware("/lib/drivers/fri3d/coprocessor_1.2.1.fw")
        LightsManager.set_all(0,255,0)
        LightsManager.write()
        # Need to reinitialize:
        expander_i2c = I2C(sda=Pin(39), scl=Pin(42), freq=400000)
        expander = Expander(i2c_bus=expander_i2c)
    except Exception as e:
        print(f"CH32 firmware install got exception: {e}")
        import sys
        sys.print_exception(e)
    try:
        current_version = expander.version
        print(f"After install, current_version of CH32 firmware: {current_version}")
    except Exception as e:
        print("Could not check CH32 firmware version after install, many things, including LCD RESET, won't work!")

# quick and dirty way to make accessible later:
mpos.io_expander = expander

# LCD reset using the CH32 microcontroller
expander.config= 0x01 # 3v3 aux on + LCD off
import time
time.sleep_ms(100)
expander.config= 0x03 # 3v3 aux + LCD on
import mpos

# see ./lvgl_micropython/api_drivers/py_api_drivers/frozen/display/display_driver_framework.py
mpos.ui.main_display = st7789.ST7789(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=240,
    display_height=320,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=st7789.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
    # reset_pin is driven by the CH32 microcontroller
) # calls lv.init()

mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(100)
mpos.ui.main_display.set_color_inversion(True)

# Touch handling:
# touch pad interrupt TP Int is on ESP.IO13
import drivers.indev.cst816s as cst816s
i2c_bus = i2c.I2C.Bus(host=0, scl=18, sda=9, freq=400000, use_locks=False)
touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=0x15, reg_bits=8)
try:
    tindev=cst816s.CST816S(touch_dev,startup_rotation=lv.DISPLAY_ROTATION._180) # button in top left, good
    InputManager.register_indev(tindev)
except Exception as e:
    print(f"Touch screen init got exception: {e}")
mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._270)

# Button handling code:
import time
btn_start = Pin(0, Pin.IN, Pin.PULL_UP) # START

# Key repeat configuration
# This whole debounce logic is only necessary because LVGL 9.2.2 seems to have an issue where
# the lv_keyboard widget doesn't handle PRESSING (long presses) properly, it loses focus.
REPEAT_INITIAL_DELAY_MS = 300  # Delay before first repeat
REPEAT_RATE_MS = 100  # Interval between repeats
last_key = None
last_state = lv.INDEV_STATE.RELEASED
key_press_start = 0  # Time when key was first pressed
last_repeat_time = 0  # Time of last repeat event

# Read callback
# Warning: This gets called several times per second, and if it outputs continuous debugging on the serial line,
# that will break tools like mpremote from working properly to upload new files over the serial line, thus needing a reflash.
def keypad_read_cb(indev, data):
    global last_key, last_state, key_press_start, last_repeat_time
    data.continue_reading = False
    since_last_repeat = 0

    # Check buttons
    current_key = None
    current_time = time.ticks_ms()

    # Check buttons
    if btn_start.value() == 0:
        current_key = lv.KEY.END

    # Key repeat logic
    if current_key:
        if current_key != last_key:
            # New key press
            data.key = current_key
            data.state = lv.INDEV_STATE.PRESSED
            last_key = current_key
            last_state = lv.INDEV_STATE.PRESSED
            key_press_start = current_time
            last_repeat_time = current_time
        else: # same key
            # Key held: Check for repeat
            elapsed = time.ticks_diff(current_time, key_press_start)
            since_last_repeat = time.ticks_diff(current_time, last_repeat_time)
            if elapsed >= REPEAT_INITIAL_DELAY_MS and since_last_repeat >= REPEAT_RATE_MS:
                # Send a new PRESSED/RELEASED pair for repeat
                data.key = current_key
                data.state = lv.INDEV_STATE.PRESSED if last_state == lv.INDEV_STATE.RELEASED else lv.INDEV_STATE.RELEASED
                last_state = data.state
                last_repeat_time = current_time
            else:
                # No repeat yet, send RELEASED to avoid PRESSING
                data.state = lv.INDEV_STATE.RELEASED
                last_state = lv.INDEV_STATE.RELEASED
    else:
        # No key pressed
        data.key = last_key if last_key else lv.KEY.ENTER
        data.state = lv.INDEV_STATE.RELEASED
        last_key = None
        last_state = lv.INDEV_STATE.RELEASED
        key_press_start = 0
        last_repeat_time = 0

group = lv.group_create()
group.set_default()

# Create and set up the input device
indev = lv.indev_create()
indev.set_type(lv.INDEV_TYPE.KEYPAD)
indev.set_read_cb(keypad_read_cb)
indev.set_group(group) # is this needed? maybe better to move the default group creation to main.py so it's available everywhere...
disp = lv.display_get_default()
indev.set_display(disp)  # different from display
indev.enable(True)
InputManager.register_indev(indev)

# initialize the expander as indev driver
try:
    from drivers.indev.fri3d_2026_expander import Fri3d2026Expander
    expander_int_pin = Pin(3, Pin.IN, Pin.PULL_UP)
    tindev_buttons=Fri3d2026Expander(expander) # not passing int_pin because unreliable
    tindev_buttons.set_group(group)
    #tindev_buttons.set_display(disp)
    tindev_buttons.enable(True)
    InputManager.register_indev(tindev_buttons)
except Exception as e:
    print(f"expander init got exception: {e}")

import mpos.sdcard
mpos.sdcard.init(spi_bus=spi_bus, cs_pin=14)

IRManager.txPin = Pin(10, Pin.OUT)
IRManager.rxPin = Pin(11, Pin.IN)

# === AUDIO HARDWARE ===
from mpos import AudioManager

headset_i2s_output_pins = {
    'ws': 47,       # Word Select / LRCLK shared between DAC and mic (mandatory)
    'sd': 16,       # Serial Data OUT (speaker/DAC)
    'sck': 10,      # SCLK aka BCLK (optional for CJC4344 DAC hardware but MicroPython I2S needs a valid pin) so set it to IO10 (badge link) for now
    'mck': 2,       # MCLK (mandatory) BUT this pin is sck on the communicator
}

AudioManager.add(
    AudioManager.Output(
        name="Headset Output",
        kind="i2s",
        i2s_pins=headset_i2s_output_pins,
    )
)

AudioManager.add(
    AudioManager.Input(
        name="Headset Input",
        kind="adc",
        adc_mic_pin=1, # ADC microphone is on GPIO 1
    )
)

# Add this after the headset output so that it doesn't become the default:
buzzer_output = AudioManager.add(
    AudioManager.Output(
        name="Badge Buzzer",
        kind="buzzer",
        buzzer_pin=38,
    )
)

# Would be better to only add these if the communicator is connected:
communicator_i2s_output_pins = {
    'ws': 47,       # Word Select / LRCLK shared between DAC and mic (mandatory)
    'sd': 16,       # Serial Data OUT (speaker/DAC)
    'sck': 2,       # SCLK or BCLK - Bit Clock for DAC output (mandatory)
}

communicator_i2s_input_pins = {
    'ws': 47,       # Word Select / LRCLK shared between DAC and mic (mandatory)
    'sck_in': 17,   # SCLK - Serial Clock for microphone input
    'sd_in': 15,    # DIN - Serial Data IN (microphone)
}

speaker_output = AudioManager.add(
    AudioManager.Output(
        name="Communicator Output",
        kind="i2s",
        i2s_pins=communicator_i2s_output_pins,
    )
)

mic_input = AudioManager.add(
    AudioManager.Input(
        name="Communicator Input",
        kind="i2s",
        i2s_pins=communicator_i2s_input_pins,
    )
)

# === SENSOR HARDWARE ===
from mpos import SensorManager
SensorManager.init(i2c_bus, address=0x6A, mounted_position=SensorManager.FACING_EARTH) # IMU (LSM6DSOTR-C / LSM6DSO)

# === STARTUP "WOW" EFFECT ===
import time
import _thread

def startup_wow_effect():
    try:
        # Startup jingle: Happy upbeat sequence (ascending scale with flourish)
        startup_jingle = "Startup:d=8,o=6,b=200:c,d,e,g,4c7,4e,4c7"
        #startup_jingle = "ShortBeeps:d=32,o=5,b=320:c6,c7"

        # Start the jingle
        player = AudioManager.player(
            rtttl=startup_jingle,
            stream_type=AudioManager.STREAM_NOTIFICATION,
            volume=60,
            output=buzzer_output,
        )
        player.start()

        # Rainbow colors for the 5 LEDs
        rainbow = [
            (255, 0, 0),    # Red
            (255, 128, 0),  # Orange
            (255, 255, 0),  # Yellow
            (0, 255, 0),    # Green
            (0, 0, 255),    # Blue
        ]

        # Rainbow sweep effect (3 passes, getting faster)
        for pass_num in range(3):
            for i in range(5):
                # Light up LEDs progressively
                for j in range(i + 1):
                    LightsManager.set_led(j, *rainbow[j])
                LightsManager.write()
                time.sleep_ms(80 - pass_num * 20)  # Speed up each pass

        # Flash all LEDs bright white
        LightsManager.set_all(255, 255, 255)
        LightsManager.write()
        time.sleep_ms(150)

        # Rainbow finale
        for i in range(5):
            LightsManager.set_led(i, *rainbow[i])
        LightsManager.write()
        time.sleep_ms(300)

        # Fade out
        LightsManager.clear()
        LightsManager.write()

    except Exception as e:
        print(f"Startup effect error: {e}")

from mpos import TaskManager
_thread.stack_size(TaskManager.good_stack_size()) # default stack size won't work, crashes!
_thread.start_new_thread(startup_wow_effect, ())

print("fri3d_2026.py finished")
