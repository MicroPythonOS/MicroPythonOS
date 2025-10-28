import machine
import os
import time
import micropython


# ----------------------------------------------------------------------
#  AudioPlayer – robust, volume-controllable WAV player (MONO + STEREO)
#  Auto-up-samples any rate < 22050 Hz to 22050 Hz for MAX98357
# ----------------------------------------------------------------------
class AudioPlayer:
    _i2s = None
    _volume = 50          # 0-100
    _keep_running = True

    # ------------------------------------------------------------------
    #  WAV header parser
    # ------------------------------------------------------------------
    @staticmethod
    def find_data_chunk(f):
        """Return (data_start, data_size, sample_rate, channels)"""
        f.seek(0)
        if f.read(4) != b'RIFF':
            raise ValueError("Not a RIFF file")
        file_size = int.from_bytes(f.read(4), 'little') + 8
        if f.read(4) != b'WAVE':
            raise ValueError("Not a WAVE file")

        pos = 12
        sample_rate = None
        channels = None
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
                if int.from_bytes(fmt[14:16], 'little') != 16:
                    raise ValueError("Only 16-bit supported")
            elif chunk_id == b'data':
                return f.tell(), chunk_size, sample_rate, channels
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
    #  Helper: up-sample a raw PCM buffer (zero-order-hold)
    # ------------------------------------------------------------------
    @staticmethod
    def _upsample_buffer(raw: bytearray, factor: int) -> bytearray:
        """
        Duplicate each 16-bit sample `factor` times.
        Input:  interleaved L,R,L,R... (or mono)
        Output: same layout, each sample repeated `factor` times.
        """
        if factor == 1:
            return raw

        upsampled = bytearray(len(raw) * factor)
        out_idx = 0
        # each sample = 2 bytes
        for i in range(0, len(raw), 2):
            lo = raw[i]
            hi = raw[i + 1]
            for _ in range(factor):
                upsampled[out_idx]     = lo
                upsampled[out_idx + 1] = hi
                out_idx += 2
        return upsampled

    # ------------------------------------------------------------------
    #  Main playback routine
    # ------------------------------------------------------------------
    @classmethod
    def play_wav(cls, filename):
        cls._keep_running = True
        try:
            with open(filename, 'rb') as f:
                st = os.stat(filename)
                file_size = st[6]
                print(f"File size: {file_size} bytes")

                # ----- parse header ------------------------------------------------
                data_start, data_size, original_rate, channels = cls.find_data_chunk(f)

                # ----- decide playback rate (force >= 22050 Hz) --------------------
                target_rate = 22050
                if original_rate >= target_rate:
                    playback_rate = original_rate
                    upsample_factor = 1
                else:
                    # find smallest integer factor so original * factor >= target
                    upsample_factor = (target_rate + original_rate - 1) // original_rate
                    playback_rate = original_rate * upsample_factor

                print(f"Original: {original_rate} Hz → Playback: {playback_rate} Hz "
                      f"(factor {upsample_factor}), {channels}-ch")

                if data_size > file_size - data_start:
                    data_size = file_size - data_start

                # ----- I2S init ----------------------------------------------------
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

                print(f"Playing {data_size} original bytes (vol {cls._volume}%) …")
                f.seek(data_start)

                # ----- Viper volume scaler (works on any buffer) -------------------
                @micropython.viper
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

                chunk_size = 4096
                bytes_per_original_sample = 2 * channels   # 2 bytes per channel
                total_original = 0

                while total_original < data_size:
                    if not cls._keep_running:
                        print("Playback stopped by user.")
                        break

                    # read a chunk of *original* data
                    to_read = min(chunk_size, data_size - total_original)
                    to_read -= (to_read % bytes_per_original_sample)
                    if to_read <= 0:
                        break

                    raw = bytearray(f.read(to_read))
                    if not raw:
                        break

                    # ----- up-sample if needed ---------------------------------
                    if upsample_factor > 1:
                        raw = cls._upsample_buffer(raw, upsample_factor)

                    # ----- volume scaling ---------------------------------------
                    scale = cls._volume / 100.0
                    if scale < 1.0:
                        scale_fixed = int(scale * 32768)
                        scale_audio(raw, len(raw), scale_fixed)

                    # ----- output ------------------------------------------------
                    if cls._i2s:
                        cls._i2s.write(raw)
                    else:
                        # simulate timing with the *playback* rate
                        num_samples = len(raw) // (2 * channels)
                        time.sleep(num_samples / playback_rate)

                    total_original += to_read   # count original bytes only

                print("Playback finished.")
        except Exception as e:
            print(f"AudioPlayer error: {e}")
        finally:
            if cls._i2s:
                cls._i2s.deinit()
                cls._i2s = None
