# ir_tx.test Test for nonblocking NEC/SONY/RC-5/RC-6 mode 0 IR blaster.

# Released under the MIT License (MIT). See LICENSE.

# Copyright (c) 2020 Peter Hinch

# Implements a 2-button remote control on a Pyboard with auto repeat.
from sys import platform
ESP32 = platform == 'esp32'
RP2 = platform == 'rp2'
PYBOARD = platform == 'pyboard'
if ESP32 or RP2:
    from machine import Pin
else:
    from pyb import Pin, LED
import uasyncio as asyncio
from primitives.switch import Switch
from primitives.delay_ms import Delay_ms
# Import all implemented classes
from ir_tx.nec import NEC
from ir_tx.sony import SONY_12, SONY_15, SONY_20
from ir_tx.philips import RC5, RC6_M0

loop = asyncio.get_event_loop()

# If button is held down normal behaviour is to retransmit
# but most NEC models send a REPEAT code
class Rbutton:
    toggle = 1  # toggle is ignored in NEC mode
    def __init__(self, irb, pin, addr, data, proto):
        self.irb = irb
        self.sw = Switch(pin)
        self.addr = addr
        self.data = data
        self.proto = proto

        self.sw.close_func(self.cfunc)
        self.sw.open_func(self.ofunc)
        self.tim = Delay_ms(self.repeat)

    def cfunc(self):  # Button push: send data
        tog = 0 if self.proto < 3 else Rbutton.toggle  # NEC, sony 12, 15: toggle==0
        self.irb.transmit(self.addr, self.data, tog, True)  # Test validation
        # Auto repeat. The Sony protocol specifies 45ms but this is tight.
        # In 20 bit mode a data burst can be upto 39ms long.
        self.tim.trigger(108)

    def ofunc(self):  # Button release: cancel repeat timer
        self.tim.stop()
        Rbutton.toggle ^= 1  # Toggle control

    async def repeat(self):
        await asyncio.sleep(0)  # Let timer stop before retriggering
        if not self.sw():  # Button is still pressed: retrigger
            self.tim.trigger(108)
            if self.proto == 0:
                self.irb.repeat()  # NEC special case: send REPEAT code
            else:
                tog = 0 if self.proto < 3 else Rbutton.toggle  # NEC, sony 12, 15: toggle==0
                self.irb.transmit(self.addr, self.data, tog, True)  # Test validation

async def main(proto):
    # Test uses a 38KHz carrier.
    if ESP32:  # Pins for IR LED gate
        pin = Pin(23, Pin.OUT, value = 0)
    elif RP2:
        pin = Pin(17, Pin.OUT, value = 0)
    else:
        pin = Pin('X1')
    classes = (NEC, SONY_12, SONY_15, SONY_20, RC5, RC6_M0)
    irb = classes[proto](pin, 38000)  # My decoder chip is 38KHz
    # Uncomment the following to print transmit timing
    # irb.timeit = True

    b = []  # Rbutton instances
    px3 = Pin('X3', Pin.IN, Pin.PULL_UP) if PYBOARD else Pin(18, Pin.IN, Pin.PULL_UP)
    px4 = Pin('X4', Pin.IN, Pin.PULL_UP) if PYBOARD else Pin(19, Pin.IN, Pin.PULL_UP)
    b.append(Rbutton(irb, px3, 0x1, 0x7, proto))
    b.append(Rbutton(irb, px4, 0x10, 0xb, proto))
    if ESP32:
        while True:
            print('Running')
            await asyncio.sleep(5)
    elif RP2:
        led = Pin(25, Pin.OUT)
        while True:
            await asyncio.sleep_ms(500)  # Obligatory flashing LED.
            led(not led())
    else:
        led = LED(1)
        while True:
            await asyncio.sleep_ms(500)  # Obligatory flashing LED.
            led.toggle()

# Greeting strings. Common:
s = '''Test for IR transmitter. Run:
from ir_tx.test import test
test() for NEC protocol
test(1) for Sony SIRC 12 bit
test(2) for Sony SIRC 15 bit
test(3) for Sony SIRC 20 bit
test(4) for Philips RC-5 protocol
test(5) for Philips RC-6 mode 0.
'''

# Pyboard:
spb = '''
IR LED on pin X1
Ground pin X3 to send addr 1 data 7
Ground pin X4 to send addr 0x10 data 0x0b.'''

# ESP32
sesp = '''
IR LED gate on pin 23
Ground pin 18 to send addr 1 data 7
Ground pin 19 to send addr 0x10 data 0x0b.'''

# RP2
srp2 = '''
IR LED gate on pin 17
Ground pin 18 to send addr 1 data 7
Ground pin 19 to send addr 0x10 data 0x0b.'''

if ESP32:
    print(''.join((s, sesp)))
elif RP2:
    print(''.join((s, srp2)))
else:
    print(''.join((s, spb)))

def test(proto=0):
    loop.run_until_complete(main(proto))
