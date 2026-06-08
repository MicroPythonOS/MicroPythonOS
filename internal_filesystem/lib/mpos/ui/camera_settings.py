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
        # Store metadata separately
        #raw_tab = tabview.add_tab("Raw")
        #self.create_raw_tab(raw_tab, self.prefs)
        # Create Basic tab (always)
        #tabview.set_size(lv.pct(100), pct_of_display_height(80))
        # Create tabview
        # Create main screen
    # Scanqr mode specific defaults
    # Normal mode specific defaults
        # Advanced corrections
        # Sensor-specific
        # White balance
        # Gain control
        # Exposure control
        # Visual effects
        # Orientation
        # Basic image adjustments
    # Common defaults shared by both normal and scanqr modes (25 settings)
    # Original: { 2560, 1920,   0,   0, 2623, 1951, 32, 16, 2844, 1968 }
    # Worked for digital zoom in C: { 2560, 1920, 0, 0, 2623, 1951, 992, 736, 2844, 1968 }
}


class CameraSettingsActivity(Activity):
    # Widgets:
        #("1280x720", "1280x720"), # too thin (16:9) and same pixel area as 960x960
        #("1024x1024", "1024x1024"), # somehow this fails to initialize
        # Disabled because they use a lot of RAM and are very slow:
        #("1280x1024", "1280x1024"),
        #("1280x1280", "1280x1280"),
        #("1600x1200", "1600x1200"),
        #("1920x1080", "1920x1080"),
        #("800x600", "800x600"), # somehow this fails to initialize
        #("800x800", "800x800"), # somehow this fails to initialize
        #("1024x768", "1024x768"), # this resolution is lower than 960x960 but it looks higher
    # Resolution options are the same for all cameras for now (can be split later)
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
        # Resolution dropdown
        # Color Mode
        #tab.set_scrollbar_mode(lv.SCROLLBAR_MODE.AUTO)
        # Save/Cancel buttons at bottom
        # Initialize keyboard (hidden initially)
                        break
        # Return success result
                    # Other dropdowns store integer enum values
                        # Resolution stored as 2 ints
        # Save all UI control values
        # This would be nice but does not provide adequate resolution:
        #startX, label, cont = self.create_slider(tab, "startX", 0, 2844, startX, "startX")
        # Lens Correction
        # Raw Gamma Mode
        # White Point Compensation
        # Black Point Compensation
        # DCW Mode
        # Color Bar
        # JPEG Quality
        # Disabled because JPEG is not used right now
        #quality = prefs.get_int("quality", 85)
        #slider, label, cont = self.create_slider(tab, "JPEG Quality", 0, 100, quality, "quality")
        #self.ui_controls["quality"] = slider
        # Denoise
        # Sharpness
        #tab.set_scrollbar_mode(lv.SCROLLBAR_MODE.AUTO)
        # Special Effect
        # AWB Gain
        # White Balance Mode (dependent)
        # Auto White Balance (master switch)
        # Gain Ceiling
        # Manual Gain Value (dependent)
        # Auto Gain Control (master switch)
        # Night Mode (AEC2)
        # Add dependency handler
        # Auto Exposure Level (dependent)
        # Manual Exposure Value (dependent)
        # Auto Exposure Control (master switch)
        # Vertical Flip
        # Horizontal Mirror
        # Saturation
        # Contrast
        # Brightness
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
