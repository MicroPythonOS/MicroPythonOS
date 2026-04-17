# acquire.py Acquire a pulse train from an IR remote
# Supports NEC protocol.
# For a remote using NEC see https://www.adafruit.com/products/389

# Author: Peter Hinch
# Copyright Peter Hinch 2020 Released under the MIT license

from machine import Pin, freq
from sys import platform

from utime import sleep_ms, ticks_us, ticks_diff
from ir_rx import IR_RX


class IR_GET(IR_RX):
    def __init__(self, pin, nedges=100, twait=100, display=True):
        self.display = display
        super().__init__(pin, nedges, twait, lambda *_ : None)
        self.data = None

    def decode(self, _):
        def near(v, target):
            return target * 0.8 < v < target * 1.2
        lb = self.edge - 1  # Possible length of burst
        if lb < 3:
            return  # Noise
        burst = []
        for x in range(lb):
            dt = ticks_diff(self._times[x + 1], self._times[x])
            if x > 0 and dt > 10000:  # Reached gap between repeats
                break
            burst.append(dt)
        lb = len(burst)  # Actual length
        # Duration of pulse train 24892 for RC-5 22205 for RC-6
        duration = ticks_diff(self._times[lb - 1], self._times[0])

        if self.display:
            for x, e in enumerate(burst):
                print('{:03d} {:5d}'.format(x, e))
            print()
            # Attempt to determine protocol
            ok = False  # Protocol not yet found
            if near(burst[0], 9000) and lb == 67:
                print('NEC')
                ok = True

            if not ok and near(burst[0], 2400) and near(burst[1], 600):  # Maybe Sony
                try:
                    nbits = {25:12, 31:15, 41:20}[lb]
                except KeyError:
                    pass
                else:
                    ok = True
                    print('Sony {}bit'.format(nbits))

            if not ok and near(burst[0], 889):  # Maybe RC-5
                if near(duration, 24892) and near(max(burst), 1778):
                    print('Philps RC-5')
                    ok = True

            if not ok and near(burst[0], 2666) and near(burst[1], 889):  # RC-6?
                if near(duration, 22205) and near(burst[1], 889) and near(burst[2], 444):
                    print('Philips RC-6 mode 0')
                    ok = True

            if not ok and near(burst[0], 2000) and near(burst[1], 1000):
                if near(duration, 19000):
                    print('Microsoft MCE edition protocol.')
                    # Constant duration, variable burst length, presumably bi-phase
                    print('Protocol start {} {} Burst length {} duration {}'.format(burst[0], burst[1], lb, duration))
                    ok = True

            if not ok and near(burst[0], 4500) and near(burst[1], 4500) and lb == 67:  # Samsung
                print('Samsung')
                ok = True

            if not ok and near(burst[0], 3500) and near(burst[1], 1680):  # Panasonic?
                print('Unsupported protocol. Panasonic?')
                ok = True

            if not ok:
                print('Unknown protocol start {} {} Burst length {} duration {}'.format(burst[0], burst[1], lb, duration))

            print()
        self.data = burst
        # Set up for new data burst. Run null callback
        self.do_callback(0, 0, 0)

    def acquire(self):
        while self.data is None:
            sleep_ms(5)
        self.close()
        return self.data

def test():
    # Define pin according to platform
    if platform == 'pyboard':
        pin = Pin('X3', Pin.IN)
    elif platform == 'esp8266':
        freq(160000000)
        pin = Pin(13, Pin.IN)
    elif platform == 'esp32' or platform == 'esp32_LoBo':
        pin = Pin(23, Pin.IN)
    elif platform == 'rp2':
        pin = Pin(16, Pin.IN)
    irg = IR_GET(pin)
    print('Waiting for IR data...')
    return irg.acquire()
