# Sound Recorder App - Record audio from I2S microphone to WAV files
import os
import time

from mpos.apps import Activity
import mpos.ui
import mpos.audio.audioflinger as AudioFlinger


def _makedirs(path):
    """
    Create directory and all parent directories (like os.makedirs).
    MicroPython doesn't have os.makedirs, so we implement it manually.
    """
    if not path:
        return

    parts = path.split('/')
    current = ''

    for part in parts:
        if not part:
            continue
        current = current + '/' + part if current else part
        try:
            os.mkdir(current)
        except OSError:
            pass  # Directory may already exist


class SoundRecorder(Activity):
    """
    Sound Recorder app for recording audio from I2S microphone.
    Saves recordings as WAV files that can be played with Music Player.
    """

    # Constants
    MAX_DURATION_MS = 60000  # 60 seconds max recording
    RECORDINGS_DIR = "data/com.micropythonos.soundrecorder/recordings"

    # UI Widgets
    _status_label = None
    _timer_label = None
    _record_button = None
    _record_button_label = None
    _play_button = None
    _play_button_label = None
    _delete_button = None
    _last_file_label = None

    # State
    _is_recording = False
    _last_recording = None
    _timer_task = None
    _record_start_time = 0

    def onCreate(self):
        screen = lv.obj()

        # Title
        title = lv.label(screen)
        title.set_text("Sound Recorder")
        title.align(lv.ALIGN.TOP_MID, 0, 10)
        title.set_style_text_font(lv.font_montserrat_20, 0)

        # Status label (shows microphone availability)
        self._status_label = lv.label(screen)
        self._status_label.align(lv.ALIGN.TOP_MID, 0, 40)

        # Timer display
        self._timer_label = lv.label(screen)
        self._timer_label.set_text("00:00 / 01:00")
        self._timer_label.align(lv.ALIGN.CENTER, 0, -30)
        self._timer_label.set_style_text_font(lv.font_montserrat_24, 0)

        # Record button
        self._record_button = lv.button(screen)
        self._record_button.set_size(120, 50)
        self._record_button.align(lv.ALIGN.CENTER, 0, 30)
        self._record_button.add_event_cb(self._on_record_clicked, lv.EVENT.CLICKED, None)

        self._record_button_label = lv.label(self._record_button)
        self._record_button_label.set_text(lv.SYMBOL.AUDIO + " Record")
        self._record_button_label.center()

        # Last recording info
        self._last_file_label = lv.label(screen)
        self._last_file_label.align(lv.ALIGN.BOTTOM_MID, 0, -70)
        self._last_file_label.set_text("No recordings yet")
        self._last_file_label.set_long_mode(lv.label.LONG_MODE.SCROLL_CIRCULAR)
        self._last_file_label.set_width(lv.pct(90))

        # Play button
        self._play_button = lv.button(screen)
        self._play_button.set_size(80, 40)
        self._play_button.align(lv.ALIGN.BOTTOM_LEFT, 20, -20)
        self._play_button.add_event_cb(self._on_play_clicked, lv.EVENT.CLICKED, None)
        self._play_button.add_flag(lv.obj.FLAG.HIDDEN)

        self._play_button_label = lv.label(self._play_button)
        self._play_button_label.set_text(lv.SYMBOL.PLAY + " Play")
        self._play_button_label.center()

        # Delete button
        self._delete_button = lv.button(screen)
        self._delete_button.set_size(80, 40)
        self._delete_button.align(lv.ALIGN.BOTTOM_RIGHT, -20, -20)
        self._delete_button.add_event_cb(self._on_delete_clicked, lv.EVENT.CLICKED, None)
        self._delete_button.add_flag(lv.obj.FLAG.HIDDEN)

        delete_label = lv.label(self._delete_button)
        delete_label.set_text(lv.SYMBOL.TRASH + " Delete")
        delete_label.center()

        # Add to focus group
        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(self._record_button)
            focusgroup.add_obj(self._play_button)
            focusgroup.add_obj(self._delete_button)

        self.setContentView(screen)

    def onResume(self, screen):
        super().onResume(screen)
        self._update_status()
        self._find_last_recording()

    def onPause(self, screen):
        super().onPause(screen)
        # Stop recording if app goes to background
        if self._is_recording:
            self._stop_recording()

    def _update_status(self):
        """Update status label based on microphone availability."""
        if AudioFlinger.has_microphone():
            self._status_label.set_text("Microphone ready")
            self._status_label.set_style_text_color(lv.color_hex(0x00AA00), 0)
            self._record_button.remove_flag(lv.obj.FLAG.HIDDEN)
        else:
            self._status_label.set_text("No microphone available")
            self._status_label.set_style_text_color(lv.color_hex(0xAA0000), 0)
            self._record_button.add_flag(lv.obj.FLAG.HIDDEN)

    def _find_last_recording(self):
        """Find the most recent recording file."""
        try:
            # Ensure recordings directory exists
            _makedirs(self.RECORDINGS_DIR)

            # List recordings
            files = os.listdir(self.RECORDINGS_DIR)
            wav_files = [f for f in files if f.endswith('.wav')]

            if wav_files:
                # Sort by name (which includes timestamp)
                wav_files.sort(reverse=True)
                self._last_recording = f"{self.RECORDINGS_DIR}/{wav_files[0]}"
                self._last_file_label.set_text(f"Last: {wav_files[0]}")
                self._play_button.remove_flag(lv.obj.FLAG.HIDDEN)
                self._delete_button.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                self._last_recording = None
                self._last_file_label.set_text("No recordings yet")
                self._play_button.add_flag(lv.obj.FLAG.HIDDEN)
                self._delete_button.add_flag(lv.obj.FLAG.HIDDEN)

        except Exception as e:
            print(f"SoundRecorder: Error finding recordings: {e}")
            self._last_recording = None

    def _generate_filename(self):
        """Generate a timestamped filename for the recording."""
        # Get current time
        t = time.localtime()
        timestamp = f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}_{t[3]:02d}-{t[4]:02d}-{t[5]:02d}"
        return f"{self.RECORDINGS_DIR}/{timestamp}.wav"

    def _on_record_clicked(self, event):
        """Handle record button click."""
        print(f"SoundRecorder: _on_record_clicked called, _is_recording={self._is_recording}")
        if self._is_recording:
            print("SoundRecorder: Stopping recording...")
            self._stop_recording()
        else:
            print("SoundRecorder: Starting recording...")
            self._start_recording()

    def _start_recording(self):
        """Start recording audio."""
        print("SoundRecorder: _start_recording called")
        print(f"SoundRecorder: has_microphone() = {AudioFlinger.has_microphone()}")

        if not AudioFlinger.has_microphone():
            print("SoundRecorder: No microphone available - aborting")
            return

        # Generate filename
        file_path = self._generate_filename()
        print(f"SoundRecorder: Generated filename: {file_path}")

        # Start recording
        print(f"SoundRecorder: Calling AudioFlinger.record_wav()")
        print(f"  file_path: {file_path}")
        print(f"  duration_ms: {self.MAX_DURATION_MS}")
        print(f"  sample_rate: 16000")

        success = AudioFlinger.record_wav(
            file_path=file_path,
            duration_ms=self.MAX_DURATION_MS,
            on_complete=self._on_recording_complete,
            sample_rate=16000
        )

        print(f"SoundRecorder: record_wav returned: {success}")

        if success:
            self._is_recording = True
            self._record_start_time = time.ticks_ms()
            self._last_recording = file_path
            print(f"SoundRecorder: Recording started successfully")

            # Update UI
            self._record_button_label.set_text(lv.SYMBOL.STOP + " Stop")
            self._record_button.set_style_bg_color(lv.color_hex(0xAA0000), 0)
            self._status_label.set_text("Recording...")
            self._status_label.set_style_text_color(lv.color_hex(0xAA0000), 0)

            # Hide play/delete buttons during recording
            self._play_button.add_flag(lv.obj.FLAG.HIDDEN)
            self._delete_button.add_flag(lv.obj.FLAG.HIDDEN)

            # Start timer update
            self._start_timer_update()
        else:
            print("SoundRecorder: record_wav failed!")
            self._status_label.set_text("Failed to start recording")
            self._status_label.set_style_text_color(lv.color_hex(0xAA0000), 0)

    def _stop_recording(self):
        """Stop recording audio."""
        AudioFlinger.stop()
        self._is_recording = False

        # Update UI
        self._record_button_label.set_text(lv.SYMBOL.AUDIO + " Record")
        self._record_button.set_style_bg_color(lv.theme_get_color_primary(None), 0)
        self._update_status()

        # Stop timer update
        self._stop_timer_update()

    def _on_recording_complete(self, message):
        """Callback when recording finishes."""
        print(f"SoundRecorder: {message}")

        # Update UI on main thread
        self.update_ui_threadsafe_if_foreground(self._recording_finished, message)

    def _recording_finished(self, message):
        """Update UI after recording finishes (called on main thread)."""
        self._is_recording = False

        # Update UI
        self._record_button_label.set_text(lv.SYMBOL.AUDIO + " Record")
        self._record_button.set_style_bg_color(lv.theme_get_color_primary(None), 0)
        self._update_status()
        self._find_last_recording()

        # Stop timer update
        self._stop_timer_update()

    def _start_timer_update(self):
        """Start updating the timer display."""
        # Use LVGL timer for periodic updates
        self._timer_task = lv.timer_create(self._update_timer, 100, None)

    def _stop_timer_update(self):
        """Stop updating the timer display."""
        if self._timer_task:
            self._timer_task.delete()
            self._timer_task = None
        self._timer_label.set_text("00:00 / 01:00")

    def _update_timer(self, timer):
        """Update timer display (called periodically)."""
        if not self._is_recording:
            return

        elapsed_ms = time.ticks_diff(time.ticks_ms(), self._record_start_time)
        elapsed_sec = elapsed_ms // 1000
        max_sec = self.MAX_DURATION_MS // 1000

        elapsed_min = elapsed_sec // 60
        elapsed_sec = elapsed_sec % 60
        max_min = max_sec // 60
        max_sec_display = max_sec % 60

        self._timer_label.set_text(
            f"{elapsed_min:02d}:{elapsed_sec:02d} / {max_min:02d}:{max_sec_display:02d}"
        )

    def _on_play_clicked(self, event):
        """Handle play button click."""
        if self._last_recording and not self._is_recording:
            # Stop any current playback
            AudioFlinger.stop()
            time.sleep_ms(100)

            # Play the recording
            success = AudioFlinger.play_wav(
                self._last_recording,
                stream_type=AudioFlinger.STREAM_MUSIC,
                on_complete=self._on_playback_complete
            )

            if success:
                self._status_label.set_text("Playing...")
                self._status_label.set_style_text_color(lv.color_hex(0x0000AA), 0)
            else:
                self._status_label.set_text("Playback failed")
                self._status_label.set_style_text_color(lv.color_hex(0xAA0000), 0)

    def _on_playback_complete(self, message):
        """Callback when playback finishes."""
        self.update_ui_threadsafe_if_foreground(self._update_status)

    def _on_delete_clicked(self, event):
        """Handle delete button click."""
        if self._last_recording and not self._is_recording:
            try:
                os.remove(self._last_recording)
                print(f"SoundRecorder: Deleted {self._last_recording}")
                self._find_last_recording()
                self._status_label.set_text("Recording deleted")
            except Exception as e:
                print(f"SoundRecorder: Delete failed: {e}")
                self._status_label.set_text("Delete failed")
                self._status_label.set_style_text_color(lv.color_hex(0xAA0000), 0)