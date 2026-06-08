import logging
import lvgl as lv
from .activity import Activity
from .appearance_manager import AppearanceManager
from .display_metrics import DisplayMetrics

logger = logging.getLogger(__name__)

SETTINGS = {
    "settings_contrast": {"type": "options", "label": "Contrast", "values": {"-2": -2, "-1": -1, "0": 0, "1": 1, "2": 2}, "value": 0},
    "settings_brightness": {"type": "options", "label": "Brightness", "values": {"-2": -2, "-1": -1, "0": 0, "1": 1, "2": 2}, "value": 0},
    "settings_saturation": {"type": "options", "label": "Saturation", "values": {"-2": -2, "-1": -1, "0": 0, "1": 1, "2": 2}, "value": 0},
    "settings_quality": {"type": "options", "label": "Quality", "values": {"10": 10, "12": 12, "14": 14, "16": 16, "18": 18, "20": 20, "22": 22, "24": 24, "26": 26, "28": 28, "30": 30, "32": 32, "34": 34, "36": 36, "38": 38, "40": 40, "42": 42, "44": 44, "46": 46, "48": 48, "50": 50, "52": 52, "54": 54, "56": 56, "58": 58, "60": 60, "62": 62, "63": 63}, "value": 10},
    "settings_resolution": {"type": "options", "label": "Resolution", "values": {"64x64": 0, "QVGA": 1, "CIF": 2, "VGA": 4, "SVGA": 5, "XGA": 6, "SXGA": 7, "UXGA": 8}, "value": 4},
    "settings_pixformat": {"type": "options", "label": "Pixel Format", "values": {"RGB565": 1, "YUV422": 2, "GRAYSCALE": 4, "JPEG": 5}, "value": 1},
    "settings_gainceiling": {"type": "options", "label": "Gain Ceiling", "values": {"2x": 0, "4x": 1, "8x": 2, "16x": 3, "32x": 4, "64x": 5, "128x": 6}, "value": 0},
    "settings_agc_gain": {"type": "options", "label": "AGC Gain", "values": {"0x": 0, "2x": 1, "4x": 2, "8x": 3, "16x": 4, "32x": 5, "64x": 6, "128x": 7}, "value": 0},
    "settings_dcw": {"type": "options", "label": "DCW", "values": {"Enable": 1, "Disable": 0}, "value": 1},
    "settings_raw_gma": {"type": "options", "label": "Raw GMA", "values": {"Enable": 1, "Disable": 0}, "value": 1},
    "settings_bpc": {"type": "options", "label": "BPC", "values": {"Enable": 1, "Disable": 0}, "value": 1},
    "settings_wpc": {"type": "options", "label": "WPC", "values": {"Enable": 1, "Disable": 0}, "value": 1},
    "settings_aec_sensor": {"type": "options", "label": "AEC Sensor", "values": {"Enable": 1, "Disable": 0}, "value": 1},
    "settings_aec_dsp": {"type": "options", "label": "AEC DSP", "values": {"Enable": 1, "Disable": 0}, "value": 1},
    "settings_led_intensity": {
        "type": "options",
        "label": "LED Intensity",
        "values": {"0": 0, "1": 1, "2": 2, "3": 3},
        "value": 0,
    },
    "settings_hmirror": {"type": "bool", "label": "H-Mirror", "value": False},
    "settings_vflip": {"type": "bool", "label": "V-Flip", "value": False},
}


class CameraSettingsActivity(Activity):
    def __init__(self):
        super().__init__()

    def on_start(self, request):
        super().on_start(request)
        if __debug__: logger.debug("CameraSettingsActivity on_start")
        self._create_ui()

    def on_resume(self):
        super().on_resume()
        if __debug__: logger.debug("CameraSettingsActivity on_resume")

    def on_new_intent(self, request):
        super().on_new_intent(request)
        if __debug__: logger.debug("CameraSettingsActivity on_new_intent")

    def on_pause(self):
        super().on_pause()
        if __debug__: logger.debug("CameraSettingsActivity on_pause")

    def _create_ui(self):
        self._container = lv.obj(lv.screen_active())
        self._container.set_size(lv.pct(100), lv.pct(100))

        title = lv.label(self._container)
        title.set_text("Camera Settings")
        title.align(lv.ALIGN.TOP_LEFT, 0, AppearanceManager.NOTIFICATION_BAR_HEIGHT)

        panel = lv.obj(self._container)
        panel.set_size(lv.pct(100), lv.pct(80))
        panel.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        panel.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        for key, setting in SETTINGS.items():
            row = lv.obj(panel)
            row.set_size(lv.pct(100), lv.SIZE_CONTENT)
            row.set_flex_flow(lv.FLEX_FLOW.ROW)

            label = lv.label(row)
            label.set_text(setting["label"])
            label.set_width(DisplayMetrics.width_pct(50))

            if setting["type"] == "bool":
                cb = lv.checkbox(row)
                cb.set_text("")
                cb.add_flag(lv.obj.FLAG.CHECKABLE)
                if setting["value"]:
                    cb.add_state(lv.STATE.CHECKED)
                cb.add_event_cb(lambda e, k=key: self._on_bool_change(e, k), lv.EVENT.VALUE_CHANGED, None)
            elif setting["type"] == "options" and "dropdown" in setting and setting["dropdown"]:
                dd = lv.dropdown(row)
                items = "\n".join(setting["values"].keys())
                idx = 0
                for i, v in enumerate(setting["values"].values()):
                    if v == setting["value"]:
                        idx = i
                        break
                dd.set_options_static(items)
                dd.set_selected(idx)
                dd.add_event_cb(lambda e, k=key: self._on_option_change(e, k), lv.EVENT.VALUE_CHANGED, None)
            elif setting["type"] == "options":
                dd = lv.dropdown(row)
                items = "\n".join(setting["values"].keys())
                idx = 0
                for i, v in enumerate(setting["values"].values()):
                    if v == setting["value"]:
                        idx = i
                        break
                dd.set_options_static(items)
                dd.set_selected(idx)
                dd.add_event_cb(lambda e, k=key: self._on_option_change(e, k), lv.EVENT.VALUE_CHANGED, None)

    def _on_bool_change(self, event, key):
        cb = event.get_target_obj()
        state = cb.get_state()
        checked = (state & lv.STATE.CHECKED) != 0
        SETTINGS[key]["value"] = checked
        if __debug__: logger.debug("Setting '%s' changed to %s", key, checked)

    def _on_option_change(self, event, key):
        dd = event.get_target_obj()
        idx = dd.get_selected()
        values_dd = list(SETTINGS[key]["values"].values())
        if idx is not None and idx < len(values_dd):
            SETTINGS[key]["value"] = values_dd[idx]
            if __debug__: logger.debug("Setting '%s' changed to index %s (value=%s)", key, idx, values_dd[idx])

    def get_settings(self):
        return SETTINGS
