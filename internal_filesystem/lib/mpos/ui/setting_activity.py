import logging
import lvgl as lv

from ..app.activity import Activity
from ..content.intent import Intent
from .input_activity import InputActivity

logger = logging.getLogger(__name__)

"""
SettingActivity is a thin wrapper around InputActivity.

It reads the SharedPreferences ("prefs") and setting metadata from the
launching Intent, launches the generic InputActivity for result, and
persists the returned value.  It also updates the SettingsActivity row
label and fires any configured changed_callback.
"""
class SettingActivity(Activity):

    prefs = None  # taken from the intent
    setting = None

    def onCreate(self):
        self.prefs = self.getIntent().extras.get("prefs")
        self.setting = self.getIntent().extras.get("setting")
        if not self.prefs:
            logger.error("SettingActivity missing 'prefs' in Intent extras")
            self.finish()
            return
        if not self.setting:
            logger.error("SettingActivity missing 'setting' in Intent extras")
            self.finish()
            return

        # Need a real (transparent) screen so that InputActivity can finish
        # back to a valid LVGL screen before we finish back to SettingsActivity.
        placeholder = lv.obj()
        placeholder.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        self.setContentView(placeholder)

        current_value = self.prefs.get_string(self.setting["key"], self.setting.get("default_value"))
        if current_value is None:
            current_value = ""

        intent = Intent(activity_class=InputActivity)
        intent.putExtra("setting", self.setting)
        intent.putExtra("value", current_value)
        self.startActivityForResult(intent, self.input_result_callback)

    def input_result_callback(self, result):
        if not result or not result.get("result_code"):
            # User cancelled or pressed back; just close the wrapper.
            self.finish()
            return
        new_value = result.get("data", {}).get("value")
        if new_value is None:
            self.finish()
            return

        old_value = self.prefs.get_string(self.setting["key"])

        # Persist the value unless explicitly disabled.
        if self.setting.get("dont_persist") is not True:
            editor = self.prefs.edit()
            editor.put_string(self.setting["key"], new_value)
            editor.commit()

        # Update model for UI. For settings with `ui_options`, the value_label
        # should show the human-readable label (e.g. "Lightning Piggy"), not
        # the raw stored value ("lightningpiggy"). Mirrors the list-view
        # rendering in settings_activity.py:_value_label_for so the row stays
        # consistent before and after a save.
        value_label = self.setting.get("value_label")
        if value_label:
            if not new_value:
                value_label.set_text("(not set)")
            else:
                display = new_value
                ui_options = self.setting.get("ui_options")
                if ui_options:
                    for label, value in ui_options:
                        if value == new_value:
                            display = label
                            break
                value_label.set_text(display)

        # self.finish (= back action) should happen before callback, in case it happens to start a new activity
        self.finish()

        # Call changed_callback if set
        changed_callback = self.setting.get("changed_callback")
        if changed_callback and old_value != new_value:
            if __debug__: logger.debug("Setting %s changed from %s to %s, calling changed_callback...", self.setting['key'], old_value, new_value)
            changed_callback(new_value)
