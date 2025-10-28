import machine
import os
import time
import micropython


# ----------------------------------------------------------------------
#  AudioPlayer – robust, volume-controllable WAV player
# ----------------------------------------------------------------------
class AudioPlayer:
    # class-level defaults (shared by every instance)
    _i2s = None          # the I2S object (created once per playback)
    _volume = 50        # 0-100  (100 = full scale)
    _keep_running = True

    @staticmethod
    def find_data_chunk(f):
        """Skip chunks until 'data' is found → (data_start, data_size, sample_rate)"""
        f.seek(0)
        if f.read(4) != b'RIFF':
            raise ValueError("Not a RIFF file")
        file_size = int.from_bytes(f.read(4), 'little') + 8
        if f.read(4) != b'WAVE':
            raise ValueError("Not a WAVE file")

        pos = 12
        sample_rate = None
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
                if channels != 1:
                    raise ValueError("Only mono supported")
                sample_rate = int.from_bytes(fmt[4:8], 'little')
                if int.from_bytes(fmt[14:16], 'little') != 16:
                    raise ValueError("Only 16-bit supported")
            elif chunk_id == b'data':
                return f.tell(), chunk_size, sample_rate
            # next chunk (pad byte if odd length)
            pos += 8 + chunk_size
            if chunk_size % 2:
                pos += 1
        raise ValueError("No 'data' chunk found")

    # ------------------------------------------------------------------
    #  Volume control
    # ------------------------------------------------------------------
    @classmethod
    def set_volume(cls, volume: int):
        """Set playback volume 0-100 (100 = full scale)."""
        volume = max(0, min(100, volume))          # clamp
        cls._volume = volume

    @classmethod
    def get_volume(cls) -> int:
        """Return current volume 0-100."""
        return cls._volume

    #@classmethod
    def stop_playing():
        print("stop_playing()")
        AudioPlayer._keep_running = False

    @classmethod
    def play_wav(cls, filename):
        AudioPlayer._keep_running = True
        """Play a large mono 16-bit PCM WAV file with on-the-fly volume."""
        try:
            with open(filename, 'rb') as f:
                st = os.stat(filename)
                file_size = st[6]
                print(f"File size: {file_size} bytes")

                data_start, data_size, sample_rate = cls.find_data_chunk(f)
                print(f"data chunk: {data_size} bytes @ {sample_rate} Hz")

                if data_size > file_size - data_start:
                    data_size = file_size - data_start

                # ---- I2S init ------------------------------------------------
                try:
                    cls._i2s = machine.I2S(
                        0,
                        sck=machine.Pin(2,  machine.Pin.OUT),
                        ws =machine.Pin(47, machine.Pin.OUT),
                        sd =machine.Pin(16, machine.Pin.OUT),
                        mode=machine.I2S.TX,
                        bits=16,
                        format=machine.I2S.MONO,
                        rate=sample_rate,
                        ibuf=32000
                    )
                except Exception as e:
                    print(f"Warning: simulating playback due to error initializing I2S audio device: {e}")

                print(f"Playing {data_size} bytes (vol {cls._volume}%) …")
                f.seek(data_start)

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

                chunk_size = 4096                     # 4 KB → safe on ESP32

                total = 0
                while total < data_size:
                    # Progress:
                    #if total % 51 == 0:
                    #    print('.', end='')
                    if not AudioPlayer._keep_running:
                        print("_keep_running = False, stopping...")
                        break
                    to_read = min(chunk_size, data_size - total)
                    raw = bytearray(f.read(to_read))  # mutable for in-place scaling
                    if not raw:
                        break

                    # ---- fast viper scaling (in-place) ----
                    scale = cls._volume / 100.0           # adjust the volume on the fly instead of at the start of playback
                    if scale < 1.0:
                        scale_fixed = int(scale * 32768)
                        scale_audio(raw, len(raw), scale_fixed)
                    # ---------------------------------------

                    if cls._i2s:
                        cls._i2s.write(raw)
                    else:
                        time.sleep((to_read/2)/44100) # 16 bits (2 bytes) per sample at 44100 samples/s
                    total += len(raw)

                print("Playback finished.")
        except Exception as e:
            print(f"AudioPlayer error: {e}")
        finally:
            if cls._i2s:
                cls._i2s.deinit()
                cls._i2s = None
