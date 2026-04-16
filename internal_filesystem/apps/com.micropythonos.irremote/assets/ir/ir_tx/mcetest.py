# ir_tx.mcetest Test for nonblocking MCE IR blaster.

# Released under the MIT License (MIT). See LICENSE.

# Copyright (c) 2020 Peter Hinch

# Implements a 2-button remote control on a Pyboard with auto repeat.
from sys import platform
ESP32 = platform == 'esp32'
if ESP32:
    from machine import Pin
else:
    from pyb import Pin, LED

from micropython import const
import uasyncio as asyncio
from aswitch import Switch, Delay_ms
from ir_tx.mce import MCE

loop = asyncio.get_event_loop()
_FIRST = const(0)
_REP = const(1)
_END = const(2)
_REP_DELAY = const(60)

class Rbutton:
    def __init__(self, irb, pin, addr, data, rep_code=False):
        self.irb = irb
        self.sw = Switch(pin)
        self.addr = addr
        self.data = data
        self.rep_code = rep_code
        self.sw.close_func(self.cfunc)
        self.sw.open_func(self.ofunc)
        self.tim = Delay_ms(self.repeat)
        self.stop = False

    def cfunc(self):  # Button push: send data and set up for repeats
        self.irb.transmit(self.addr, self.data, _FIRST, True)
        self.tim.trigger(_REP_DELAY)

    def ofunc(self):  # Button release: cancel repeat timer
        self.stop = True

    async def repeat(self):
        await asyncio.sleep(0)  # Let timer stop before retriggering
        if self.stop:  # Button has been released: send last message
            self.stop = False
            self.tim.stop()  # Not strictly necessary
            self.irb.transmit(self.addr, self.data, _END, True)
        else:
            self.tim.trigger(_REP_DELAY)
            self.irb.transmit(self.addr, self.data, _REP, True)

async def main():
    pin = Pin(23, Pin.OUT, value = 0) if ESP32 else Pin('X1')
    irb = MCE(pin)  # verbose=True)
    # Uncomment the following to print transmit timing
    # irb.timeit = True

    b = []  # Rbutton instances
    px3 = Pin(18, Pin.IN, Pin.PULL_UP) if ESP32 else Pin('X3', Pin.IN, Pin.PULL_UP)
    px4 = Pin(19, Pin.IN, Pin.PULL_UP) if ESP32 else Pin('X4', Pin.IN, Pin.PULL_UP)
    b.append(Rbutton(irb, px3, 0x1, 0x7))
    b.append(Rbutton(irb, px4, 0xe, 0xb))
    if ESP32:
        while True:
            print('Running')
            await asyncio.sleep(5)
    else:
        led = LED(1)
        while True:
            await asyncio.sleep_ms(500)  # Obligatory flashing LED.
            led.toggle()

# Greeting strings. Common:
s = '''Test for IR transmitter. Run:
from ir_tx.mcetest import test
test()
'''
# Pyboard:
spb = '''
IR LED on pin X1
Ground pin X3 to send addr 1 data 7
Ground pin X4 to send addr 0xe data 0x0b.'''
# ESP32
sesp = '''
IR LED gate on pins 23, 21
Ground pin 18 to send addr 1 data 7
Ground pin 19 to send addr 0xe data 0x0b.'''

print(''.join((s, sesp)) if ESP32 else ''.join((s, spb)))

def test():
    loop.run_until_complete(main())
