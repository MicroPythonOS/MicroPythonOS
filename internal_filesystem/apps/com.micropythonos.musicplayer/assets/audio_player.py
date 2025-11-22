import machine
import os
import time
import micropython


# ----------------------------------------------------------------------
#  AudioPlayer – robust, volume-controllable WAV player
#  Supports 8 / 16 / 24 / 32-bit PCM, mono + stereo
#  Auto-up-samples any rate < 22050 Hz to >=22050 Hz
# ----------------------------------------------------------------------
class AudioPlayer:
    _i2s = None
    _volume = 50 # 0-100
    _keep_running = True

    # ------------------------------------------------------------------
    #  WAV header parser – returns bit-depth
    # ------------------------------------------------------------------
    @staticmethod
    def find_data_chunk(f):
        """Return (data_start, data_size, sample_rate, channels, bits_per_sample)"""
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

    # ------------------------------------------------------------------
    #  Volume control
    # ------------------------------------------------------------------
    @classmethod
    def set_volume(cls, volume: int):
        volume = max(0, min(100, volume))
        cls._volume = volume

    @classmethod
    def get_volume(cls) -> int:
        return cls._volume

    @classmethod
    def stop_playing(cls):
        print("stop_playing()")
        cls._keep_running = False

    # ------------------------------------------------------------------
    #  1. Up-sample 16-bit buffer (zero-order-hold)
    # ------------------------------------------------------------------
    @staticmethod
    def _upsample_buffer(raw: bytearray, factor: int) -> bytearray:
        if factor == 1:
            return raw
        upsampled = bytearray(len(raw) * factor)
        out_idx = 0
        for i in range(0, len(raw), 2):
            lo = raw[i]
            hi = raw[i + 1]
            for _ in range(factor):
                upsampled[out_idx]     = lo
                upsampled[out_idx + 1] = hi
                out_idx += 2
        return upsampled

    # ------------------------------------------------------------------
    #  2. Convert 8-bit to 16-bit (non-viper, Viper-safe)
    # ------------------------------------------------------------------
    @staticmethod
    def _convert_8_to_16(buf: bytearray) -> bytearray:
        out = bytearray(len(buf) * 2)
        j = 0
        for i in range(len(buf)):
            u8 = buf[i]
            s16 = (u8 - 128) << 8
            out[j]     = s16 & 0xFF
            out[j + 1] = (s16 >> 8) & 0xFF
            j += 2
        return out

    # ------------------------------------------------------------------
    #  3. Convert 24-bit to 16-bit (non-viper)
    # ------------------------------------------------------------------
    @staticmethod
    def _convert_24_to_16(buf: bytearray) -> bytearray:
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
            out[i * 2]     = s16 & 0xFF
            out[i * 2 + 1] = (s16 >> 8) & 0xFF
            j += 3
        return out

    # ------------------------------------------------------------------
    #  4. Convert 32-bit to 16-bit (non-viper)
    # ------------------------------------------------------------------
    @staticmethod
    def _convert_32_to_16(buf: bytearray) -> bytearray:
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
            out[i * 2]     = s16 & 0xFF
            out[i * 2 + 1] = (s16 >> 8) & 0xFF
            j += 4
        return out

    # ------------------------------------------------------------------
    #  Main playback routine
    # ------------------------------------------------------------------
    @classmethod
    def play_wav(cls, filename, result_callback=None):
        cls._keep_running = True
        try:
            with open(filename, 'rb') as f:
                st = os.stat(filename)
                file_size = st[6]
                print(f"File size: {file_size} bytes")

                # ----- parse header ------------------------------------------------
                data_start, data_size, original_rate, channels, bits_per_sample = \
                    cls.find_data_chunk(f)

                # ----- decide playback rate (force >=22050 Hz) --------------------
                target_rate = 22050
                if original_rate >= target_rate:
                    playback_rate = original_rate
                    upsample_factor = 1
                else:
                    upsample_factor = (target_rate + original_rate - 1) // original_rate
                    playback_rate = original_rate * upsample_factor

                print(f"Original: {original_rate} Hz, {bits_per_sample}-bit, {channels}-ch "
                      f"to Playback: {playback_rate} Hz (factor {upsample_factor})")

                if data_size > file_size - data_start:
                    data_size = file_size - data_start

                # ----- I2S init (always 16-bit) ----------------------------------
                try:
                    i2s_format = machine.I2S.MONO if channels == 1 else machine.I2S.STEREO
                    cls._i2s = machine.I2S(
                        0,
                        sck=machine.Pin(2,  machine.Pin.OUT),
                        ws =machine.Pin(47, machine.Pin.OUT),
                        sd =machine.Pin(16, machine.Pin.OUT),
                        mode=machine.I2S.TX,
                        bits=16,
                        format=i2s_format,
                        rate=playback_rate,
                        ibuf=32000
                    )
                except Exception as e:
                    print(f"Warning: simulating playback (I2S init failed): {e}")

                print(f"Playing {data_size} original bytes (vol {cls._volume}%) ...")
                f.seek(data_start)

                # Fallback to non-viper and non-functional code on desktop, as macOS/darwin throws "invalid micropython decorator"
                def scale_audio(buf: ptr8, num_bytes: int, scale_fixed: int):
                    pass

                try:
                    # ----- Viper volume scaler (16-bit only) -------------------------
                    @micropython.viper # throws "invalid micropython decorator" on macOS / darwin
                    def scale_audio(buf: ptr8, num_bytes: int, scale_fixed: int):
                        for i in range(0, num_bytes, 2):
                            lo = int(buf[i])
                            hi = int(buf[i+1])
                            sample = (hi << 8) | lo
                            if hi & 128:
                                sample -= 65536
                            sample = (sample * scale_fixed) // 32768
                            if sample > 32767:
                                sample = 32767
                            elif sample < -32768:
                                sample = -32768
                            buf[i] = sample & 255
                            buf[i+1] = (sample >> 8) & 255
                except SyntaxError:
                    print("Viper not supported (e.g., on desktop)—using plain Python.")

                chunk_size = 4096
                bytes_per_original_sample = (bits_per_sample // 8) * channels
                total_original = 0

                while total_original < data_size:
                    if not cls._keep_running:
                        print("Playback stopped by user.")
                        break

                    # ---- read a whole-sample chunk of original data -------------
                    to_read = min(chunk_size, data_size - total_original)
                    to_read -= (to_read % bytes_per_original_sample)
                    if to_read <= 0:
                        break

                    raw = bytearray(f.read(to_read))
                    if not raw:
                        break

                    # ---- 1. Convert bit-depth to 16-bit (non-viper) -------------
                    if bits_per_sample == 8:
                        raw = cls._convert_8_to_16(raw)
                    elif bits_per_sample == 24:
                        raw = cls._convert_24_to_16(raw)
                    elif bits_per_sample == 32:
                        raw = cls._convert_32_to_16(raw)
                    # 16-bit to unchanged

                    # ---- 2. Up-sample if needed ---------------------------------
                    if upsample_factor > 1:
                        raw = cls._upsample_buffer(raw, upsample_factor)

                    # ---- 3. Volume scaling --------------------------------------
                    scale = cls._volume / 100.0
                    if scale < 1.0:
                        scale_fixed = int(scale * 32768)
                        scale_audio(raw, len(raw), scale_fixed)

                    # ---- 4. Output ---------------------------------------------
                    if cls._i2s:
                        cls._i2s.write(raw)
                    else:
                        num_samples = len(raw) // (2 * channels)
                        time.sleep(num_samples / playback_rate)

                    total_original += to_read

                print(f"Finished playing {filename}")
                if result_callback:
                    result_callback(f"Finished playing {filename}")
        except Exception as e:
            print(f"Error: {e}\nwhile playing {filename}")
            if result_callback:
                result_callback(f"Error: {e}\nwhile playing {filename}")
        finally:
            if cls._i2s:
                cls._i2s.deinit()
                cls._i2s = None



def optional_viper(func):
    """Decorator to apply @micropython.viper if possible."""
    try:
        @micropython.viper
        @func  # Wait, no—see below for proper chaining
        def wrapped(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapped
    except SyntaxError:
        return func  # Fallback to original
