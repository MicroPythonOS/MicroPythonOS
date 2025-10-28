import machine
import os
import time
import micropython


# ----------------------------------------------------------------------
#  AudioPlayer – robust, volume-controllable WAV player (MONO + STEREO)
# ----------------------------------------------------------------------
class AudioPlayer:
    # class-level defaults
    _i2s = None
    _volume = 50        # 0-100
    _keep_running = True

    @staticmethod
    def find_data_chunk(f):
        """Skip chunks until 'data' is found → (data_start, data_size, sample_rate, channels)"""
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

    @classmethod
    def play_wav(cls, filename):
        cls._keep_running = True
        try:
            with open(filename, 'rb') as f:
                st = os.stat(filename)
                file_size = st[6]
                print(f"File size: {file_size} bytes")

                data_start, data_size, sample_rate, channels = cls.find_data_chunk(f)
                print(f"data chunk: {data_size} bytes @ {sample_rate} Hz, {channels}-channel")

                if data_size > file_size - data_start:
                    data_size = file_size - data_start

                # ---- I2S init ------------------------------------------------
                i2s_format = machine.I2S.MONO if channels == 1 else machine.I2S.STEREO
                try:
                    cls._i2s = machine.I2S(
                        0,
                        sck=machine.Pin(2,  machine.Pin.OUT),
                        ws =machine.Pin(47, machine.Pin.OUT),
                        sd =machine.Pin(16, machine.Pin.OUT),
                        mode=machine.I2S.TX,
                        bits=16,
                        format=i2s_format,
                        rate=sample_rate,
                        ibuf=32000
                    )
                except Exception as e:
                    print(f"Warning: simulating playback (I2S init failed): {e}")

                print(f"Playing {data_size} bytes (vol {cls._volume}%) …")
                f.seek(data_start)

                @micropython.viper
                def scale_audio(buf: ptr8, num_bytes: int, scale_fixed: int):
                    # Process 16-bit samples (2 bytes each)
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
                bytes_per_sample = 2 * channels  # 2 bytes per channel
                total = 0

                while total < data_size:
                    if not cls._keep_running:
                        print("Playback stopped by user.")
                        break

                    to_read = min(chunk_size, data_size - total)
                    # Ensure we read full samples
                    to_read -= (to_read % bytes_per_sample)
                    if to_read <= 0:
                        break

                    raw = bytearray(f.read(to_read))
                    if not raw:
                        break

                    # Apply volume scaling (in-place, per sample)
                    scale = cls._volume / 100.0
                    if scale < 1.0:
                        scale_fixed = int(scale * 32768)
                        scale_audio(raw, len(raw), scale_fixed)

                    # Write to I2S (stereo interleaves L,R,L,R...)
                    if cls._i2s:
                        cls._i2s.write(raw)
                    else:
                        # Simulate timing
                        num_samples = len(raw) // bytes_per_sample
                        time.sleep(num_samples / sample_rate)

                    total += len(raw)

                print("Playback finished.")
        except Exception as e:
            print(f"AudioPlayer error: {e}")
        finally:
            if cls._i2s:
                cls._i2s.deinit()
                cls._i2s = None
