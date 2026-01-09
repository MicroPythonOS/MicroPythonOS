import lvgl as lv
from mpos.apps import Activity, Intent
from mpos.activity_navigator import ActivityNavigator

from mpos.ui.keyboard import MposKeyboard
from mpos import PackageManager
import mpos.config
import mpos.ui
import mpos.time

from setting_activity import SettingActivity
from calibrate_imu import CalibrateIMUActivity
from check_imu_calibration import CheckIMUCalibrationActivity

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
            {"title": "Light/Dark Theme", "key": "theme_light_dark", "value_label": None, "cont": None, "ui": "radiobuttons", "ui_options":  [("Light", "light"), ("Dark", "dark")], "changed_callback": self.theme_changed},
            {"title": "Theme Color", "key": "theme_primary_color", "value_label": None, "cont": None, "placeholder": "HTML hex color, like: EC048C", "ui": "dropdown", "ui_options": theme_colors, "changed_callback": self.theme_changed},
            {"title": "Timezone", "key": "timezone", "value_label": None, "cont": None, "ui": "dropdown", "ui_options": self.get_timezone_tuples(), "changed_callback": lambda *args: mpos.time.refresh_timezone_preference()},
            # Advanced settings, alphabetically:
            #{"title": "Audio Output Device", "key": "audio_device", "value_label": None, "cont": None, "ui": "radiobuttons", "ui_options": [("Auto-detect", "auto"), ("I2S (Digital Audio)", "i2s"), ("Buzzer (PWM Tones)", "buzzer"), ("Both I2S and Buzzer", "both"), ("Disabled", "null")], "changed_callback": self.audio_device_changed},
            {"title": "Auto Start App", "key": "auto_start_app", "value_label": None, "cont": None, "ui": "radiobuttons", "ui_options":  [(app.name, app.fullname) for app in PackageManager.get_app_list()]},
            {"title": "Check IMU Calibration", "key": "check_imu_calibration", "value_label": None, "cont": None, "ui": "activity", "activity_class": CheckIMUCalibrationActivity},
            {"title": "Calibrate IMU", "key": "calibrate_imu", "value_label": None, "cont": None, "ui": "activity", "activity_class": CalibrateIMUActivity},
            # Expert settings, alphabetically
            {"title": "Restart to Bootloader", "key": "boot_mode", "dont_persist": True, "value_label": None, "cont": None, "ui": "radiobuttons", "ui_options":  [("Normal", "normal"), ("Bootloader", "bootloader")], "changed_callback": self.reset_into_bootloader},
            {"title": "Format internal data partition", "key": "format_internal_data_partition", "dont_persist": True, "value_label": None, "cont": None, "ui": "radiobuttons", "ui_options":  [("No, do not format", "no"), ("Yes, erase all settings, files and non-builtin apps", "yes")], "changed_callback": self.format_internal_data_partition},
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

        activity_class = SettingActivity
        if ui_type == "activity":
            activity_class = setting.get("activity_class")
            if not activity_class:
                print("ERROR: Setting is defined as 'activity' ui without 'activity_class', aborting...")

        intent = Intent(activity_class=activity_class)
        intent.putExtra("setting", setting)
        intent.putExtra("prefs", self.prefs)
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

    def reset_into_bootloader(self, new_value):
        if new_value is not "bootloader":
            return
        from mpos.bootloader import ResetIntoBootloader
        intent = Intent(activity_class=ResetIntoBootloader)
        self.startActivity(intent)

    def format_internal_data_partition(self, new_value):
        if new_value is not "yes":
            return
        # Inspired by lvgl_micropython/lib/micropython/ports/esp32/modules/inisetup.py
        # Note: it would be nice to create a "FormatInternalDataPartition" activity with some progress or confirmation
        try:
            import vfs
            from flashbdev import bdev
        except Exception as e:
            print(f"Could not format internal data partition because: {e}")
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

    def theme_changed(self, new_value):
        mpos.ui.set_theme(self.prefs)
