"""Minimal duplex I2S proof-of-concept for Fri3d 2024.

Creates TX + RX I2S instances simultaneously using merged pin config
from the fri3d_2024 board setup. Intended for quick validation only.
"""

import time

try:
    import machine
    _HAS_MACHINE = True
except ImportError:
    _HAS_MACHINE = False


# Merged pin map from internal_filesystem/lib/mpos/board/fri3d_2024.py
I2S_PINS = {
    "ws": 47,       # shared LRCLK
    "sck": 2,       # DAC bit clock
    "sd": 16,       # DAC data out
    "sck_in": 17,   # mic bit clock
    "sd_in": 15,    # mic data in
}


class DuplexI2STest:
    """Minimal duplex setup: one TX I2S + one RX I2S running together."""

    def __init__(self, sample_rate=16000, duration_ms=3000):
        self.sample_rate = sample_rate
        self.duration_ms = duration_ms
        self._tx = None
        self._rx = None

    def _init_i2s(self):
        if not _HAS_MACHINE:
            raise RuntimeError("machine.I2S not available")

        self._tx = machine.I2S(
            0,
            sck=machine.Pin(I2S_PINS["sck"], machine.Pin.OUT),
            ws=machine.Pin(I2S_PINS["ws"], machine.Pin.OUT),
            sd=machine.Pin(I2S_PINS["sd"], machine.Pin.OUT),
            mode=machine.I2S.TX,
            bits=16,
            format=machine.I2S.MONO,
            rate=self.sample_rate,
            ibuf=8000,
        )

        self._rx = machine.I2S(
            1,
            sck=machine.Pin(I2S_PINS["sck_in"], machine.Pin.OUT),
            ws=machine.Pin(I2S_PINS["ws"], machine.Pin.OUT),
            sd=machine.Pin(I2S_PINS["sd_in"], machine.Pin.IN),
            mode=machine.I2S.RX,
            bits=16,
            format=machine.I2S.MONO,
            rate=self.sample_rate,
            ibuf=8000,
        )

    def _deinit_i2s(self):
        if self._tx:
            self._tx.deinit()
            self._tx = None
        if self._rx:
            self._rx.deinit()
            self._rx = None

    def run(self):
        """Run a short duplex session: play a tone while reading mic data."""
        self._init_i2s()
        try:
            tone = self._make_tone_buffer(freq_hz=440, ms=50)
            read_buf = bytearray(1024)
            t_end = time.ticks_add(time.ticks_ms(), self.duration_ms)

            while time.ticks_diff(t_end, time.ticks_ms()) > 0:
                self._tx.write(tone)
                self._rx.readinto(read_buf)
        finally:
            self._deinit_i2s()

    def _make_tone_buffer(self, freq_hz=440, ms=50):
        samples = int(self.sample_rate * (ms / 1000))
        buf = bytearray(samples * 2)
        for i in range(samples):
            phase = 2 * 3.14159265 * freq_hz * (i / self.sample_rate)
            sample = int(12000 * __import__("math").sin(phase))
            buf[i * 2] = sample & 0xFF
            buf[i * 2 + 1] = (sample >> 8) & 0xFF
        return buf


def run_duplex_test(sample_rate=16000, duration_ms=3000):
    """Convenience entry point for quick manual tests."""
    DuplexI2STest(sample_rate=sample_rate, duration_ms=duration_ms).run()


if __name__ == "__main__":
    run_duplex_test()
