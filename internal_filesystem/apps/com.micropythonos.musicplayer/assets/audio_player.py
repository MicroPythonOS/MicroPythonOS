import os
import time

# ----------------------------------------------------------------------
#  AudioPlayer – robust, volume-controllable WAV player
# ----------------------------------------------------------------------
class AudioPlayer:
    # class-level defaults (shared by every instance)
    _i2s = None          # the I2S object (created once per playback)
    _volume = 100        # 0-100  (100 = full scale)

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
        # If playback is already running we could instantly re-scale the
        # current buffer, but the simple way (scale on each write) is
        # enough and works even if playback starts later.

    @classmethod
    def get_volume(cls) -> int:
        """Return current volume 0-100."""
        return cls._volume

    # ------------------------------------------------------------------
    #  Playback entry point (called from a thread)
    # ------------------------------------------------------------------
    @classmethod
    def play_wav(cls, filename):
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
                    print("Warning: error initializing I2S audio device, simulating playback...")

                print(f"Playing {data_size} bytes (vol {cls._volume}%) …")
                f.seek(data_start)

                chunk_size = 4096                     # 4 KB → safe on ESP32
                scale = cls._volume / 100.0           # float 0.0-1.0

                total = 0
                while total < data_size:
                    to_read = min(chunk_size, data_size - total)
                    raw = f.read(to_read)
                    if not raw:
                        break

                    # ---- on-the-fly volume scaling (16-bit little-endian) ----
                    if scale < 1.0:
                        # convert bytes → array of signed ints → scale → back to bytes
                        import array
                        samples = array.array('h', raw)          # 'h' = signed short
                        for i in range(len(samples)):
                            samples[i] = int(samples[i] * scale)
                        raw = samples.tobytes()
                    # ---------------------------------------------------------

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
