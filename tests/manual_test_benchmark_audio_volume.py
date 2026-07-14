"""Manual benchmark for audio volume scaling performance.

Run with:
    ./tests/unittest.sh --ondevice tests/manual_test_benchmark_audio_volume.py

Compares 4 methods of reducing 16-bit stereo audio volume:
  1. i2s.shift(buf, bits=16, shift=-3)          — hardware bit-shift
  2. _scale_none(buf, num_bytes, scale_fixed)   — plain Python
  3. _scale_native(buf, num_bytes, scale_fixed) — @micropython.native
  4. _scale_viper(buf, num_bytes, scale_fixed)  — @micropython.viper

Buffer: 22050 Hz stereo 16-bit, ~4120 bytes (~2060 samples).
"""

import micropython
import random
import sys
import time
import unittest


_SAMPLE_RATE = 22050
_CHANNELS = 2
_CHUNK_SECONDS = 1.0 / 10.7  # matches stream_wav chunk size
_CHUNK_SAMPLES = int(_SAMPLE_RATE * _CHUNK_SECONDS)
_CHUNK_BYTES = _CHUNK_SAMPLES * _CHANNELS * 2
_ITERATIONS = 10
_SHIFT = -3
_SCALE_FIXED = 32768 >> abs(_SHIFT)  # 4096 — equivalent volume reduction


@micropython.native
def _shift_16_native(buf, shift):
    """Equivalent to C i2s.shift for bits=16: arithmetic right-shift
    each signed int16_t in-place, matching extmod/machine_i2s.c."""
    n = len(buf) // 2
    ashift = -shift if shift < 0 else shift
    for i in range(n):
        lo = buf[i * 2]
        hi = buf[i * 2 + 1]
        val = lo | (hi << 8)
        if hi & 0x80:
            val -= 0x10000
        if shift < 0:
            val >>= ashift
        else:
            val <<= ashift
        val &= 0xFFFF
        buf[i * 2] = val & 0xFF
        buf[i * 2 + 1] = (val >> 8) & 0xFF


def _scale_none(buf, num_bytes, scale_fixed):
    """_scale_audio_optimized — plain Python (no decorator)."""
    if scale_fixed >= 32768:
        return
    if scale_fixed <= 0:
        for i in range(num_bytes):
            buf[i] = 0
        return

    mask = scale_fixed

    for i in range(0, num_bytes, 2):
        s = buf[i] | (buf[i + 1] << 8)
        if s >= 0x8000:
            s -= 0x10000

        r = 0
        if mask & 0x8000: r += s
        if mask & 0x4000: r += s >> 1
        if mask & 0x2000: r += s >> 2
        if mask & 0x1000: r += s >> 3
        if mask & 0x0800: r += s >> 4
        if mask & 0x0400: r += s >> 5
        if mask & 0x0200: r += s >> 6
        if mask & 0x0100: r += s >> 7
        if mask & 0x0080: r += s >> 8
        if mask & 0x0040: r += s >> 9
        if mask & 0x0020: r += s >> 10
        if mask & 0x0010: r += s >> 11
        if mask & 0x0008: r += s >> 12
        if mask & 0x0004: r += s >> 13
        if mask & 0x0002: r += s >> 14
        if mask & 0x0001: r += s >> 15

        if r > 32767:
            r = 32767
        if r < -32768:
            r = -32768

        buf[i] = r & 0xFF
        buf[i + 1] = (r >> 8) & 0xFF


@micropython.native
def _scale_native(buf, num_bytes, scale_fixed):
    """_scale_audio_optimized — @micropython.native."""
    if scale_fixed >= 32768:
        return
    if scale_fixed <= 0:
        for i in range(num_bytes):
            buf[i] = 0
        return

    mask = scale_fixed

    for i in range(0, num_bytes, 2):
        s = buf[i] | (buf[i + 1] << 8)
        if s >= 0x8000:
            s -= 0x10000

        r = 0
        if mask & 0x8000: r += s
        if mask & 0x4000: r += s >> 1
        if mask & 0x2000: r += s >> 2
        if mask & 0x1000: r += s >> 3
        if mask & 0x0800: r += s >> 4
        if mask & 0x0400: r += s >> 5
        if mask & 0x0200: r += s >> 6
        if mask & 0x0100: r += s >> 7
        if mask & 0x0080: r += s >> 8
        if mask & 0x0040: r += s >> 9
        if mask & 0x0020: r += s >> 10
        if mask & 0x0010: r += s >> 11
        if mask & 0x0008: r += s >> 12
        if mask & 0x0004: r += s >> 13
        if mask & 0x0002: r += s >> 14
        if mask & 0x0001: r += s >> 15

        if r > 32767:
            r = 32767
        if r < -32768:
            r = -32768

        buf[i] = r & 0xFF
        buf[i + 1] = (r >> 8) & 0xFF


try:
    @micropython.viper
    def _scale_viper(buf: ptr8, num_bytes: int, scale_fixed: int):
        if scale_fixed >= 32768:
            return
        if scale_fixed <= 0:
            for i in range(num_bytes):
                buf[i] = 0
            return

        mask: int = scale_fixed

        for i in range(0, num_bytes, 2):
            s: int = int(buf[i]) | (int(buf[i + 1]) << 8)
            if s & 0x8000:
                s -= 0x10000

            r: int = 0
            if mask & 0x8000: r += s
            if mask & 0x4000: r += s >> 1
            if mask & 0x2000: r += s >> 2
            if mask & 0x1000: r += s >> 3
            if mask & 0x0800: r += s >> 4
            if mask & 0x0400: r += s >> 5
            if mask & 0x0200: r += s >> 6
            if mask & 0x0100: r += s >> 7
            if mask & 0x0080: r += s >> 8
            if mask & 0x0040: r += s >> 9
            if mask & 0x0020: r += s >> 10
            if mask & 0x0010: r += s >> 11
            if mask & 0x0008: r += s >> 12
            if mask & 0x0004: r += s >> 13
            if mask & 0x0002: r += s >> 14
            if mask & 0x0001: r += s >> 15

            if r > 32767:  r = 32767
            if r < -32768: r = -32768

            buf[i] = r & 0xFF
            buf[i + 1] = (r >> 8) & 0xFF

    _HAS_VIPER = True
except (SyntaxError, NameError, TypeError):
    _HAS_VIPER = False


def _ms(start, end=None):
    if end is None:
        end = time.ticks_ms()
    return time.ticks_diff(end, start)


def _make_buf():
    buf = bytearray(_CHUNK_BYTES)
    for i in range(_CHUNK_BYTES):
        buf[i] = random.randint(0, 255)
    return buf


class BenchmarkI2SShift(unittest.TestCase):
    def test_benchmark_shift(self):
        print(
            "\n--- Audio volume scaling benchmark ---\n"
            "buffer: %d bytes, %d samples, %d ch @ %d Hz, %d iterations\n"
            "shift: %d, scale_fixed: %d (equiv. volume: %.1f%%)\n"
            % (_CHUNK_BYTES, _CHUNK_SAMPLES, _CHANNELS, _SAMPLE_RATE,
               _ITERATIONS, _SHIFT, _SCALE_FIXED, _SCALE_FIXED / 32768.0 * 100)
        )

        if sys.platform == "esp32":
            import machine
            i2s = machine.I2S(
                0,
                sck=machine.Pin(15, machine.Pin.OUT),
                ws=machine.Pin(13, machine.Pin.OUT),
                sd=machine.Pin(12, machine.Pin.OUT),
                mode=machine.I2S.TX,
                bits=16,
                format=machine.I2S.STEREO,
                rate=_SAMPLE_RATE,
                ibuf=8192,
            )
            shift_func = lambda b: i2s.shift(buf=b, bits=16, shift=_SHIFT)
            platform_label = "esp32 (hw i2s.shift)"
        else:
            shift_func = lambda b: _shift_16_native(b, _SHIFT)
            platform_label = "desktop (@native i2s.shift equiv)"

        self._run_one("i2s.shift (%s)" % platform_label, shift_func, _make_buf())

        self._run_one("plain Python  ", lambda b: _scale_none(b, len(b), _SCALE_FIXED), _make_buf())
        self._run_one("@native       ", lambda b: _scale_native(b, len(b), _SCALE_FIXED), _make_buf())

        if _HAS_VIPER:
            self._run_one("@viper        ", lambda b: _scale_viper(b, len(b), _SCALE_FIXED), _make_buf())
        else:
            print("@viper        : not available on this platform")

        if sys.platform == "esp32":
            i2s.deinit()

        print("--- end benchmark ---\n")
        self.assertTrue(True)

    def _run_one(self, label, func, buf):
        start = time.ticks_ms()
        for _ in range(_ITERATIONS):
            func(buf)
        elapsed = _ms(start)
        avg_ms = elapsed / _ITERATIONS
        print("%s: %d ms total, %.2f ms/call" % (label, elapsed, avg_ms))


if __name__ == "__main__":
    unittest.main()
