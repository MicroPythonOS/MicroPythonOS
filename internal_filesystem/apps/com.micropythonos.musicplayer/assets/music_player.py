import machine
import uos
import _thread

from mpos.apps import Activity, Intent
import mpos.sdcard
import mpos.ui

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
                    self.destination = FullscreenPlayer
                    self.startActivity(Intent(activity_class=FullscreenPlayer).putExtra("filename", fullpath))
                else:
                    print("INFO: ignoring unsupported file format")

class AudioPlayer:

    def find_data_chunk(f):
        """Skip chunks until 'data' is found. Returns (data_start_pos, data_size)."""
        # Go back to start
        f.seek(0)
        riff = f.read(4)
        if riff != b'RIFF':
            raise ValueError("Not a RIFF file")
        file_size = int.from_bytes(f.read(4), 'little') + 8  # Total file size
        wave = f.read(4)
        if wave != b'WAVE':
            raise ValueError("Not a WAVE file")
    
        pos = 12  # Start after RIFF header
        while pos < file_size:
            f.seek(pos)
            chunk_id = f.read(4)
            if len(chunk_id) < 4:
                break
            chunk_size = int.from_bytes(f.read(4), 'little')
            if chunk_id == b'fmt ':
                fmt_data = f.read(chunk_size)
                if len(fmt_data) < 16:
                    raise ValueError("Invalid fmt chunk")
                audio_format = int.from_bytes(fmt_data[0:2], 'little')
                channels = int.from_bytes(fmt_data[2:4], 'little')
                sample_rate = int.from_bytes(fmt_data[4:8], 'little')
                bits_per_sample = int.from_bytes(fmt_data[14:16], 'little')
                if audio_format != 1:
                    raise ValueError("Only PCM supported")
                if bits_per_sample != 16:
                    raise ValueError("Only 16-bit supported")
                if channels != 1:
                    raise ValueError("Only mono supported")
            elif chunk_id == b'data':
                data_start = f.tell()
                data_size = chunk_size
                return data_start, data_size, sample_rate
            # Skip chunk (pad byte if odd size)
            pos += 8 + chunk_size
            if chunk_size % 2 == 1:
                pos += 1
        raise ValueError("No 'data' chunk found")
    
    def play_wav(filename):
        """Play large WAV files robustly with chunk skipping and streaming."""
        try:
            with open(filename, 'rb') as f:
                stat = uos.stat(filename)
                file_size = stat[6]
                print(f"File size: {file_size} bytes")
    
                data_start, data_size, sample_rate = AudioPlayer.find_data_chunk(f)
                print(f"Found 'data' chunk: {data_size} bytes at {sample_rate} Hz")
    
                if data_size > file_size - data_start:
                    print("Warning: data_size exceeds file bounds. Truncating.")
                    data_size = file_size - data_start
    
                # Configure I2S
                i2s = machine.I2S(
                    0,
                    sck=machine.Pin(2, machine.Pin.OUT),
                    ws=machine.Pin(47, machine.Pin.OUT),
                    sd=machine.Pin(16, machine.Pin.OUT),
                    mode=machine.I2S.TX,
                    bits=16,
                    format=machine.I2S.MONO,
                    rate=sample_rate,
                    ibuf=32000  # Larger buffer for stability
                )
    
                print(f"Playing {data_size} bytes at {sample_rate} Hz...")
                f.seek(data_start)
    
                chunk_size = 4096  # 4KB chunks = safe for ESP32
                total_read = 0
                while total_read < data_size:
                    remaining = data_size - total_read
                    read_size = min(chunk_size, remaining)
                    chunk = f.read(read_size)
                    if not chunk:
                        break
                    i2s.write(chunk)
                    total_read += len(chunk)
    
                print("Playback finished.")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            try:
                i2s.deinit()
            except:
                pass



class FullscreenPlayer(Activity):
    # No __init__() so super.__init__() will be called automatically

    # Widgets:
    _filename_label = None
    _slider_label = None
    _slider = None
    
    # Internal state:
    _filename = None

    def onCreate(self):
        self._filename = self.getIntent().extras.get("filename")
        qr_screen = lv.obj()
        self._slider_label=lv.label(qr_screen)
        self._slider_label.set_text(f"Volume: 100%")
        self._slider_label.align(lv.ALIGN.TOP_MID,0,lv.pct(4))
        self._slider=lv.slider(qr_screen)
        self._slider.set_range(0,100)
        self._slider.set_value(100,False)
        self._slider.set_width(lv.pct(80))
        self._slider.align_to(self._slider_label,lv.ALIGN.OUT_BOTTOM_MID,0,10)
        def volume_slider_changed(e):
            volume_int = self._slider.get_value()
            self._slider_label.set_text(f"Volume: {volume_int}%")
            # TODO: set volume using AudioPlayer.set_volume(volume_int)
        self._slider.add_event_cb(volume_slider_changed,lv.EVENT.VALUE_CHANGED,None)
        self._filename_label = lv.label(qr_screen)
        self._filename_label.align(lv.ALIGN.CENTER,0,0)
        self._filename_label.set_text(self._filename)
        self._filename_label.set_width(lv.pct(90))
        self._filename_label.add_event_cb(lambda e, obj=self._filename_label: self.focus_obj(obj), lv.EVENT.FOCUSED, None)
        self._filename_label.add_event_cb(lambda e, obj=self._filename_label: self.defocus_obj(obj), lv.EVENT.DEFOCUSED, None)
        self._filename_label.set_long_mode(lv.label.LONG_MODE.SCROLL_CIRCULAR)

        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(qr_screen)
            focusgroup.add_obj(self._filename_label)
        self.setContentView(qr_screen)

    def onResume(self, screen):
        if not self._filename:
            print("Not playing any file...")
        else:
            print("Starting thread to play file {self._filename}")
            _thread.stack_size(mpos.apps.good_stack_size())
            _thread.start_new_thread(AudioPlayer.play_wav, (self._filename,))

    def focus_obj(self, obj):
        obj.set_style_border_color(lv.theme_get_color_primary(None),lv.PART.MAIN)
        obj.set_style_border_width(1, lv.PART.MAIN)

    def defocus_obj(self, obj):
        obj.set_style_border_width(0, lv.PART.MAIN)
