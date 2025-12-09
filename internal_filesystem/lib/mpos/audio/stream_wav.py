# WAVStream - WAV File Playback Stream for AudioFlinger
# Supports 8/16/24/32-bit PCM, mono+stereo, auto-upsampling, volume control
# Ported from MusicPlayer's AudioPlayer class

import machine
import micropython
import os
import time
import sys

# Volume scaling function - Viper-optimized for ESP32 performance
# NOTE: The line below is automatically commented out by build_mpos.sh during
# Unix/macOS builds (cross-compiler doesn't support Viper), then uncommented after build.
@micropython.viper
def _scale_audio(buf: ptr8, num_bytes: int, scale_fixed: int):
    """Fast volume scaling for 16-bit audio samples using Viper (ESP32 native code emitter)."""
    for i in range(0, num_bytes, 2):
        lo = int(buf[i])
        hi = int(buf[i + 1])
        sample = (hi << 8) | lo
        if hi & 128:
            sample -= 65536
        sample = (sample * scale_fixed) // 32768
        if sample > 32767:
            sample = 32767
        elif sample < -32768:
            sample = -32768
        buf[i] = sample & 255
        buf[i + 1] = (sample >> 8) & 255

@micropython.viper
def _scale_audio_optimized(buf: ptr8, num_bytes: int, scale_fixed: int):
    if scale_fixed >= 32768:
        return
    if scale_fixed <= 0:
        for i in range(num_bytes):
            buf[i] = 0
        return

    mask: int = scale_fixed

    for i in range(0, num_bytes, 2):
        s: int = int(buf[i]) | (int(buf[i+1]) << 8)
        if s >= 0x8000:
            s -= 0x10000

        r: int = 0
        if mask & 0x8000: r += s
        if mask & 0x4000: r += s>>1
        if mask & 0x2000: r += s>>2
        if mask & 0x1000: r += s>>3
        if mask & 0x0800: r += s>>4
        if mask & 0x0400: r += s>>5
        if mask & 0x0200: r += s>>6
        if mask & 0x0100: r += s>>7
        if mask & 0x0080: r += s>>8
        if mask & 0x0040: r += s>>9
        if mask & 0x0020: r += s>>10
        if mask & 0x0010: r += s>>11
        if mask & 0x0008: r += s>>12
        if mask & 0x0004: r += s>>13
        if mask & 0x0002: r += s>>14
        if mask & 0x0001: r += s>>15

        if r > 32767:  r = 32767
        if r < -32768: r = -32768

        buf[i]   = r & 0xFF
        buf[i+1] = (r >> 8) & 0xFF

@micropython.viper
def _scale_audio_rough(buf: ptr8, num_bytes: int, scale_fixed: int):
    """Rough volume scaling for 16-bit audio samples using right shifts for performance."""
    if scale_fixed >= 32768:
        return

    # Determine the shift amount
    shift: int = 0
    threshold: int = 32768
    while shift < 16 and scale_fixed < threshold:
        shift += 1
        threshold >>= 1

    # If shift is 16 or more, set buffer to zero (volume too low)
    if shift >= 16:
        for i in range(num_bytes):
            buf[i] = 0
        return

    # Apply right shift to each 16-bit sample
    for i in range(0, num_bytes, 2):
        lo: int = int(buf[i])
        hi: int = int(buf[i + 1])
        sample: int = (hi << 8) | lo
        if hi & 128:
            sample -= 65536
        sample >>= shift
        buf[i] = sample & 255
        buf[i + 1] = (sample >> 8) & 255

@micropython.viper
def _scale_audio_shift(buf: ptr8, num_bytes: int, shift: int):
    """Rough volume scaling for 16-bit audio samples using right shifts for performance."""
    if shift <= 0:
        return

    # If shift is 16 or more, set buffer to zero (volume too low)
    if shift >= 16:
        for i in range(num_bytes):
            buf[i] = 0
        return

    # Apply right shift to each 16-bit sample
    for i in range(0, num_bytes, 2):
        lo: int = int(buf[i])
        hi: int = int(buf[i + 1])
        sample: int = (hi << 8) | lo
        if hi & 128:
            sample -= 65536
        sample >>= shift
        buf[i] = sample & 255
        buf[i + 1] = (sample >> 8) & 255

@micropython.viper
def _scale_audio_powers_of_2(buf: ptr8, num_bytes: int, shift: int):
    if shift <= 0:
        return
    if shift >= 16:
        for i in range(num_bytes):
            buf[i] = 0
        return

    # Unroll the sign-extend + shift into one tight loop with no inner branch
    inv_shift: int = 16 - shift
    for i in range(0, num_bytes, 2):
        s: int = int(buf[i]) | (int(buf[i+1]) << 8)
        if s & 0x8000:              # only one branch, highly predictable when shift fixed shift
            s |= -65536             # sign extend using OR (faster than subtract!)
        s <<= inv_shift             # bring the bits we want into lower 16
        s >>= 16                    # arithmetic shift right by 'shift' amount
        buf[i]   = s & 0xFF
        buf[i+1] = (s >> 8) & 0xFF

class WAVStream:
    """
    WAV file playback stream with I2S output.
    Supports 8/16/24/32-bit PCM, mono and stereo, auto-upsampling to >=22050 Hz.
    """

    def __init__(self, file_path, stream_type, volume, i2s_pins, on_complete):
        """
        Initialize WAV stream.

        Args:
            file_path: Path to WAV file
            stream_type: Stream type (STREAM_MUSIC, STREAM_NOTIFICATION, STREAM_ALARM)
            volume: Volume level (0-100)
            i2s_pins: Dict with 'sck', 'ws', 'sd' pin numbers
            on_complete: Callback function(message) when playback finishes
        """
        self.file_path = file_path
        self.stream_type = stream_type
        self.volume = volume
        self.i2s_pins = i2s_pins
        self.on_complete = on_complete
        self._keep_running = True
        self._is_playing = False
        self._i2s = None

    def is_playing(self):
        """Check if stream is currently playing."""
        return self._is_playing

    def stop(self):
        """Stop playback."""
        self._keep_running = False

    # ----------------------------------------------------------------------
    #  WAV header parser - returns bit-depth and format info
    # ----------------------------------------------------------------------
    @staticmethod
    def _find_data_chunk(f):
        """
        Parse WAV header and find data chunk.

        Returns:
            tuple: (data_start, data_size, sample_rate, channels, bits_per_sample)
        """
        f.seek(0)
        if f.read(4) != b'RIFF':
            raise ValueError("Not a RIFF (standard .wav) file")

        file_size = int.from_bytes(f.read(4), 'little') + 8

        if f.read(4) != b'WAVE':
            raise ValueError("Not a WAVE (standard .wav) file")

        pos = 12
        sample_rate = None
        channels = None
        bits_per_sample = None

        while pos < file_size:
            f.seek(pos)
            chunk_id = f.read(4)
            if len(chunk_id) < 4:
                break

            chunk_size = int.from_bytes(f.read(4), 'little')

            if chunk_id == b'fmt ':
                fmt = f.read(chunk_size)
                if len(fmt) < 16:
                    raise ValueError("Invalid fmt chunk")

                if int.from_bytes(fmt[0:2], 'little') != 1:
                    raise ValueError("Only PCM supported")

                channels = int.from_bytes(fmt[2:4], 'little')
                if channels not in (1, 2):
                    raise ValueError("Only mono or stereo supported")

                sample_rate = int.from_bytes(fmt[4:8], 'little')
                bits_per_sample = int.from_bytes(fmt[14:16], 'little')

                if bits_per_sample not in (8, 16, 24, 32):
                    raise ValueError("Only 8/16/24/32-bit PCM supported")

            elif chunk_id == b'data':
                return f.tell(), chunk_size, sample_rate, channels, bits_per_sample

            pos += 8 + chunk_size
            if chunk_size % 2:
                pos += 1

        raise ValueError("No 'data' chunk found")

    # ----------------------------------------------------------------------
    #  Bit depth conversion functions
    # ----------------------------------------------------------------------
    @staticmethod
    def _convert_8_to_16(buf):
        """Convert 8-bit unsigned PCM to 16-bit signed PCM."""
        out = bytearray(len(buf) * 2)
        j = 0
        for i in range(len(buf)):
            u8 = buf[i]
            s16 = (u8 - 128) << 8
            out[j] = s16 & 0xFF
            out[j + 1] = (s16 >> 8) & 0xFF
            j += 2
        return out

    @staticmethod
    def _convert_24_to_16(buf):
        """Convert 24-bit PCM to 16-bit PCM."""
        samples = len(buf) // 3
        out = bytearray(samples * 2)
        j = 0
        for i in range(samples):
            b0 = buf[j]
            b1 = buf[j + 1]
            b2 = buf[j + 2]
            s24 = (b2 << 16) | (b1 << 8) | b0
            if b2 & 0x80:
                s24 -= 0x1000000
            s16 = s24 >> 8
            out[i * 2] = s16 & 0xFF
            out[i * 2 + 1] = (s16 >> 8) & 0xFF
            j += 3
        return out

    @staticmethod
    def _convert_32_to_16(buf):
        """Convert 32-bit PCM to 16-bit PCM."""
        samples = len(buf) // 4
        out = bytearray(samples * 2)
        j = 0
        for i in range(samples):
            b0 = buf[j]
            b1 = buf[j + 1]
            b2 = buf[j + 2]
            b3 = buf[j + 3]
            s32 = (b3 << 24) | (b2 << 16) | (b1 << 8) | b0
            if b3 & 0x80:
                s32 -= 0x100000000
            s16 = s32 >> 16
            out[i * 2] = s16 & 0xFF
            out[i * 2 + 1] = (s16 >> 8) & 0xFF
            j += 4
        return out

    # ----------------------------------------------------------------------
    #  Upsampling (zero-order-hold)
    # ----------------------------------------------------------------------
    @staticmethod
    def _upsample_buffer(raw, factor):
        """Upsample 16-bit buffer by repeating samples."""
        if factor == 1:
            return raw

        upsampled = bytearray(len(raw) * factor)
        out_idx = 0
        for i in range(0, len(raw), 2):
            lo = raw[i]
            hi = raw[i + 1]
            for _ in range(factor):
                upsampled[out_idx] = lo
                upsampled[out_idx + 1] = hi
                out_idx += 2
        return upsampled

    # ----------------------------------------------------------------------
    #  Main playback routine
    # ----------------------------------------------------------------------
    def play(self):
        """Main playback routine (runs in background thread)."""
        self._is_playing = True

        try:
            with open(self.file_path, 'rb') as f:
                st = os.stat(self.file_path)
                file_size = st[6]
                print(f"WAVStream: Playing {self.file_path} ({file_size} bytes)")

                # Parse WAV header
                data_start, data_size, original_rate, channels, bits_per_sample = \
                    self._find_data_chunk(f)

                # Decide playback rate (force >=22050 Hz) - but why?! the DAC should support down to 8kHz!
                target_rate = 22050
                if original_rate >= target_rate:
                    playback_rate = original_rate
                    upsample_factor = 1
                else:
                    upsample_factor = (target_rate + original_rate - 1) // original_rate
                    playback_rate = original_rate * upsample_factor

                print(f"WAVStream: {original_rate} Hz, {bits_per_sample}-bit, {channels}-ch")
                print(f"WAVStream: Playback at {playback_rate} Hz (factor {upsample_factor})")

                if data_size > file_size - data_start:
                    data_size = file_size - data_start

                # Initialize I2S (always 16-bit output)
                try:
                    i2s_format = machine.I2S.MONO if channels == 1 else machine.I2S.STEREO
                    self._i2s = machine.I2S(
                        0,
                        sck=machine.Pin(self.i2s_pins['sck'], machine.Pin.OUT),
                        ws=machine.Pin(self.i2s_pins['ws'], machine.Pin.OUT),
                        sd=machine.Pin(self.i2s_pins['sd'], machine.Pin.OUT),
                        mode=machine.I2S.TX,
                        bits=16,
                        format=i2s_format,
                        rate=playback_rate,
                        ibuf=32000
                    )
                except Exception as e:
                    print(f"WAVStream: I2S init failed: {e}")
                    return

                print(f"WAVStream: Playing {data_size} bytes (volume {self.volume}%)")
                f.seek(data_start)

                # smaller chunk size means less jerks but buffer can run empty
                # at 22050 Hz, 16-bit, 2-ch, 4096/4 = 1024 samples / 22050 = 46ms
                # with rough volume scaling:
                # 4096 => audio stutters during quasibird at ~20fps
                # 8192 => no audio stutters and quasibird runs at ~16 fps => good compromise!
                # 16384 => no audio stutters during quasibird but low framerate (~8fps)
                # with optimized volume scaling:
                # 6144 => audio stutters and quasibird at ~17fps
                # 7168 => audio slightly stutters and quasibird at ~16fps
                # 8192 => no audio stutters and quasibird runs at ~15-17fps => this is probably best
                # with shift volume scaling:
                # 6144 => audio slightly stutters and quasibird at ~16fps?!
                # 8192 => no audio stutters, quasibird runs at ~13fps?!
                # with power of 2 thing:
                # 6144 => audio sutters and quasibird at ~18fps
                # 8192 => no audio stutters, quasibird runs at ~14fps
                chunk_size = 8192
                bytes_per_original_sample = (bits_per_sample // 8) * channels
                total_original = 0

                while total_original < data_size:
                    if not self._keep_running:
                        print("WAVStream: Playback stopped by user")
                        break

                    # Read chunk of original data
                    to_read = min(chunk_size, data_size - total_original)
                    to_read -= (to_read % bytes_per_original_sample)
                    if to_read <= 0:
                        break

                    raw = bytearray(f.read(to_read))
                    if not raw:
                        break

                    # 1. Convert bit-depth to 16-bit
                    if bits_per_sample == 8:
                        raw = self._convert_8_to_16(raw)
                    elif bits_per_sample == 24:
                        raw = self._convert_24_to_16(raw)
                    elif bits_per_sample == 32:
                        raw = self._convert_32_to_16(raw)
                    # 16-bit unchanged

                    # 2. Upsample if needed
                    if upsample_factor > 1:
                        raw = self._upsample_buffer(raw, upsample_factor)

                    # 3. Volume scaling
                    #shift = 16 - int(self.volume / 6.25)
                    #_scale_audio_powers_of_2(raw, len(raw), shift)
                    scale = self.volume / 100.0
                    if scale < 1.0:
                        scale_fixed = int(scale * 32768)
                        _scale_audio_optimized(raw, len(raw), scale_fixed)

                    # 4. Output to I2S
                    if self._i2s:
                        self._i2s.write(raw)
                    else:
                        # Simulate playback timing if no I2S
                        num_samples = len(raw) // (2 * channels)
                        time.sleep(num_samples / playback_rate)

                    total_original += to_read

                print(f"WAVStream: Finished playing {self.file_path}")
                if self.on_complete:
                    self.on_complete(f"Finished: {self.file_path}")

        except Exception as e:
            print(f"WAVStream: Error: {e}")
            if self.on_complete:
                self.on_complete(f"Error: {e}")

        finally:
            self._is_playing = False
            if self._i2s:
                self._i2s.deinit()
                self._i2s = None

    def set_volume(self, vol):
        self.volume = vol
