import lvgl as lv
from mpos.apps import Activity, Intent
from mpos.activity_navigator import ActivityNavigator

from mpos.ui.keyboard import MposKeyboard
from mpos import PackageManager
import mpos.config
import mpos.ui
import mpos.time

# Import IMU calibration activities
from check_imu_calibration import CheckIMUCalibrationActivity
from calibrate_imu import CalibrateIMUActivity

# Used to list and edit all settings:
class SettingsActivity(Activity):
    def __init__(self):
        super().__init__()
        self.prefs = None
        theme_colors = [
            ("Aqua Blue", "00ffff"),
            ("Bitcoin Orange", "f0a010"),
            ("Coral Red", "ff7f50"),
            ("Dark Slate", "2f4f4f"),
            ("Forest Green", "228b22"),
            ("Piggy Pink", "ff69b4"),
            ("Matrix Green", "03a062"),
            ("Midnight Blue", "191970"),
            ("Nostr Purple", "ff00ff"),
            ("Saddle Brown", "8b4513"),
            ("Sky Blue", "87ceeb"),
            ("Solarized Yellow", "b58900"),
            ("Vivid Violet", "9f00ff"),
            ("Amethyst", "9966cc"),
            ("Burnt Orange", "cc5500"),
            ("Charcoal Gray", "36454f"),
            ("Crimson", "dc143c"),
            ("Emerald", "50c878"),
            ("Goldenrod", "daa520"),
            ("Indigo", "4b0082"),
            ("Lime", "00ff00"),
            ("Teal", "008080"),
            ("Turquoise", "40e0d0")
        ]
        self.settings = [
            # Basic settings, alphabetically:
            {"title": "Light/Dark Theme", "key": "theme_light_dark", "value_label": None, "cont": None, "ui": "radiobuttons", "ui_options":  [("Light", "light"), ("Dark", "dark")]},
            {"title": "Theme Color", "key": "theme_primary_color", "value_label": None, "cont": None, "placeholder": "HTML hex color, like: EC048C", "ui": "dropdown", "ui_options": theme_colors},
            {"title": "Timezone", "key": "timezone", "value_label": None, "cont": None, "ui": "dropdown", "ui_options": self.get_timezone_tuples(), "changed_callback": lambda : mpos.time.refresh_timezone_preference()},
            # Advanced settings, alphabetically:
            #{"title": "Audio Output Device", "key": "audio_device", "value_label": None, "cont": None, "ui": "radiobuttons", "ui_options": [("Auto-detect", "auto"), ("I2S (Digital Audio)", "i2s"), ("Buzzer (PWM Tones)", "buzzer"), ("Both I2S and Buzzer", "both"), ("Disabled", "null")], "changed_callback": self.audio_device_changed},
            {"title": "Auto Start App", "key": "auto_start_app", "value_label": None, "cont": None, "ui": "radiobuttons", "ui_options":  [(app.name, app.fullname) for app in PackageManager.get_app_list()]},
            {"title": "Check IMU Calibration", "key": "check_imu_calibration", "value_label": None, "cont": None, "ui": "activity", "activity_class": "CheckIMUCalibrationActivity"},
            {"title": "Calibrate IMU", "key": "calibrate_imu", "value_label": None, "cont": None, "ui": "activity", "activity_class": "CalibrateIMUActivity"},
            # Expert settings, alphabetically
            {"title": "Restart to Bootloader", "key": "boot_mode", "value_label": None, "cont": None, "ui": "radiobuttons", "ui_options":  [("Normal", "normal"), ("Bootloader", "bootloader")]}, # special that doesn't get saved
            {"title": "Format internal data partition", "key": "format_internal_data_partition", "value_label": None, "cont": None, "ui": "radiobuttons", "ui_options":  [("No, do not format", "no"), ("Yes, erase all settings, files and non-builtin apps", "yes")]}, # special that doesn't get saved
            # This is currently only in the drawer but would make sense to have it here for completeness:
            #{"title": "Display Brightness", "key": "display_brightness", "value_label": None, "cont": None, "placeholder": "A value from 0 to 100."},
            # Maybe also add font size (but ideally then all fonts should scale up/down)
        ]

    def onCreate(self):
        screen = lv.obj()
        print("creating SettingsActivity ui...")
        screen.set_style_pad_all(mpos.ui.pct_of_display_width(2), 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_style_border_width(0, 0)
        self.setContentView(screen)

    def onResume(self, screen):
        # reload settings because the SettingsActivity might have changed them - could be optimized to only load if it did:
        self.prefs = mpos.config.SharedPreferences("com.micropythonos.settings")
        #wallet_type = self.prefs.get_string("wallet_type") # unused

        # Create settings entries
        screen.clean()
        # Get the group for focusable objects
        focusgroup = lv.group_get_default()
        if not focusgroup:
            print("WARNING: could not get default focusgroup")

        for setting in self.settings:
            #print(f"setting {setting.get('title')} has changed_callback {setting.get('changed_callback')}")
            # Container for each setting
            setting_cont = lv.obj(screen)
            setting_cont.set_width(lv.pct(100))
            setting_cont.set_height(lv.SIZE_CONTENT)
            setting_cont.set_style_border_width(1, 0)
            #setting_cont.set_style_border_side(lv.BORDER_SIDE.BOTTOM, 0)
            setting_cont.set_style_pad_all(mpos.ui.pct_of_display_width(2), 0)
            setting_cont.add_flag(lv.obj.FLAG.CLICKABLE)
            setting["cont"] = setting_cont  # Store container reference for visibility control

            # Title label (bold, larger)
            title = lv.label(setting_cont)
            title.set_text(setting["title"])
            title.set_style_text_font(lv.font_montserrat_16, 0)
            title.set_pos(0, 0)

            # Value label (smaller, below title)
            value = lv.label(setting_cont)
            value.set_text(self.prefs.get_string(setting["key"], "(not set)"))
            value.set_style_text_font(lv.font_montserrat_12, 0)
            value.set_style_text_color(lv.color_hex(0x666666), 0)
            value.set_pos(0, 20)
            setting["value_label"] = value  # Store reference for updating
            setting_cont.add_event_cb(lambda e, s=setting: self.startSettingActivity(s), lv.EVENT.CLICKED, None)
            setting_cont.add_event_cb(lambda e, container=setting_cont: self.focus_container(container),lv.EVENT.FOCUSED,None)
            setting_cont.add_event_cb(lambda e, container=setting_cont: self.defocus_container(container),lv.EVENT.DEFOCUSED,None)
            if focusgroup:
                focusgroup.add_obj(setting_cont)

    def startSettingActivity(self, setting):
        ui_type = setting.get("ui")

        # Handle activity-based settings (NEW)
        if ui_type == "activity":
            activity_class_name = setting.get("activity_class")
            if activity_class_name == "CheckIMUCalibrationActivity":
                intent = Intent(activity_class=CheckIMUCalibrationActivity)
                self.startActivity(intent)
            elif activity_class_name == "CalibrateIMUActivity":
                intent = Intent(activity_class=CalibrateIMUActivity)
                self.startActivity(intent)
            return

        # Handle traditional settings (existing code)
        intent = Intent(activity_class=SettingActivity)
        intent.putExtra("setting", setting)
        self.startActivity(intent)

    @staticmethod
    def get_timezone_tuples():
        return [(tz, tz) for tz in mpos.time.get_timezones()]

    def audio_device_changed(self):
        """
        Called when audio device setting changes.
        Note: Changing device type at runtime requires a restart for full effect.
        AudioFlinger initialization happens at boot.
        """
        import mpos.audio.audioflinger as AudioFlinger

        new_value = self.prefs.get_string("audio_device", "auto")
        print(f"Audio device setting changed to: {new_value}")
        print("Note: Restart required for audio device change to take effect")

        # Map setting values to device types
        device_map = {
            "auto": AudioFlinger.get_device_type(),  # Keep current
            "i2s": AudioFlinger.DEVICE_I2S,
            "buzzer": AudioFlinger.DEVICE_BUZZER,
            "both": AudioFlinger.DEVICE_BOTH,
            "null": AudioFlinger.DEVICE_NULL,
        }

        desired_device = device_map.get(new_value, AudioFlinger.get_device_type())
        current_device = AudioFlinger.get_device_type()

        if desired_device != current_device:
            print(f"Desired device type ({desired_device}) differs from current ({current_device})")
            print("Full device type change requires restart - current session continues with existing device")

    def focus_container(self, container):
        print(f"container {container} focused, setting border...")
        container.set_style_border_color(lv.theme_get_color_primary(None),lv.PART.MAIN)
        container.set_style_border_width(1, lv.PART.MAIN)
        container.scroll_to_view(True) # scroll to bring it into view

    def defocus_container(self, container):
        print(f"container {container} defocused, unsetting border...")
        container.set_style_border_width(0, lv.PART.MAIN)


# Used to edit one setting:
class SettingActivity(Activity):

    active_radio_index = -1  # Track active radio button index

    # Widgets:
    keyboard = None
    textarea = None
    dropdown = None
    radio_container = None

    def __init__(self):
        super().__init__()
        self.prefs = mpos.config.SharedPreferences("com.micropythonos.settings")
        self.setting = None

    def onCreate(self):
        setting = self.getIntent().extras.get("setting")
        #print(f"onCreate changed_callback: {setting.get('changed_callback')}")
        settings_screen_detail = lv.obj()
        settings_screen_detail.set_style_pad_all(mpos.ui.pct_of_display_width(2), 0)
        settings_screen_detail.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        top_cont = lv.obj(settings_screen_detail)
        top_cont.set_width(lv.pct(100))
        top_cont.set_style_border_width(0, 0)
        top_cont.set_height(lv.SIZE_CONTENT)
        top_cont.set_style_pad_all(mpos.ui.pct_of_display_width(1), 0)
        top_cont.set_flex_flow(lv.FLEX_FLOW.ROW)
        top_cont.set_style_flex_main_place(lv.FLEX_ALIGN.SPACE_BETWEEN, 0)
        top_cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

        setting_label = lv.label(top_cont)
        setting_label.set_text(setting["title"])
        setting_label.align(lv.ALIGN.TOP_LEFT,0,0)
        setting_label.set_style_text_font(lv.font_montserrat_20, 0)

        ui = setting.get("ui")
        ui_options = setting.get("ui_options")
        current_setting = self.prefs.get_string(setting["key"])
        if ui and ui == "radiobuttons" and ui_options:
            # Create container for radio buttons
            self.radio_container = lv.obj(settings_screen_detail)
            self.radio_container.set_width(lv.pct(100))
            self.radio_container.set_height(lv.SIZE_CONTENT)
            self.radio_container.set_flex_flow(lv.FLEX_FLOW.COLUMN)
            self.radio_container.add_event_cb(self.radio_event_handler, lv.EVENT.VALUE_CHANGED, None)
            # Create radio buttons and check the right one
            self.active_radio_index = -1 # none
            for i, (option_text, option_value) in enumerate(ui_options):
                cb = self.create_radio_button(self.radio_container, option_text, i)
                if current_setting == option_value:
                    self.active_radio_index = i
                    cb.add_state(lv.STATE.CHECKED)
        elif ui and ui == "dropdown" and ui_options:
            self.dropdown = lv.dropdown(settings_screen_detail)
            self.dropdown.set_width(lv.pct(100))
            options_with_newlines = ""
            for option in ui_options:
                if option[0] != option[1]:
                    options_with_newlines += (f"{option[0]} ({option[1]})\n")
                else: # don't show identical options
                    options_with_newlines += (f"{option[0]}\n")
            self.dropdown.set_options(options_with_newlines)
            # select the right one:
            for i, (option_text, option_value) in enumerate(ui_options):
                if current_setting == option_value:
                    self.dropdown.set_selected(i)
                    break # no need to check the rest because only one can be selected
        else:
            # Textarea for other settings
            self.textarea = lv.textarea(settings_screen_detail)
            self.textarea.set_width(lv.pct(100))
            self.textarea.set_height(lv.SIZE_CONTENT)
            self.textarea.align_to(top_cont, lv.ALIGN.OUT_BOTTOM_MID, 0, 0)
            if current_setting:
                self.textarea.set_text(current_setting)
            placeholder = setting.get("placeholder")
            if placeholder:
                self.textarea.set_placeholder_text(placeholder)
            self.textarea.add_event_cb(lambda *args: mpos.ui.anim.smooth_show(self.keyboard), lv.EVENT.CLICKED, None) # it might be focused, but keyboard hidden (because ready/cancel clicked)
            self.textarea.add_event_cb(lambda *args: mpos.ui.anim.smooth_hide(self.keyboard), lv.EVENT.DEFOCUSED, None)
            # Initialize keyboard (hidden initially)
            self.keyboard = MposKeyboard(settings_screen_detail)
            self.keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
            self.keyboard.add_flag(lv.obj.FLAG.HIDDEN)
            self.keyboard.add_event_cb(lambda *args: mpos.ui.anim.smooth_hide(self.keyboard), lv.EVENT.READY, None)
            self.keyboard.add_event_cb(lambda *args: mpos.ui.anim.smooth_hide(self.keyboard), lv.EVENT.CANCEL, None)
            self.keyboard.set_textarea(self.textarea)

        # Button container
        btn_cont = lv.obj(settings_screen_detail)
        btn_cont.set_width(lv.pct(100))
        btn_cont.set_style_border_width(0, 0)
        btn_cont.set_height(lv.SIZE_CONTENT)
        btn_cont.set_flex_flow(lv.FLEX_FLOW.ROW)
        btn_cont.set_style_flex_main_place(lv.FLEX_ALIGN.SPACE_BETWEEN, 0)
        # Save button
        save_btn = lv.button(btn_cont)
        save_btn.set_size(lv.pct(45), lv.SIZE_CONTENT)
        save_label = lv.label(save_btn)
        save_label.set_text("Save")
        save_label.center()
        save_btn.add_event_cb(lambda e, s=setting: self.save_setting(s), lv.EVENT.CLICKED, None)
        # Cancel button
        cancel_btn = lv.button(btn_cont)
        cancel_btn.set_size(lv.pct(45), lv.SIZE_CONTENT)
        cancel_label = lv.label(cancel_btn)
        cancel_label.set_text("Cancel")
        cancel_label.center()
        cancel_btn.add_event_cb(lambda e: self.finish(), lv.EVENT.CLICKED, None)

        if False: # No scan QR button for text settings because they're all short right now
            cambutton = lv.button(settings_screen_detail)
            cambutton.align(lv.ALIGN.BOTTOM_MID,0,0)
            cambutton.set_size(lv.pct(100), lv.pct(30))
            cambuttonlabel = lv.label(cambutton)
            cambuttonlabel.set_text("Scan data from QR code")
            cambuttonlabel.set_style_text_font(lv.font_montserrat_18, 0)
            cambuttonlabel.align(lv.ALIGN.TOP_MID, 0, 0)
            cambuttonlabel2 = lv.label(cambutton)
            cambuttonlabel2.set_text("Tip: Create your own QR code,\nusing https://genqrcode.com or another tool.")
            cambuttonlabel2.set_style_text_font(lv.font_montserrat_10, 0)
            cambuttonlabel2.align(lv.ALIGN.BOTTOM_MID, 0, 0)
            cambutton.add_event_cb(self.cambutton_cb, lv.EVENT.CLICKED, None)

        self.setContentView(settings_screen_detail)

    def onStop(self, screen):
        if self.keyboard:
            mpos.ui.anim.smooth_hide(self.keyboard)

    def radio_event_handler(self, event):
        print("radio_event_handler called")
        target_obj = event.get_target_obj()
        target_obj_state = target_obj.get_state()
        print(f"target_obj state {target_obj.get_text()} is {target_obj_state}")
        checked = target_obj_state & lv.STATE.CHECKED
        current_checkbox_index = target_obj.get_index()
        print(f"current_checkbox_index: {current_checkbox_index}")
        if not checked:
            if self.active_radio_index == current_checkbox_index:
                print(f"unchecking {current_checkbox_index}")
                self.active_radio_index = -1 # nothing checked
            return
        else:
            if self.active_radio_index >= 0: # is there something to uncheck?
                old_checked = self.radio_container.get_child(self.active_radio_index)
                old_checked.remove_state(lv.STATE.CHECKED)
            self.active_radio_index = current_checkbox_index

    def create_radio_button(self, parent, text, index):
        cb = lv.checkbox(parent)
        cb.set_text(text)
        cb.add_flag(lv.obj.FLAG.EVENT_BUBBLE)
        # Add circular style to indicator for radio button appearance
        style_radio = lv.style_t()
        style_radio.init()
        style_radio.set_radius(lv.RADIUS_CIRCLE)
        cb.add_style(style_radio, lv.PART.INDICATOR)
        style_radio_chk = lv.style_t()
        style_radio_chk.init()
        style_radio_chk.set_bg_image_src(None)
        cb.add_style(style_radio_chk, lv.PART.INDICATOR | lv.STATE.CHECKED)
        return cb

    def gotqr_result_callback_unused(self, result):
        print(f"QR capture finished, result: {result}")
        if result.get("result_code"):
            data = result.get("data")
            print(f"Setting textarea data: {data}")
            self.textarea.set_text(data)

    def cambutton_cb_unused(self, event):
        print("cambutton clicked!")
        self.startActivityForResult(Intent(activity_class=CameraApp).putExtra("scanqr_mode", True), self.gotqr_result_callback)

    def save_setting(self, setting):
        # Check special cases that aren't saved
        if self.radio_container and self.active_radio_index == 1:
            if setting["key"] == "boot_mode":
                from mpos.bootloader import ResetIntoBootloader
                intent = Intent(activity_class=ResetIntoBootloader)
                self.startActivity(intent)
                return
            elif setting["key"] == "format_internal_data_partition":
                # Inspired by lvgl_micropython/lib/micropython/ports/esp32/modules/inisetup.py
                # Note: it would be nice to create a "FormatInternalDataPartition" activity with some progress or confirmation
                try:
                    import vfs
                    from flashbdev import bdev
                except Exception as e:
                    print(f"Could not format internal data partition because: {e}")
                    self.finish() # would be nice to show the error instead of silently returning
                    return
                if bdev.info()[4] == "vfs":
                    print(f"Formatting {bdev} as LittleFS2")
                    vfs.VfsLfs2.mkfs(bdev)
                    fs = vfs.VfsLfs2(bdev)
                elif bdev.info()[4] == "ffat":
                    print(f"Formatting {bdev} as FAT")
                    vfs.VfsFat.mkfs(bdev)
                    fs = vfs.VfsFat(bdev)
                print(f"Mounting {fs} at /")
                vfs.mount(fs, "/")
                print("Done formatting, (re)mounting /builtin")
                try:
                    import freezefs_mount_builtin
                except Exception as e:
                    # This will throw an exception if there is already a "/builtin" folder present
                    print("settings.py: WARNING: could not import/run freezefs_mount_builtin: ", e)
                print("Done mounting, refreshing apps")
                PackageManager.refresh_apps()
                self.finish()
                return

        ui = setting.get("ui")
        ui_options = setting.get("ui_options")
        if ui and ui == "radiobuttons" and ui_options:
            selected_idx = self.active_radio_index
            new_value = ""
            if selected_idx >= 0:
                new_value = ui_options[selected_idx][1]
        elif ui and ui == "dropdown" and ui_options:
            selected_index = self.dropdown.get_selected()
            print(f"selected item: {selected_index}")
            new_value = ui_options[selected_index][1]
        elif self.textarea:
            new_value = self.textarea.get_text()
        else:
            new_value = ""
        old_value = self.prefs.get_string(setting["key"])
        editor = self.prefs.edit()
        editor.put_string(setting["key"], new_value)
        editor.commit()
        setting["value_label"].set_text(new_value if new_value else "(not set)")
        changed_callback = setting.get("changed_callback")
        #print(f"changed_callback: {changed_callback}")
        if changed_callback and old_value != new_value:
            print(f"Setting {setting['key']} changed from {old_value} to {new_value}, calling changed_callback...")
            changed_callback()
        if setting["key"] == "theme_light_dark" or setting["key"] == "theme_primary_color":
            mpos.ui.set_theme(self.prefs)
        self.finish()
