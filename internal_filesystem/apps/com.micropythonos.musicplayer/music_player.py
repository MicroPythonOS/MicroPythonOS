import logging
import os
import time

import lvgl as lv

logger = logging.getLogger(__name__)

from mpos import Activity, AppManager, DisplayMetrics, Intent, sdcard, AudioManager, add_focus_border

slider_max = 16
ENDLESS_REPEAT_COUNT = 1_000_000


class MusicPlayer(Activity):
    # Widgets
    _filename_label = None
    _slider_label = None
    _slider = None
    _repeat_checkbox = None
    _stop_button = None
    _stop_button_label = None
    _open_button = None
    _settings_button = None

    # Internal state
    _filename = None
    _playback_attempted_for = None

    def onCreate(self):
        screen = lv.obj()
        # the user might have recently plugged in the sd card so try to mount it
        sdcard.mount_with_optional_format("/sdcard")

        self._filename = self.getIntent().extras.get("filename") or self.getIntent().data
        self._playback_attempted_for = None

        # Settings button (top-left)
        self._settings_button = lv.button(screen)
        self._settings_button.set_size(DisplayMetrics.pct_of_height(20), DisplayMetrics.pct_of_height(20))
        self._settings_button.align(lv.ALIGN.TOP_LEFT, 4, 4)
        self._settings_button.add_event_cb(lambda *args: AppManager.start_app("com.micropythonos.settings.audio"), lv.EVENT.CLICKED, None)
        settings_label = lv.label(self._settings_button)
        settings_label.set_text(lv.SYMBOL.SETTINGS)
        settings_label.set_style_text_font(lv.font_montserrat_24, lv.PART.MAIN)
        settings_label.center()

        # Open file button (top-right)
        self._open_button = lv.button(screen)
        self._open_button.set_size(DisplayMetrics.pct_of_width(30), DisplayMetrics.pct_of_height(20))
        self._open_button.align(lv.ALIGN.TOP_RIGHT, -4, 4)
        self._open_button.add_event_cb(self._open_file_clicked, lv.EVENT.CLICKED, None)
        open_label = lv.label(self._open_button)
        open_label.set_text("Open...")
        open_label.center()

        audio_volume = AudioManager.get_volume()
        slider_volume = int(round(audio_volume * slider_max / 100))

        self._slider_label = lv.label(screen)
        self._slider_label.set_text("Volume: {}%".format(audio_volume))
        self._slider_label.align(lv.ALIGN.TOP_MID, 0, DisplayMetrics.pct_of_height(23))
        self._slider = lv.slider(screen)
        self._slider.set_range(0, slider_max)
        self._slider.set_value(slider_volume, False)
        self._slider.set_width(lv.pct(90))
        self._slider.align_to(self._slider_label, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)

        def volume_slider_changed(e):
            slider_value = int(self._slider.get_value())
            volume_int = int(round(slider_value * 100 / slider_max))
            self._slider_label.set_text("Volume: {}%".format(volume_int))
            AudioManager.set_volume(volume_int)

        self._slider.add_event_cb(volume_slider_changed, lv.EVENT.VALUE_CHANGED, None)

        self._filename_label = lv.label(screen)
        self._filename_label.align(lv.ALIGN.CENTER, 0, 0)
        self._filename_label.set_width(lv.pct(90))
        add_focus_border(self._filename_label)
        self._filename_label.set_long_mode(lv.label.LONG_MODE.WRAP)

        self._repeat_checkbox = lv.checkbox(screen)
        self._repeat_checkbox.set_text("Repeat")
        self._repeat_checkbox.add_state(lv.STATE.CHECKED)
        self._repeat_checkbox.align_to(self._filename_label, lv.ALIGN.OUT_BOTTOM_MID, 0, DisplayMetrics.pct_of_height(10))
        self._repeat_checkbox.add_event_cb(self._repeat_checkbox_changed, lv.EVENT.VALUE_CHANGED, None)

        self._stop_button = lv.button(screen)
        self._stop_button.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self._stop_button.add_event_cb(self.stop_button_clicked, lv.EVENT.CLICKED, None)
        self._stop_button_label = lv.label(self._stop_button)
        self._stop_button_label.set_text("Stop")
        self._stop_button_label.set_style_pad_all(5, lv.PART.MAIN)

        self.setContentView(screen)

    def onResume(self, screen):
        super().onResume(screen)
        if not self._filename:
            active_track = AudioManager.get_active_track(stream_type=AudioManager.STREAM_MUSIC)
            if active_track:
                self._filename = active_track
            else:
                self._filename_label.set_text("Not playing")
                return

        self._filename_label.set_text(self._filename)

        active_player = AudioManager.get_active_player(stream_type=AudioManager.STREAM_MUSIC)
        if active_player and active_player.file_path == self._filename and active_player.is_playing():
            return

        if self._playback_attempted_for == self._filename:
            return
        self._playback_attempted_for = self._filename
        self._start_playback(self._filename)

    def _start_playback(self, filename):
        if __debug__: logger.debug("MusicPlayer: playing file %s", filename)

        AudioManager.stop()
        time.sleep(0.1)

        output = AudioManager.get_default_output()
        if output is None:
            error_msg = "Error: No audio output available"
            logger.error(error_msg)
            self.update_ui_threadsafe_if_foreground(
                self._filename_label.set_text,
                error_msg
            )
            return

        try:
            player = AudioManager.player(
                file_path=filename,
                stream_type=AudioManager.STREAM_MUSIC,
                on_complete=self.player_finished,
                output=output,
            )
            player.set_repeat(self._get_repeat_count())
            player.start()
        except Exception as exc:
            error_msg = "Error: Audio device unavailable or busy"
            logger.error("%s: %s", error_msg, exc)
            self.update_ui_threadsafe_if_foreground(
                self._filename_label.set_text,
                error_msg
            )

    def _open_file_clicked(self, event):
        intent = Intent(
            action="pick_file",
            extras={"start_dir": "/data/audio/", "path_pattern": [".wav"]},
        )
        self.startActivityForResult(intent, self._on_file_picked)

    def _on_file_picked(self, result):
        if not result or not result.get("result_code"):
            return
        paths = result.get("data", {}).get("paths", [])
        filename = self._find_first_wav(paths)
        if filename:
            self._filename = filename
            self._playback_attempted_for = None
            self._filename_label.set_text(self._filename)
            self._start_playback(self._filename)

    def _find_first_wav(self, paths):
        for path in paths:
            if path.endswith("/"):
                try:
                    items = os.listdir(path)
                    items.sort()
                    for item in items:
                        if item.lower().endswith(".wav"):
                            return path + item
                except OSError:
                    pass
            elif path.lower().endswith(".wav"):
                return path
        return None

    def _repeat_checkbox_changed(self, event):
        self._apply_repeat()

    def _get_repeat_count(self):
        if self._repeat_checkbox.get_state() & lv.STATE.CHECKED:
            return ENDLESS_REPEAT_COUNT
        return 1

    def _apply_repeat(self):
        repeat_count = self._get_repeat_count()
        player = AudioManager.get_active_player(stream_type=AudioManager.STREAM_MUSIC)
        if player and player.file_path == self._filename:
            player.set_repeat(repeat_count)

    def stop_button_clicked(self, event):
        AudioManager.stop()
        self.finish()

    def player_finished(self, result=None):
        text = "Finished playing {}".format(self._filename)
        if result:
            text = result
        if __debug__: logger.debug("AudioPlayer finished: %s", text)
        self.update_ui_threadsafe_if_foreground(self._filename_label.set_text, text)
