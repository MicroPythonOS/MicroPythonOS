import lvgl as lv

from ..config import SharedPreferences
from ..app.activity import Activity
from .display_metrics import DisplayMetrics
from .widget_animator import WidgetAnimator

class CameraSettingsActivity(Activity):

    # Original: { 2560, 1920,   0,   0, 2623, 1951, 32, 16, 2844, 1968 }
    # Worked for digital zoom in C: { 2560, 1920, 0, 0, 2623, 1951, 992, 736, 2844, 1968 }
    startX_default=0
    startY_default=0
    endX_default=2623
    endY_default=1951
    offsetX_default=32
    offsetY_default=16
    totalX_default=2844
    totalY_default=1968
    outputX_default=640
    outputY_default=480
    scale_default=False
    binning_default=False

    # Common defaults shared by both normal and scanqr modes (25 settings)
    COMMON_DEFAULTS = {
        # Basic image adjustments
        "brightness": 0,
        "contrast": 0,
        "saturation": 0,
        # Orientation
        "hmirror": False,
        "vflip": True,
        # Visual effects
        "special_effect": 0,
        # Exposure control
        "exposure_ctrl": True,
        "aec_value": 300,
        "aec2": False,
        # Gain control
        "gain_ctrl": True,
        "agc_gain": 0,
        "gainceiling": 0,
        # White balance
        "whitebal": True,
        "wb_mode": 0,
        "awb_gain": True,
        # Sensor-specific
        "sharpness": 0,
        "denoise": 0,
        # Advanced corrections
        "colorbar": False,
        "dcw": True,
        "bpc": False,
        "wpc": True,
        "lenc": True,
    }

    # Normal mode specific defaults
    NORMAL_DEFAULTS = {
        "resolution_width": 240,
        "resolution_height": 240,
        "colormode": True,
        "ae_level": 0,
        "raw_gma": True,
    }

    # Scanqr mode specific defaults
    SCANQR_DEFAULTS = {
        "resolution_width": 960,
        "resolution_height": 960,
        "colormode": False,
        "ae_level": 2, # Higher auto-exposure compensation
        "raw_gma": False, # Disable raw gamma for better contrast
    }

    # Resolution options for both ESP32 and webcam
    # Webcam supports all ESP32 resolutions via automatic cropping/padding
    RESOLUTIONS = [
        ("96x96", "96x96"),
        ("160x120", "160x120"),
        ("128x128", "128x128"),
        ("176x144", "176x144"),
        ("240x176", "240x176"),
        ("240x240", "240x240"),
        ("320x240", "320x240"),
        ("320x320", "320x320"),
        ("400x296", "400x296"),
        ("480x320", "480x320"),
        ("480x480", "480x480"),
        ("640x480", "640x480"),
        ("640x640", "640x640"),
        ("720x720", "720x720"),
        #("800x600", "800x600"), # somehow this fails to initialize
        #("800x800", "800x800"), # somehow this fails to initialize
        #("1024x768", "1024x768"), # this resolution is lower than 960x960 but it looks higher
        ("960x960", "960x960"), # ideal for QR scanning, quick and high quality scaling (binning)
        #("1280x720", "1280x720"), # too thin (16:9) and same pixel area as 960x960
        #("1024x1024", "1024x1024"), # somehow this fails to initialize
        # Disabled because they use a lot of RAM and are very slow:
        #("1280x1024", "1280x1024"),
        #("1280x1280", "1280x1280"),
        #("1600x1200", "1600x1200"),
        #("1920x1080", "1920x1080"),
    ]

    # Widgets:
    button_cont = None

    def __init__(self):
        super().__init__()
        self.ui_controls = {}
        self.control_metadata = {}  # Store pref_key and option_values for each control
        self.dependent_controls = {}

    def onCreate(self):
        self.use_webcam = self.getIntent().extras.get("use_webcam")
        self.prefs = self.getIntent().extras.get("prefs")
        self.scanqr_mode = self.getIntent().extras.get("scanqr_mode")

        # Create main screen
        screen = lv.obj()
        screen.set_size(lv.pct(100), lv.pct(100))
        screen.set_style_pad_all(1, lv.PART.MAIN)

        # Create tabview
        tabview = lv.tabview(screen)
        tabview.set_tab_bar_size(DisplayMetrics.pct_of_height(15))
        #tabview.set_size(lv.pct(100), pct_of_display_height(80))

        # Create Basic tab (always)
        basic_tab = tabview.add_tab("Basic")
        self.create_basic_tab(basic_tab, self.prefs)

        # Create Advanced and Expert tabs only for ESP32 camera
        if not self.use_webcam or True: # for now, show all tabs
            advanced_tab = tabview.add_tab("Advanced")
            self.create_advanced_tab(advanced_tab, self.prefs)

            expert_tab = tabview.add_tab("Expert")
            self.create_expert_tab(expert_tab, self.prefs)

            #raw_tab = tabview.add_tab("Raw")
            #self.create_raw_tab(raw_tab, self.prefs)

        self.setContentView(screen)

    def create_slider(self, parent, label_text, min_val, max_val, default_val, pref_key):
        """Create slider with label showing current value."""
        cont = lv.obj(parent)
        cont.set_size(lv.pct(100), 60)
        cont.set_style_pad_all(3, lv.PART.MAIN)

        label = lv.label(cont)
        label.set_text(f"{label_text}: {default_val}")
        label.align(lv.ALIGN.TOP_LEFT, 0, 0)

        slider = lv.slider(cont)
        slider.set_size(lv.pct(90), 15)
        slider.set_range(min_val, max_val)
        slider.set_value(default_val, False)
        slider.align(lv.ALIGN.BOTTOM_MID, 0, -10)

        def slider_changed(e):
            val = slider.get_value()
            label.set_text(f"{label_text}: {val}")

        slider.add_event_cb(slider_changed, lv.EVENT.VALUE_CHANGED, None)

        return slider, label, cont

    def create_checkbox(self, parent, label_text, default_val, pref_key):
        """Create checkbox with label."""
        cont = lv.obj(parent)
        cont.set_size(lv.pct(100), 35)
        cont.set_style_pad_all(3, lv.PART.MAIN)

        checkbox = lv.checkbox(cont)
        checkbox.set_text(label_text)
        if default_val:
            checkbox.add_state(lv.STATE.CHECKED)
        checkbox.align(lv.ALIGN.LEFT_MID, 0, 0)

        return checkbox, cont

    def create_dropdown(self, parent, label_text, options, default_idx, pref_key):
        """Create dropdown with label."""
        cont = lv.obj(parent)
        cont.set_size(lv.pct(100), lv.SIZE_CONTENT)
        cont.set_style_pad_all(2, lv.PART.MAIN)

        label = lv.label(cont)
        label.set_text(label_text)
        label.set_size(lv.pct(50), lv.SIZE_CONTENT)
        label.align(lv.ALIGN.LEFT_MID, 0, 0)

        dropdown = lv.dropdown(cont)
        dropdown.set_size(lv.pct(50), lv.SIZE_CONTENT)
        dropdown.align(lv.ALIGN.RIGHT_MID, 0, 0)

        options_str = "\n".join([text for text, _ in options])
        dropdown.set_options(options_str)
        dropdown.set_selected(default_idx)

        # Store metadata separately
        option_values = [val for _, val in options]
        self.control_metadata[id(dropdown)] = {
            "pref_key": pref_key,
            "type": "dropdown",
            "option_values": option_values
        }

        return dropdown, cont

    def create_textarea(self, parent, label_text, min_val, max_val, default_val, pref_key):
        cont = lv.obj(parent)
        cont.set_size(lv.pct(100), lv.SIZE_CONTENT)
        cont.set_style_pad_all(3, lv.PART.MAIN)

        label = lv.label(cont)
        label.set_text(f"{label_text}:")
        label.align(lv.ALIGN.TOP_LEFT, 0, 0)

        textarea = lv.textarea(cont)
        textarea.set_width(lv.pct(50))
        textarea.set_one_line(True) # might not be good for all settings but it's good for most
        textarea.set_text(str(default_val))
        textarea.align(lv.ALIGN.TOP_RIGHT, 0, 0)

        # Initialize keyboard (hidden initially)
        from ..indev.mpos_sdl_keyboard import MposKeyboard
        keyboard = MposKeyboard(parent)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        keyboard.add_flag(lv.obj.FLAG.HIDDEN)
        keyboard.set_textarea(textarea)

        return textarea, cont

    def add_buttons(self, parent):
        # Save/Cancel buttons at bottom
        button_cont = lv.obj(parent)
        button_cont.set_size(lv.pct(100), DisplayMetrics.pct_of_height(20))
        button_cont.remove_flag(lv.obj.FLAG.SCROLLABLE)
        button_cont.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        button_cont.set_style_border_width(0, lv.PART.MAIN)

        save_button = lv.button(button_cont)
        save_button.set_size(lv.SIZE_CONTENT, lv.SIZE_CONTENT)
        save_button.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        save_button.add_event_cb(lambda e: self.save_and_close(), lv.EVENT.CLICKED, None)
        save_label = lv.label(save_button)
        savetext = "Save"
        if self.scanqr_mode:
            savetext += " QR tweaks"
        save_label.set_text(savetext)
        save_label.center()

        cancel_button = lv.button(button_cont)
        cancel_button.set_size(DisplayMetrics.pct_of_width(25), lv.SIZE_CONTENT)
        cancel_button.set_style_opa(lv.OPA._70, lv.PART.MAIN)
        if self.scanqr_mode:
            cancel_button.align(lv.ALIGN.BOTTOM_MID, DisplayMetrics.pct_of_width(10), 0)
        else:
            cancel_button.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        cancel_button.add_event_cb(lambda e: self.finish(), lv.EVENT.CLICKED, None)
        cancel_label = lv.label(cancel_button)
        cancel_label.set_text("Cancel")
        cancel_label.center()

        erase_button = lv.button(button_cont)
        erase_button.set_size(DisplayMetrics.pct_of_width(20), lv.SIZE_CONTENT)
        erase_button.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        erase_button.add_event_cb(lambda e: self.erase_and_close(), lv.EVENT.CLICKED, None)
        erase_label = lv.label(erase_button)
        erase_label.set_text("Erase")
        erase_label.center()


    def create_basic_tab(self, tab, prefs):
        """Create Basic settings tab."""
        tab.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        #tab.set_scrollbar_mode(lv.SCROLLBAR_MODE.AUTO)
        tab.set_style_pad_all(1, lv.PART.MAIN)

        # Color Mode
        colormode = prefs.get_bool("colormode")
        checkbox, cont = self.create_checkbox(tab, "Color Mode (slower)", colormode, "colormode")
        self.ui_controls["colormode"] = checkbox

        # Resolution dropdown
        print(f"self.scanqr_mode: {self.scanqr_mode}")
        current_resolution_width = prefs.get_int("resolution_width")
        current_resolution_height = prefs.get_int("resolution_height")
        dropdown_value = f"{current_resolution_width}x{current_resolution_height}"
        print(f"looking for {dropdown_value}")
        resolution_idx = 0
        for idx, (_, value) in enumerate(self.RESOLUTIONS):
            print(f"got {value}")
            if value == dropdown_value:
                resolution_idx = idx
                print(f"found it! {idx}")
                break

        dropdown, cont = self.create_dropdown(tab, "Resolution:", self.RESOLUTIONS, resolution_idx, "resolution")
        self.ui_controls["resolution"] = dropdown

        # Brightness
        brightness = prefs.get_int("brightness")
        slider, label, cont = self.create_slider(tab, "Brightness", -2, 2, brightness, "brightness")
        self.ui_controls["brightness"] = slider

        # Contrast
        contrast = prefs.get_int("contrast")
        slider, label, cont = self.create_slider(tab, "Contrast", -2, 2, contrast, "contrast")
        self.ui_controls["contrast"] = slider

        # Saturation
        saturation = prefs.get_int("saturation")
        slider, label, cont = self.create_slider(tab, "Saturation", -2, 2, saturation, "saturation")
        self.ui_controls["saturation"] = slider

        # Horizontal Mirror
        hmirror = prefs.get_bool("hmirror")
        checkbox, cont = self.create_checkbox(tab, "Horizontal Mirror", hmirror, "hmirror")
        self.ui_controls["hmirror"] = checkbox

        # Vertical Flip
        vflip = prefs.get_bool("vflip")
        checkbox, cont = self.create_checkbox(tab, "Vertical Flip", vflip, "vflip")
        self.ui_controls["vflip"] = checkbox

        self.add_buttons(tab)

    def create_advanced_tab(self, tab, prefs):
        """Create Advanced settings tab."""
        tab.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        tab.set_style_pad_all(1, lv.PART.MAIN)

        # Auto Exposure Control (master switch)
        exposure_ctrl = prefs.get_bool("exposure_ctrl")
        aec_checkbox, cont = self.create_checkbox(tab, "Auto Exposure", exposure_ctrl, "exposure_ctrl")
        self.ui_controls["exposure_ctrl"] = aec_checkbox

        # Manual Exposure Value (dependent)
        aec_value = prefs.get_int("aec_value")
        me_slider, label, me_cont = self.create_slider(tab, "Manual Exposure", 0, 1200, aec_value, "aec_value")
        self.ui_controls["aec_value"] = me_slider

        # Auto Exposure Level (dependent)
        ae_level = prefs.get_int("ae_level")
        ae_slider, label, ae_cont = self.create_slider(tab, "Auto Exposure Level", -2, 2, ae_level, "ae_level")
        self.ui_controls["ae_level"] = ae_slider

        # Add dependency handler
        def exposure_ctrl_changed(e=None):
            is_auto = aec_checkbox.get_state() & lv.STATE.CHECKED
            if is_auto:
                WidgetAnimator.smooth_hide(me_cont, duration=1000)
                WidgetAnimator.smooth_show(ae_cont, delay=1000)
            else:
                WidgetAnimator.smooth_hide(ae_cont, duration=1000)
                WidgetAnimator.smooth_show(me_cont, delay=1000)

        aec_checkbox.add_event_cb(exposure_ctrl_changed, lv.EVENT.VALUE_CHANGED, None)
        exposure_ctrl_changed()

        # Night Mode (AEC2)
        aec2 = prefs.get_bool("aec2")
        checkbox, cont = self.create_checkbox(tab, "Night Mode (AEC2)", aec2, "aec2")
        self.ui_controls["aec2"] = checkbox

        # Auto Gain Control (master switch)
        gain_ctrl = prefs.get_bool("gain_ctrl")
        agc_checkbox, cont = self.create_checkbox(tab, "Auto Gain", gain_ctrl, "gain_ctrl")
        self.ui_controls["gain_ctrl"] = agc_checkbox

        # Manual Gain Value (dependent)
        agc_gain = prefs.get_int("agc_gain")
        slider, label, agc_cont = self.create_slider(tab, "Manual Gain", 0, 30, agc_gain, "agc_gain")
        self.ui_controls["agc_gain"] = slider

        def gain_ctrl_changed(e=None):
            is_auto = agc_checkbox.get_state() & lv.STATE.CHECKED
            gain_slider = self.ui_controls["agc_gain"]
            if is_auto:
                WidgetAnimator.smooth_hide(agc_cont, duration=1000)
            else:
                WidgetAnimator.smooth_show(agc_cont, duration=1000)

        agc_checkbox.add_event_cb(gain_ctrl_changed, lv.EVENT.VALUE_CHANGED, None)
        gain_ctrl_changed()

        # Gain Ceiling
        gainceiling_options = [
            ("2X", 0), ("4X", 1), ("8X", 2), ("16X", 3),
            ("32X", 4), ("64X", 5), ("128X", 6)
        ]
        gainceiling = prefs.get_int("gainceiling")
        dropdown, cont = self.create_dropdown(tab, "Gain Ceiling:", gainceiling_options, gainceiling, "gainceiling")
        self.ui_controls["gainceiling"] = dropdown

        # Auto White Balance (master switch)
        whitebal = prefs.get_bool("whitebal")
        wbcheckbox, cont = self.create_checkbox(tab, "Auto White Balance", whitebal, "whitebal")
        self.ui_controls["whitebal"] = wbcheckbox

        # White Balance Mode (dependent)
        wb_mode_options = [
            ("Auto", 0), ("Sunny", 1), ("Cloudy", 2), ("Office", 3), ("Home", 4)
        ]
        wb_mode = prefs.get_int("wb_mode")
        wb_dropdown, wb_cont = self.create_dropdown(tab, "WB Mode:", wb_mode_options, wb_mode, "wb_mode")
        self.ui_controls["wb_mode"] = wb_dropdown

        def whitebal_changed(e=None):
            is_auto = wbcheckbox.get_state() & lv.STATE.CHECKED
            if is_auto:
                WidgetAnimator.smooth_hide(wb_cont, duration=1000)
            else:
                WidgetAnimator.smooth_show(wb_cont, duration=1000)
        wbcheckbox.add_event_cb(whitebal_changed, lv.EVENT.VALUE_CHANGED, None)
        whitebal_changed()

        # AWB Gain
        awb_gain = prefs.get_bool("awb_gain")
        checkbox, cont = self.create_checkbox(tab, "AWB Gain", awb_gain, "awb_gain")
        self.ui_controls["awb_gain"] = checkbox

        self.add_buttons(tab)

        # Special Effect
        special_effect_options = [
            ("None", 0), ("Negative", 1), ("Grayscale", 2),
            ("Reddish", 3), ("Greenish", 4), ("Blue", 5), ("Retro", 6)
        ]
        special_effect = prefs.get_int("special_effect")
        dropdown, cont = self.create_dropdown(tab, "Special Effect:", special_effect_options,
                                              special_effect, "special_effect")
        self.ui_controls["special_effect"] = dropdown

    def create_expert_tab(self, tab, prefs):
        """Create Expert settings tab."""
        #tab.set_scrollbar_mode(lv.SCROLLBAR_MODE.AUTO)
        tab.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        tab.set_style_pad_all(1, lv.PART.MAIN)

        # Sharpness
        sharpness = prefs.get_int("sharpness")
        slider, label, cont = self.create_slider(tab, "Sharpness", -3, 3, sharpness, "sharpness")
        self.ui_controls["sharpness"] = slider

        # Denoise
        denoise = prefs.get_int("denoise")
        slider, label, cont = self.create_slider(tab, "Denoise", 0, 8, denoise, "denoise")
        self.ui_controls["denoise"] = slider

        # JPEG Quality
        # Disabled because JPEG is not used right now
        #quality = prefs.get_int("quality", 85)
        #slider, label, cont = self.create_slider(tab, "JPEG Quality", 0, 100, quality, "quality")
        #self.ui_controls["quality"] = slider

        # Color Bar
        colorbar = prefs.get_bool("colorbar")
        checkbox, cont = self.create_checkbox(tab, "Color Bar Test", colorbar, "colorbar")
        self.ui_controls["colorbar"] = checkbox

        # DCW Mode
        dcw = prefs.get_bool("dcw")
        checkbox, cont = self.create_checkbox(tab, "Downsize Crop Window", dcw, "dcw")
        self.ui_controls["dcw"] = checkbox

        # Black Point Compensation
        bpc = prefs.get_bool("bpc")
        checkbox, cont = self.create_checkbox(tab, "Black Point Compensation", bpc, "bpc")
        self.ui_controls["bpc"] = checkbox

        # White Point Compensation
        wpc = prefs.get_bool("wpc")
        checkbox, cont = self.create_checkbox(tab, "White Point Compensation", wpc, "wpc")
        self.ui_controls["wpc"] = checkbox

        # Raw Gamma Mode
        raw_gma = prefs.get_bool("raw_gma")
        checkbox, cont = self.create_checkbox(tab, "Raw Gamma Mode", raw_gma, "raw_gma")
        self.ui_controls["raw_gma"] = checkbox

        # Lens Correction
        lenc = prefs.get_bool("lenc")
        checkbox, cont = self.create_checkbox(tab, "Lens Correction", lenc, "lenc")
        self.ui_controls["lenc"] = checkbox

        self.add_buttons(tab)

    def create_raw_tab(self, tab, prefs):
        tab.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        tab.set_style_pad_all(0, lv.PART.MAIN)

        # This would be nice but does not provide adequate resolution:
        #startX, label, cont = self.create_slider(tab, "startX", 0, 2844, startX, "startX")

        startX = prefs.get_int("startX", self.startX_default)
        textarea, cont = self.create_textarea(tab, "startX", 0, 2844, startX, "startX")
        self.ui_controls["startX"] = textarea

        startY = prefs.get_int("startY", self.startY_default)
        textarea, cont = self.create_textarea(tab, "startY", 0, 2844, startY, "startY")
        self.ui_controls["startY"] = textarea

        endX = prefs.get_int("endX", self.endX_default)
        textarea, cont = self.create_textarea(tab, "endX", 0, 2844, endX, "endX")
        self.ui_controls["endX"] = textarea

        endY = prefs.get_int("endY", self.endY_default)
        textarea, cont = self.create_textarea(tab, "endY", 0, 2844, endY, "endY")
        self.ui_controls["endY"] = textarea

        offsetX = prefs.get_int("offsetX", self.offsetX_default)
        textarea, cont = self.create_textarea(tab, "offsetX", 0, 2844, offsetX, "offsetX")
        self.ui_controls["offsetX"] = textarea

        offsetY = prefs.get_int("offsetY", self.offsetY_default)
        textarea, cont = self.create_textarea(tab, "offsetY", 0, 2844, offsetY, "offsetY")
        self.ui_controls["offsetY"] = textarea

        totalX = prefs.get_int("totalX", self.totalX_default)
        textarea, cont = self.create_textarea(tab, "totalX", 0, 2844, totalX, "totalX")
        self.ui_controls["totalX"] = textarea

        totalY = prefs.get_int("totalY", self.totalY_default)
        textarea, cont = self.create_textarea(tab, "totalY", 0, 2844, totalY, "totalY")
        self.ui_controls["totalY"] = textarea

        outputX = prefs.get_int("outputX", self.outputX_default)
        textarea, cont = self.create_textarea(tab, "outputX", 0, 2844, outputX, "outputX")
        self.ui_controls["outputX"] = textarea

        outputY = prefs.get_int("outputY", self.outputY_default)
        textarea, cont = self.create_textarea(tab, "outputY", 0, 2844, outputY, "outputY")
        self.ui_controls["outputY"] = textarea

        scale = prefs.get_bool("scale", self.scale_default)
        checkbox, cont = self.create_checkbox(tab, "Scale?", scale, "scale")
        self.ui_controls["scale"] = checkbox

        binning = prefs.get_bool("binning", self.binning_default)
        checkbox, cont = self.create_checkbox(tab, "Binning?", binning, "binning")
        self.ui_controls["binning"] = checkbox

        self.add_buttons(tab)

    def erase_and_close(self):
        self.prefs.edit().remove_all().commit()
        self.setResult(True, {"settings_changed": True})
        self.finish()

    def save_and_close(self):
        """Save all settings to SharedPreferences and return result."""
        editor = self.prefs.edit()

        # Save all UI control values
        for pref_key, control in self.ui_controls.items():
            print(f"saving {pref_key} with {control}")
            control_id = id(control)
            metadata = self.control_metadata.get(control_id, {})

            if isinstance(control, lv.slider):
                value = control.get_value()
                editor.put_int(pref_key, value)
            elif isinstance(control, lv.checkbox):
                is_checked = control.get_state() & lv.STATE.CHECKED
                editor.put_bool(pref_key, bool(is_checked))
            elif isinstance(control, lv.textarea):
                try:
                    value = int(control.get_text())
                    editor.put_int(pref_key, value)
                except Exception as e:
                    print(f"Error while trying to save {pref_key}: {e}")
            elif isinstance(control, lv.dropdown):
                selected_idx = control.get_selected()
                option_values = metadata.get("option_values", [])
                if pref_key == "resolution":
                    try:
                        # Resolution stored as 2 ints
                        value = option_values[selected_idx]
                        width_str, height_str = value.split('x')
                        editor.put_int("resolution_width", int(width_str))
                        editor.put_int("resolution_height", int(height_str))
                    except Exception as e:
                        print(f"Error parsing resolution '{value}': {e}")
                else:
                    # Other dropdowns store integer enum values
                    value = option_values[selected_idx]
                    editor.put_int(pref_key, value)

        editor.commit()
        print("Camera settings saved")

        # Return success result
        self.setResult(True, {"settings_changed": True})
        self.finish()
