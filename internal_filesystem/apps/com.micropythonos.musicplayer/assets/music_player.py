from mpos.apps import Activity
import mpos.sdcard
import mpos.ui
# play music
import machine
import uos
from machine import I2S, Pin

class MusicPlayer(Activity):

    # Widgets:
    file_explorer = None

    def onCreate(self):
        screen = lv.obj()
        # the user might have recently plugged in the sd card so try to mount it
        mpos.sdcard.mount_with_optional_format('/sdcard')
        self.file_explorer = lv.file_explorer(screen)
        self.file_explorer.explorer_open_dir('M:/')
        self.file_explorer.align(lv.ALIGN.CENTER, 0, 0)
        self.file_explorer.add_event_cb(self.file_explorer_event_cb, lv.EVENT.ALL, None)
        self.setContentView(screen)

    def onResume(self, screen):
        # the user might have recently plugged in the sd card so try to mount it
        mpos.sdcard.mount_with_optional_format('/sdcard') # would be good to refresh the file_explorer so the /sdcard folder shows up

    def file_explorer_event_cb(self, event):
        event_code = event.get_code()
        if event_code not in [2,19,23,24,25,26,27,28,29,30,31,32,33,47,49,52]:
            name = mpos.ui.get_event_name(event_code)
            print(f"file_explorer_event_cb {event_code} with name {name}")
            if event_code == lv.EVENT.VALUE_CHANGED:
                path = self.file_explorer.explorer_get_current_path()
                clean_path = path[2:] if path[1] == ':' else path
                file = self.file_explorer.explorer_get_selected_file_name()
                fullpath = f"{clean_path}{file}"
                print(f"Selected: {fullpath}")
                if fullpath.lower().endswith('.wav'):
                    self.play_wav(fullpath)
                else:
                    print("INFO: ignoring unsupported file format")

    def parse_wav_header(self, f):
        """Parse standard WAV header (44 bytes) and return channels, sample_rate, bits_per_sample, data_size."""
        header = f.read(44)
        if header[0:4] != b'RIFF' or header[8:12] != b'WAVE' or header[12:16] != b'fmt ':
            raise ValueError("Invalid WAV file")
        audio_format = int.from_bytes(header[20:22], 'little')
        if audio_format != 1:  # PCM only
            raise ValueError("Only PCM WAV supported")
        channels = int.from_bytes(header[22:24], 'little')
        sample_rate = int.from_bytes(header[24:28], 'little')
        bits_per_sample = int.from_bytes(header[34:36], 'little')
        # Skip to data chunk
        f.read(8)  # 'data' + size
        data_size = int.from_bytes(f.read(4), 'little')
        return channels, sample_rate, bits_per_sample, data_size

    def play_wav(self, filename):
        """Play WAV file via I2S to MAX98357A."""
        with open(filename, 'rb') as f:
            try:
                channels, sample_rate, bits_per_sample, data_size = self.parse_wav_header(f)
                if bits_per_sample != 16:
                    raise ValueError("Only 16-bit audio supported")
                if channels != 1:
                    raise ValueError("Only mono audio supported (convert with -ac 1 in FFmpeg)")
	
                # Configure I2S (TX mode for output)
                i2s = I2S(0,  # I2S peripheral 0
                        sck=Pin(2, Pin.OUT),      # BCK
                        ws=Pin(47, Pin.OUT),      # LRCK
                        sd=Pin(16, Pin.OUT),      # DIN
                        mode=I2S.TX,
                        bits=16,
                        format=I2S.MONO,
                        rate=sample_rate,
                        ibuf=16000)  # Internal buffer size (adjust if audio stutters)

                print(f"Playing {data_size} bytes at {sample_rate} Hz...")

                # Stream data in chunks (16-bit = 2 bytes per sample)
                chunk_size = 1024 * 2  # 1KB chunks (tune for your RAM)
                total_read = 0
                while total_read < data_size:
                    chunk = f.read(min(chunk_size, data_size - total_read))
                    if not chunk:
                        break
                    i2s.write(chunk)  # Direct byte stream (little-endian matches I2S)
                    total_read += len(chunk)

                print("Playback finished.")
            except Exception as e:
                print(f"Error: {e}")
            finally:
                i2s.deinit()  # Clean up
