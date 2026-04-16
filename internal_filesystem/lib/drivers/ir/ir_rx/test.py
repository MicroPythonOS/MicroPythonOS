# test.py Test program for IR remote control decoder
# Supports Pyboard, ESP32 and ESP8266

# Author: Peter Hinch
# Copyright Peter Hinch 2020-2022 Released under the MIT license

# Run this to characterise a remote.

from sys import platform
import time
import gc
from machine import Pin, freq
from ir_rx.print_error import print_error  # Optional print of error codes

# Import all implemented classes
from ir_rx.nec import NEC_8, NEC_16, SAMSUNG
from ir_rx.sony import SONY_12, SONY_15, SONY_20
from ir_rx.philips import RC5_IR, RC6_M0
from ir_rx.mce import MCE

# Define pin according to platform
if platform == "pyboard":
    p = Pin("X3", Pin.IN)
elif platform == "esp8266":
    freq(160000000)
    p = Pin(13, Pin.IN)
elif platform == "esp32" or platform == "esp32_LoBo":
    p = Pin(23, Pin.IN)
elif platform == "rp2":
    p = Pin(16, Pin.IN)

# User callback
def cb(data, addr, ctrl):
    if data < 0:  # NEC protocol sends repeat codes.
        print("Repeat code.")
    else:
        print(f"Data 0x{data:02x} Addr 0x{addr:04x} Ctrl 0x{ctrl:02x}")


def test(proto=0):
    classes = (NEC_8, NEC_16, SONY_12, SONY_15, SONY_20, RC5_IR, RC6_M0, MCE, SAMSUNG)
    ir = classes[proto](p, cb)  # Instantiate receiver
    ir.error_function(print_error)  # Show debug information
    # ir.verbose = True
    # A real application would do something here...
    try:
        while True:
            print("running")
            time.sleep(5)
            gc.collect()
    except KeyboardInterrupt:
        ir.close()


# **** DISPLAY GREETING ****
s = """Test for IR receiver. Run:
from ir_rx.test import test
test() for NEC 8 bit protocol,
test(1) for NEC 16 bit,
test(2) for Sony SIRC 12 bit,
test(3) for Sony SIRC 15 bit,
test(4) for Sony SIRC 20 bit,
test(5) for Philips RC-5 protocol,
test(6) for RC6 mode 0.
test(7) for Microsoft Vista MCE.
test(8) for Samsung.

Hit ctrl-c to stop, then ctrl-d to soft reset."""

print(s)
