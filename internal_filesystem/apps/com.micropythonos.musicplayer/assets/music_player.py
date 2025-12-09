import machine
import os
import time

from mpos.apps import Activity, Intent
import mpos.sdcard
import mpos.ui
import mpos.audio.audioflinger as AudioFlinger

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
        import os
        local_filesystem_dir = os.getcwd().rstrip('/') # if it's / then it has a slash, if it's a subfolder then it doesn't
        self.file_explorer.explorer_set_quick_access_path(lv.EXPLORER.FS_DIR, f"M:{local_filesystem_dir}")
        self.file_explorer.explorer_set_quick_access_path(lv.EXPLORER.HOME_DIR, f"M:{local_filesystem_dir}/sdcard")
        self.file_explorer.explorer_set_quick_access_path(lv.EXPLORER.MUSIC_DIR, f"M:{local_filesystem_dir}/sdcard/music")
        #self.file_explorer.explorer_set_sort(lv.EXPLORER_SORT.KIND)
        self.setContentView(screen)

    def onResume(self, screen):
        # the user might have recently plugged in the sd card so try to mount it
        mpos.sdcard.mount_with_optional_format('/sdcard') # would be good to refresh the file_explorer so the /sdcard folder shows up

    def file_explorer_event_cb(self, event):
        event_code = event.get_code()
        if event_code not in [2,19,23,24,25,26,27,28,29,30,31,32,33,47,49,52]:
            name = mpos.ui.get_event_name(event_code)
            #print(f"file_explorer_event_cb {event_code} with name {name}")
            if event_code == lv.EVENT.VALUE_CHANGED:
                path = self.file_explorer.explorer_get_current_path()
                clean_path = path[2:] if path[1] == ':' else path
                file = self.file_explorer.explorer_get_selected_file_name()
                fullpath = f"{clean_path}{file}"
                print(f"Selected: {fullpath}")
                #if fullpath.lower().endswith('.wav'):
                self.destination = FullscreenPlayer
                self.startActivity(Intent(activity_class=FullscreenPlayer).putExtra("filename", fullpath))
                #else:
                #    print("INFO: ignoring unsupported file format")

class FullscreenPlayer(Activity):
    # No __init__() so super.__init__() will be called automatically

    # Widgets:
    _filename_label = None
    _slider_label = None
    _slider = None
    _stop_button = None
    _stop_button_label = None
    
    # Internal state:
    _filename = None

    def onCreate(self):
        self._filename = self.getIntent().extras.get("filename")
        qr_screen = lv.obj()
        self._slider_label=lv.label(qr_screen)
        self._slider_label.set_text(f"Volume: {AudioFlinger.get_volume()}%")
        self._slider_label.align(lv.ALIGN.TOP_MID,0,lv.pct(4))
        self._slider=lv.slider(qr_screen)
        self._slider.set_range(0,16)
        self._slider.set_value(int(AudioFlinger.get_volume()/6.25), False)
        self._slider.set_width(lv.pct(90))
        self._slider.align_to(self._slider_label,lv.ALIGN.OUT_BOTTOM_MID,0,10)
        def volume_slider_changed(e):
            volume_int = self._slider.get_value()*6.25
            self._slider_label.set_text(f"Volume: {volume_int}%")
            AudioFlinger.set_volume(volume_int)
        self._slider.add_event_cb(volume_slider_changed,lv.EVENT.VALUE_CHANGED,None)
        self._filename_label = lv.label(qr_screen)
        self._filename_label.align(lv.ALIGN.CENTER,0,0)
        self._filename_label.set_text(self._filename)
        self._filename_label.set_width(lv.pct(90))
        self._filename_label.add_event_cb(lambda e, obj=self._filename_label: self.focus_obj(obj), lv.EVENT.FOCUSED, None)
        self._filename_label.add_event_cb(lambda e, obj=self._filename_label: self.defocus_obj(obj), lv.EVENT.DEFOCUSED, None)
        self._filename_label.set_long_mode(lv.label.LONG_MODE.SCROLL_CIRCULAR)
        self._stop_button = lv.button(qr_screen)
        self._stop_button.align(lv.ALIGN.BOTTOM_MID,0,0)
        self._stop_button.add_event_cb(self.stop_button_clicked,lv.EVENT.CLICKED,None)
        self._stop_button_label = lv.label(self._stop_button)
        self._stop_button_label.set_text("Stop")

        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(qr_screen)
            focusgroup.add_obj(self._filename_label)
        self.setContentView(qr_screen)

    def onResume(self, screen):
        super().onResume(screen)
        if not self._filename:
            print("Not playing any file...")
        else:
            print(f"Playing file {self._filename}")
            AudioFlinger.stop()
            time.sleep(0.1)

            success = AudioFlinger.play_wav(
                self._filename,
                stream_type=AudioFlinger.STREAM_MUSIC,
                on_complete=self.player_finished
            )

            if not success:
                error_msg = "Error: Audio device unavailable or busy"
                print(error_msg)
                self.update_ui_threadsafe_if_foreground(
                    self._filename_label.set_text,
                    error_msg
                )

    def focus_obj(self, obj):
        obj.set_style_border_color(lv.theme_get_color_primary(None),lv.PART.MAIN)
        obj.set_style_border_width(1, lv.PART.MAIN)

    def defocus_obj(self, obj):
        obj.set_style_border_width(0, lv.PART.MAIN)

    def stop_button_clicked(self, event):
        AudioFlinger.stop()
        self.finish()

    def player_finished(self, result=None):
        text = f"Finished playing {self._filename}"
        if result:
            text = result
        print(f"AudioPlayer finished: {text}")
        self.update_ui_threadsafe_if_foreground(self._filename_label.set_text, text)
