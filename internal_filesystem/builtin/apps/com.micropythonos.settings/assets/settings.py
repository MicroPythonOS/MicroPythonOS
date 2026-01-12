import lvgl as lv

from mpos.apps import Intent
from mpos import PackageManager, SettingActivity, SettingsActivity

from calibrate_imu import CalibrateIMUActivity
from check_imu_calibration import CheckIMUCalibrationActivity

class Settings(SettingsActivity):

    """Override getIntent to provide prefs and settings via Intent extras"""
    def getIntent(self):
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
        intent = Intent()
        import mpos.config
        intent.putExtra("prefs", mpos.config.SharedPreferences("com.micropythonos.settings"))
        import mpos.time
        intent.putExtra("settings", [
            # Basic settings, alphabetically:
            {"title": "Light/Dark Theme", "key": "theme_light_dark", "ui": "radiobuttons", "ui_options":  [("Light", "light"), ("Dark", "dark")], "changed_callback": self.theme_changed},
            {"title": "Theme Color", "key": "theme_primary_color", "placeholder": "HTML hex color, like: EC048C", "ui": "dropdown", "ui_options": theme_colors, "changed_callback": self.theme_changed},
            {"title": "Timezone", "key": "timezone", "ui": "dropdown", "ui_options": [(tz, tz) for tz in mpos.time.get_timezones()], "changed_callback": lambda *args: mpos.time.refresh_timezone_preference()},
            # Advanced settings, alphabetically:
            {"title": "Auto Start App", "key": "auto_start_app", "ui": "radiobuttons", "ui_options":  [(app.name, app.fullname) for app in PackageManager.get_app_list()]},
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
        import mpos.ui
        mpos.ui.set_theme(self.prefs)
