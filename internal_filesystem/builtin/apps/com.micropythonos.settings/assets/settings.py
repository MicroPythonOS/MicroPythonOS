import lvgl as lv

from mpos import Activity, Intent, AppearanceManager, AppManager, NumberFormat, SettingActivity, SettingsActivity, TimeZone

from bootloader import ResetIntoBootloader
from calibrate_imu import CalibrateIMUActivity
from check_imu_calibration import CheckIMUCalibrationActivity

class LaunchWiFi(Activity):

    def onCreate(self):
        AppManager.start_app("com.micropythonos.settings.wifi")


class LaunchHotspot(Activity):

    def onCreate(self):
        AppManager.start_app("com.micropythonos.settings.hotspot")


class LaunchWebServer(Activity):

    def onCreate(self):
        AppManager.start_app("com.micropythonos.settings.webserver")


class LaunchAudioSettings(Activity):

    def onCreate(self):
        AppManager.start_app("com.micropythonos.settings.audio")


class Settings(SettingsActivity):

    """Override getIntent to provide prefs and settings via Intent extras"""
    def getIntent(self):
        theme_colors = [
            ("Amethyst", "9966cc"),
            ("Aqua Blue", "00ffff"),
            ("Bitcoin Orange", "f0a010"),
            ("Burnt Orange", "cc5500"),
            ("Charcoal Gray", "36454f"),
            ("Coral Red", "ff7f50"),
            ("Crimson", "dc143c"),
            ("Dark Slate", "2f4f4f"),
            ("Emerald", "50c878"),
            ("Forest Green", "228b22"),
            ("Goldenrod", "daa520"),
            ("Indigo", "4b0082"),
            ("Lime", "00ff00"),
            ("Matrix Green", "03a062"),
            ("Midnight Blue", "191970"),
            ("Nostr Purple", "ff00ff"),
            ("Piggy Pink", "ff69b4"),
            ("Saddle Brown", "8b4513"),
            ("Sky Blue", "87ceeb"),
            ("Solarized Yellow", "b58900"),
            ("Teal", "008080"),
            ("Turquoise", "40e0d0"),
            ("Vivid Violet", "9f00ff")
        ]
        intent = Intent()
        from mpos import SharedPreferences
        intent.putExtra("prefs", SharedPreferences(self.appFullName))
        intent.putExtra("settings", [
            {
                "title": "Wi-Fi",
                "key": "wifi_settings",
                "ui": "activity",
                "activity_class": LaunchWiFi,
                "placeholder": "Scan and connect to Wi-Fi",
            },
            {
                "title": "Hotspot",
                "key": "hotspot_settings",
                "ui": "activity",
                "activity_class": LaunchHotspot,
                "placeholder": "Standalone Wi-Fi access point",
            },
            {
                "title": "WebServer",
                "key": "webserver_settings",
                "ui": "activity",
                "activity_class": LaunchWebServer,
                "placeholder": "WebREPL, password, port etc",
            },
            {
                "title": "Audio",
                "key": "audio_settings",
                "ui": "activity",
                "activity_class": LaunchAudioSettings,
                "placeholder": "Input/output devices",
            },
            # Basic settings, alphabetically:
            {"title": "Light/Dark Theme", "key": "theme_light_dark", "ui": "radiobuttons", "ui_options":  [("Light", "light"), ("Dark", "dark")], "changed_callback": self.theme_changed},
            {"title": "Theme Color", "key": "theme_primary_color", "placeholder": "HTML hex color, like: EC048C", "ui": "dropdown", "ui_options": theme_colors, "changed_callback": self.theme_changed, "default_value": AppearanceManager.DEFAULT_PRIMARY_COLOR},
            {"title": "Timezone", "key": "timezone", "ui": "dropdown", "ui_options": [(tz, tz) for tz in TimeZone.get_timezones()], "changed_callback": lambda *args: TimeZone.refresh_timezone_preference()},
            {"title": "Number Format", "key": "number_format", "ui": "dropdown", "ui_options": NumberFormat.get_format_options(), "changed_callback": lambda *args: NumberFormat.refresh_preference(), "default_value": "comma_dot"},
            # Advanced settings, alphabetically:
            {"title": "Auto Start App", "key": "auto_start_app", "ui": "radiobuttons", "ui_options":  [(app.name, app.fullname) for app in AppManager.get_app_list()]},
            {"title": "Check IMU Calibration", "key": "check_imu_calibration", "ui": "activity", "activity_class": CheckIMUCalibrationActivity},
            {"title": "Calibrate IMU", "key": "calibrate_imu", "ui": "activity", "activity_class": CalibrateIMUActivity},
            # Expert settings, alphabetically
            {"title": "Restart to Bootloader", "key": "boot_mode", "dont_persist": True, "ui": "radiobuttons", "ui_options":  [("Normal", "normal"), ("Bootloader", "bootloader")], "changed_callback": self.reset_into_bootloader},
            {"title": "Format internal data partition", "key": "format_internal_data_partition", "dont_persist": True, "ui": "radiobuttons", "ui_options":  [("No, do not format", "no"), ("Yes, erase all settings, files and non-builtin apps", "yes")], "changed_callback": self.format_internal_data_partition},
            # This is currently only in the drawer but would make sense to have it here for completeness:
            #{"title": "Display Brightness", "key": "display_brightness", "placeholder": "A value from 0 to 100."},
            # Maybe also add font size (but ideally then all fonts should scale up/down)
            ])
        return intent

    # Change handlers:
    def reset_into_bootloader(self, new_value):
        if new_value is not "bootloader":
            return
        intent = Intent(activity_class=ResetIntoBootloader)
        self.startActivity(intent)

    def format_internal_data_partition(self, new_value):
        if new_value is not "yes":
            return # user picked "no" - abort
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
        AppManager.refresh_apps()

    def theme_changed(self, new_value):
        from mpos import AppearanceManager
        AppearanceManager.init(self.prefs)
