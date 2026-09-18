import logging
import lvgl as lv

from ..app.activity import Activity
from .setting_activity import SettingActivity
import mpos.ui

logger = logging.getLogger(__name__)


def _value_label_for(setting, stored_value):
    """Map a stored pref value to its human-readable display label using
    the setting's `ui_options` list (a list of (label, value) tuples).
    Returns the matching label if one is found, otherwise the raw value
    unchanged.

    Without this, settings with `ui_options` (radiobuttons, dropdown)
    show the raw pref value in the row's value label — e.g.
    "lightningpiggy" instead of "Lightning Piggy". The matching label
    only exists in the picker activity itself, never on the list view.
    """
    ui_options = setting.get("ui_options")
    if ui_options:
        for label, value in ui_options:
            if value == stored_value:
                return label
    return stored_value


def _row_value_text(setting, stored_value):
    """Label text for a setting row in the SettingsActivity list.

    Pure function of the setting dict plus the stored pref value (None
    when unset) so the row-rendering rule is unit-testable. A
    `dont_persist` entry with a `default_value` (e.g. live state re-read
    on every open, like USB Host Mode) shows "(defaults to X)" instead
    of "(not persisted)"; `dont_persist` without one keeps the old text.
    """
    if setting.get("activity_class"):
        return setting.get("placeholder") or ""
    if setting.get("dont_persist"):
        default_value = setting.get("default_value")
        if default_value is not None:
            return f"(defaults to {_value_label_for(setting, default_value)})"
        return "(not persisted)"
    if stored_value is None:
        default_value = setting.get("default_value")
        if default_value is not None:
            # Map default to its human-readable label too, when one exists.
            return f"(defaults to {_value_label_for(setting, default_value)})"
        return "(not set)"
    # Map stored value to its ui_options label when present
    # (e.g. "lightningpiggy" → "Lightning Piggy"). No-op when
    # no ui_options or the value isn't in the list. Prefs are JSON, so a
    # value stored as int/float (an older app version, or a numeric
    # ui_options value) must still become label text.
    return str(_value_label_for(setting, stored_value))


# Used to list and edit all settings:
class SettingsActivity(Activity):

    # Taken from the Intent (initialized in onCreate)
    prefs = None
    settings = ()

    def onCreate(self):
        extras = self.getIntent().extras or {}
        self.prefs = extras.get("prefs")
        self.settings = extras.get("settings") or ()
        if not self.prefs:
            logger.error("SettingsActivity missing 'prefs' in Intent extras")
        if not self.settings:
            logger.warning("SettingsActivity has no settings to display")

        if __debug__: logger.debug("creating SettingsActivity ui...")
        screen = lv.obj()
        screen.set_style_pad_all(mpos.ui.DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_style_border_width(0, lv.PART.MAIN)
        self.setContentView(screen)

    def onResume(self, screen):
        # Create settings entries
        screen.clean()
        if not self.prefs:
            logger.error("SettingsActivity cannot render without prefs")
            return

        for setting in self.settings:
            if "should_show" in setting:
                should_show = setting["should_show"]
                if callable(should_show):
                    should_show = should_show(setting)
                if not should_show:
                    continue
            # Container for each setting
            setting_cont = lv.obj(screen)
            setting_cont.set_width(lv.pct(100))
            setting_cont.set_height(lv.SIZE_CONTENT)
            setting_cont.set_style_border_width(1, lv.PART.MAIN)
            setting_cont.set_style_pad_all(mpos.ui.DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
            setting_cont.add_flag(lv.obj.FLAG.CLICKABLE)
            setting["cont"] = setting_cont  # Store container reference for visibility control

            # Title label (bold, larger)
            title = lv.label(setting_cont)
            title.set_text(setting["title"])
            title.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
            title.set_pos(0, 0)

            # Value label (smaller, below title)
            value = lv.label(setting_cont)
            if setting.get("activity_class"):
                value_text = setting.get("placeholder") or ""
            else:
                stored_value = self.prefs.get_string(setting["key"])
                value_text = _row_value_text(setting, stored_value)
            value.set_text(value_text)
            value.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
            value.set_style_text_color(lv.color_hex(0x666666), lv.PART.MAIN)
            value.set_pos(0, 20)
            setting["value_label"] = value  # Store reference for updating
            setting_cont.add_event_cb(lambda e, s=setting: self.startSettingActivity(s), lv.EVENT.CLICKED, None)
            mpos.ui.add_focus_border(setting_cont)

    def startSettingActivity(self, setting):
        from ..content.intent import Intent
        activity_class = SettingActivity
        if setting.get("ui") == "activity":
            activity_class = setting.get("activity_class")
            if not activity_class:
                logger.error("Setting is defined as 'activity' ui without 'activity_class', aborting...")

        intent = Intent(activity_class=activity_class)
        intent.putExtra("setting", setting)
        intent.putExtra("prefs", self.prefs)
        self.startActivity(intent)
