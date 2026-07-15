"""Manual benchmark for audio volume scaling performance.


Compares 7 methods of reducing 16-bit stereo audio volume:
  1. i2s.shift(buf, bits=16, shift=-3)           — C software bit-shift (extmod/machine_i2s.c)
  2-4. _scale_audio_optimized (plain/native/viper) — bit-test add
  5-6. _scale_audio (native/viper)                — multiply + divide
  7. _scale_audio_powers_of_2 (viper)             — shift via double-shift trick

Buffer: 22050 Hz stereo 16-bit, ~4120 bytes (~2060 samples).
"""

import micropython
import random
import sys
import time
import unittest


_SAMPLE_RATE = 22050
_CHANNELS = 2
_CHUNK_SECONDS = 1.0 / 10.7
_CHUNK_SAMPLES = int(_SAMPLE_RATE * _CHUNK_SECONDS)
_CHUNK_BYTES = _CHUNK_SAMPLES * _CHANNELS * 2
_ITERATIONS = 100 if sys.platform != "esp32" else 10
_SHIFT = -3
_SHIFT_POS = abs(_SHIFT)  # 3 — for powers_of_2
_SCALE_FIXED = 32768 >> _SHIFT_POS  # 4096


# ---- i2s.shift C equivalent (@native) ------------------------------------

@micropython.native
def _shift_16_native(buf, shift):
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


# ---- _scale_audio_optimized variants (bit-test add) -----------------------

def _scale_opt_none(buf, num_bytes, scale_fixed):
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
        if r > 32767: r = 32767
        if r < -32768: r = -32768
        buf[i] = r & 0xFF
        buf[i + 1] = (r >> 8) & 0xFF


@micropython.native
def _scale_opt_native(buf, num_bytes, scale_fixed):
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
        if r > 32767: r = 32767
        if r < -32768: r = -32768
        buf[i] = r & 0xFF
        buf[i + 1] = (r >> 8) & 0xFF


# ---- _scale_audio variants (multiply + divide) ---------------------------

@micropython.native
def _scale_mul_native(buf, num_bytes, scale_fixed):
    if scale_fixed >= 32768:
        return
    if scale_fixed <= 0:
        for i in range(num_bytes):
            buf[i] = 0
        return
    for i in range(0, num_bytes, 2):
        lo = buf[i]
        hi = buf[i + 1]
        sample = (hi << 8) | lo
        if hi & 0x80:
            sample -= 0x10000
        sample = (sample * scale_fixed) // 32768
        if sample > 32767: sample = 32767
        elif sample < -32768: sample = -32768
        buf[i] = sample & 0xFF
        buf[i + 1] = (sample >> 8) & 0xFF


# ---- viper block ----------------------------------------------------------

try:

    @micropython.viper
    def _scale_opt_viper(buf: ptr8, num_bytes: int, scale_fixed: int):
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

    @micropython.viper
    def _scale_mul_viper(buf: ptr8, num_bytes: int, scale_fixed: int):
        if scale_fixed >= 32768:
            return
        if scale_fixed <= 0:
            for i in range(num_bytes):
                buf[i] = 0
            return
        for i in range(0, num_bytes, 2):
            lo: int = int(buf[i])
            hi: int = int(buf[i + 1])
            sample: int = (hi << 8) | lo
            if hi & 128:
                sample -= 65536
            sample = (sample * scale_fixed) // 32768
            if sample > 32767: sample = 32767
            elif sample < -32768: sample = -32768
            buf[i] = sample & 255
            buf[i + 1] = (sample >> 8) & 255

    @micropython.viper
    def _scale_powers_of_2(buf: ptr8, num_bytes: int, shift: int):
        if shift <= 0:
            return
        if shift >= 16:
            for i in range(num_bytes):
                buf[i] = 0
            return
        inv_shift: int = 16 - shift
        for i in range(0, num_bytes, 2):
            s: int = int(buf[i]) | (int(buf[i + 1]) << 8)
            if s & 0x8000:
                s |= -65536
            s <<= inv_shift
            s >>= 16
            buf[i] = s & 0xFF
            buf[i + 1] = (s >> 8) & 0xFF

    _HAS_VIPER = True
except (SyntaxError, NameError, TypeError):
    _HAS_VIPER = False


# ---- benchmark harness ----------------------------------------------------

def _us(start, end=None):
    if end is None:
        end = time.ticks_us()
    return time.ticks_diff(end, start)


def _make_buf():
    buf = bytearray(_CHUNK_BYTES)
    for i in range(_CHUNK_BYTES):
        buf[i] = random.randint(0, 255)
    return buf


def _decode_s16(buf, idx):
    sample_idx = idx * 2
    lo = buf[sample_idx]
    hi = buf[sample_idx + 1]
    val = lo | (hi << 8)
    if hi & 0x80:
        val -= 0x10000
    return val


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
            platform_label = "esp32 (C)"
        else:
            shift_func = lambda b: _shift_16_native(b, _SHIFT)
            platform_label = "desktop (@native equiv)"

        run = self._run_one

        run("i2s.shift %-13s" % platform_label, shift_func, _make_buf())

        print("--- _scale_audio_optimized (bit-test add) ---")
        run("  _scale_opt_none     ", lambda b: _scale_opt_none(b, len(b), _SCALE_FIXED), _make_buf())
        run("  _scale_opt_native   ", lambda b: _scale_opt_native(b, len(b), _SCALE_FIXED), _make_buf())
        if _HAS_VIPER:
            run("  _scale_opt_viper    ", lambda b: _scale_opt_viper(b, len(b), _SCALE_FIXED), _make_buf())

        print("--- _scale_audio (multiply + divide) ---")
        run("  _scale_mul_native   ", lambda b: _scale_mul_native(b, len(b), _SCALE_FIXED), _make_buf())
        if _HAS_VIPER:
            run("  _scale_mul_viper    ", lambda b: _scale_mul_viper(b, len(b), _SCALE_FIXED), _make_buf())

        print("--- _scale_audio_powers_of_2 ---")
        if _HAS_VIPER:
            run("  _scale_powers_of_2  ", lambda b: _scale_powers_of_2(b, len(b), _SHIFT_POS), _make_buf())
        else:
            print("  _scale_powers_of_2  : not available")

        if not _HAS_VIPER:
            print("(@viper not available on this platform)")

        if sys.platform == "esp32":
            i2s.deinit()

        print("--- end benchmark ---\n")
        self.assertTrue(True)

    def _run_one(self, label, func, buf):
        _CHECK_COUNT = min(10, _CHUNK_SAMPLES)
        check_buf = bytearray(buf)
        pre = [_decode_s16(check_buf, i) for i in range(_CHECK_COUNT)]
        func(check_buf)
        ok = self._verify_scaled(check_buf, pre, label)

        start = time.ticks_us()
        for _ in range(_ITERATIONS):
            func(buf)
        elapsed_us = _us(start)
        avg_us = elapsed_us / _ITERATIONS
        status = "OK" if ok else "FAIL"
        print("%s: %d µs total, %.0f µs/call [%s]" % (label, elapsed_us, avg_us, status))

    def _verify_scaled(self, buf, pre, label):
        for i, original in enumerate(pre):
            actual = _decode_s16(buf, i)
            expected = original >> 3  # arithmetic shift by _SHIFT_POS=3
            if actual != expected:
                print("  SANITY FAIL sample[%d]: orig=%d, expected=%d, actual=%d" % (i, original, expected, actual))
                return False
        return True


if __name__ == "__main__":
    unittest.main()
