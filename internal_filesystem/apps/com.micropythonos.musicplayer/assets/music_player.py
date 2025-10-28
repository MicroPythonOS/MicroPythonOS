import machine
import os
import _thread

from mpos.apps import Activity, Intent
import mpos.sdcard
import mpos.ui

from audio_player import AudioPlayer

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
