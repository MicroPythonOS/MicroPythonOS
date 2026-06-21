import logging
import lvgl as lv

from ..app.activity import Activity
from .camera_activity import CameraActivity
from .display_metrics import DisplayMetrics
from .widget_animator import WidgetAnimator
from ..camera_manager import CameraManager

logger = logging.getLogger(__name__)

"""
InputActivity is a generic single-value input screen.

It is launched with an Intent containing a "setting" metadata dict
(and optionally an initial "value").  The activity only handles
rendering and user input; it does NOT persist the value.  On save it
returns a result dict with the new value:

    {"result_code": True, "value": <new_value>, "key": ..., "ui": ...}

Callers (e.g. SettingActivity) are responsible for persisting the
result and updating any UI that depends on it.
"""
class InputActivity(Activity):

    active_radio_index = -1  # Track active radio button index

    # Widgets:
    keyboard = None
    textarea = None
    dropdown = None
    radio_container = None
    slider = None

    def onCreate(self):
        self.setting = self.getIntent().extras.get("setting")
        if not self.setting:
            logger.error("InputActivity requires 'setting' in Intent extras")
            self.finish()
            return

        if __debug__: logger.debug("%s", self.setting)

        initial_value = self.getIntent().extras.get("value")
        if initial_value is None:
            initial_value = self.setting.get("default_value", "")
        # Coerce None default to empty string.
        if initial_value is None:
            initial_value = ""

        input_screen = lv.obj()
        input_screen.set_style_pad_all(0, lv.PART.MAIN)
        input_screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        top_cont = lv.obj(input_screen)
        top_cont.set_width(lv.pct(100))
        top_cont.set_style_border_width(0, lv.PART.MAIN)
        top_cont.set_height(lv.SIZE_CONTENT)
        top_cont.set_style_pad_all(0, lv.PART.MAIN)
        top_cont.set_flex_flow(lv.FLEX_FLOW.ROW)
        top_cont.set_style_flex_main_place(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.PART.MAIN)
        top_cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

        setting_label = lv.label(top_cont)
        setting_label.set_text(self.setting["title"])
        setting_label.align(lv.ALIGN.TOP_LEFT, 0, 0)
        setting_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)

        ui = self.setting.get("ui")
        ui_options = self.setting.get("ui_options")
        if ui and ui == "radiobuttons" and ui_options:
            # Create container for radio buttons
            self.radio_container = lv.obj(input_screen)
            self.radio_container.set_width(lv.pct(100))
            self.radio_container.set_height(lv.SIZE_CONTENT)
            self.radio_container.set_flex_flow(lv.FLEX_FLOW.COLUMN)
            self.radio_container.add_event_cb(self.radio_event_handler, lv.EVENT.VALUE_CHANGED, None)
            # `allow_deselect` is an opt-in for inputs where "nothing
            # selected" is a legitimate value.
            self._radio_allow_deselect = bool(self.setting.get("allow_deselect", False))
            # Create radio buttons and check the right one
            self.active_radio_index = -1 # none
            for i, (option_text, option_value) in enumerate(ui_options):
                cb = self.create_radio_button(self.radio_container, option_text, i)
                if initial_value == option_value:
                    self.active_radio_index = i
                    cb.add_state(lv.STATE.CHECKED)
        elif ui and ui == "dropdown" and ui_options:
            self.dropdown = lv.dropdown(input_screen)
            self.dropdown.set_width(lv.pct(100))
            options_with_newlines = ""
            for option in ui_options:
                if option[0] != option[1]:
                    options_with_newlines += ("%s (%s)\n" % (option[0], option[1]))
                else: # don't show identical options
                    options_with_newlines += ("%s\n" % option[0])
            self.dropdown.set_options(options_with_newlines)
            # select the right one:
            for i, (option_text, option_value) in enumerate(ui_options):
                if initial_value == option_value:
                    self.dropdown.set_selected(i)
                    break # no need to check the rest because only one can be selected
        elif ui and ui == "slider":
            slider_min = self.setting.get("min", 0)
            slider_max = self.setting.get("max", 100)
            try:
                current_val = int(initial_value) if initial_value else slider_min
            except (ValueError, TypeError):
                current_val = slider_min
            current_val = max(slider_min, min(slider_max, current_val))

            self._slider_val_label = lv.label(input_screen)
            self._slider_val_label.set_text(str(current_val))
            self._slider_val_label.set_style_text_font(lv.font_montserrat_24, lv.PART.MAIN)
            self._slider_val_label.set_style_pad_top(DisplayMetrics.pct_of_width(6), lv.PART.MAIN)

            self.slider = lv.slider(input_screen)
            self.slider.set_range(slider_min, slider_max)
            self.slider.set_value(current_val, False)
            self.slider.set_width(lv.pct(90))
            def slider_changed(e):
                self._slider_val_label.set_text(str(self.slider.get_value()))
            self.slider.add_event_cb(slider_changed, lv.EVENT.VALUE_CHANGED, None)
        else: # Textarea for other settings
            ui = "textarea"
            self.textarea = lv.textarea(input_screen)
            self.textarea.set_width(lv.pct(100))
            self.textarea.set_style_pad_all(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
            self.textarea.set_style_margin_left(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
            self.textarea.set_style_margin_right(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
            self.textarea.set_one_line(True)
            if initial_value:
                self.textarea.set_text(initial_value)
            placeholder = self.setting.get("placeholder")
            if placeholder:
                self.textarea.set_placeholder_text(placeholder)
            from mpos import MposKeyboard
            self.keyboard = MposKeyboard(input_screen)
            self.keyboard.add_flag(lv.obj.FLAG.HIDDEN)
            self.keyboard.set_textarea(self.textarea)

        # Optional informational note below the input widget.
        note_text = self.setting.get("note")
        if note_text:
            note_label = lv.label(input_screen)
            note_label.set_text(note_text)
            note_label.set_long_mode(lv.label.LONG_MODE.WRAP)
            note_label.set_width(lv.pct(95))
            note_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
            note_label.set_style_text_color(lv.color_hex(0x999999), lv.PART.MAIN)
            note_label.set_style_pad_top(DisplayMetrics.pct_of_width(3), lv.PART.MAIN)

        # Button container
        btn_cont = lv.obj(input_screen)
        btn_cont.set_width(lv.pct(100))
        btn_cont.set_style_border_width(0, lv.PART.MAIN)
        btn_cont.set_height(lv.SIZE_CONTENT)
        btn_cont.set_flex_flow(lv.FLEX_FLOW.ROW)
        btn_cont.set_style_flex_main_place(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.PART.MAIN)
        # Cancel button
        cancel_btn = lv.button(btn_cont)
        cancel_btn.set_size(lv.pct(45), lv.SIZE_CONTENT)
        cancel_btn.set_style_opa(lv.OPA._70, lv.PART.MAIN)
        cancel_label = lv.label(cancel_btn)
        cancel_label.set_text("Cancel")
        cancel_label.center()
        cancel_btn.add_event_cb(lambda e: self.cancel_input(), lv.EVENT.CLICKED, None)
        # Save button
        save_btn = lv.button(btn_cont)
        save_btn.set_size(lv.pct(45), lv.SIZE_CONTENT)
        save_label = lv.label(save_btn)
        save_label.set_text("Save")
        save_label.center()
        save_btn.add_event_cb(lambda e: self.save_input(), lv.EVENT.CLICKED, None)

        if ui == "textarea" and CameraManager.has_camera(): # Scan QR button for text settings (only if camera available)
            cambutton = lv.button(input_screen)
            cambutton.align(lv.ALIGN.BOTTOM_MID, 0, 0)
            cambutton.set_size(lv.pct(100), lv.pct(30))
            cambuttonlabel = lv.label(cambutton)
            cambuttonlabel.set_text("Scan data from QR code")
            cambuttonlabel.set_style_text_font(lv.font_montserrat_18, lv.PART.MAIN)
            cambuttonlabel.align(lv.ALIGN.TOP_MID, 0, 0)
            cambuttonlabel2 = lv.label(cambutton)
            cambuttonlabel2.set_text("Tip: Create your own QR code,\nusing https://genqrcode.com or another tool.")
            cambuttonlabel2.set_style_text_font(lv.font_montserrat_10, lv.PART.MAIN)
            cambuttonlabel2.align(lv.ALIGN.BOTTOM_MID, 0, 0)
            cambutton.add_event_cb(self.cambutton_cb, lv.EVENT.CLICKED, None)

        self.setContentView(input_screen)

    def onBackPressed(self, screen):
        """Hardware back / swipe back cancels the input."""
        self.cancel_input()
        return True

    def onStop(self, screen):
        if self.keyboard:
            WidgetAnimator.smooth_hide(self.keyboard)

    def cancel_input(self):
        """Finish without saving, returning a cancel result to the caller."""
        self.setResult(False, {
            "value": self._read_value(),
            "key": self.setting.get("key"),
            "ui": self.setting.get("ui", "textarea"),
        })
        self.finish()

    def radio_event_handler(self, event):
        if __debug__: logger.debug("radio_event_handler called")
        target_obj = event.get_target_obj()
        target_obj_state = target_obj.get_state()
        if __debug__: logger.debug("target_obj state %s is %s", target_obj.get_text(), target_obj_state)
        checked = target_obj_state & lv.STATE.CHECKED
        current_checkbox_index = target_obj.get_index()
        if __debug__: logger.debug("current_checkbox_index: %s", current_checkbox_index)
        if not checked:
            # Radio-button convention: clicking the already-selected option
            # must NOT un-select it, unless the caller opted in via
            # allow_deselect.
            if self.active_radio_index == current_checkbox_index:
                if getattr(self, '_radio_allow_deselect', False):
                    if __debug__: logger.debug("radio: un-check of active option %s (allow_deselect=True)", current_checkbox_index)
                    self.active_radio_index = -1
                else:
                    logger.warning("radio: ignoring un-check of active option %s (radios require exactly one)", current_checkbox_index)
                    target_obj.add_state(lv.STATE.CHECKED)
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

    def gotqr_result_callback(self, result):
        if __debug__: logger.debug("QR capture finished, result: %s", result)
        if result.get("result_code"):
            data = result.get("data")
            if __debug__: logger.debug("Setting textarea data: %s", data)
            self.textarea.set_text(data)

    def cambutton_cb(self, event):
        from ..content.intent import Intent
        if __debug__: logger.debug("cambutton clicked!")
        self.startActivityForResult(Intent(activity_class=CameraActivity).putExtra("scanqr_intent", True), self.gotqr_result_callback)

    def _read_value(self):
        ui = self.setting.get("ui")
        ui_options = self.setting.get("ui_options")
        if ui and ui == "radiobuttons" and ui_options:
            selected_idx = self.active_radio_index
            if selected_idx >= 0:
                return ui_options[selected_idx][1]
            return ""
        elif ui and ui == "dropdown" and ui_options:
            selected_index = self.dropdown.get_selected()
            if __debug__: logger.debug("selected item: %s", selected_index)
            return ui_options[selected_index][1]
        elif ui and ui == "slider":
            return str(self.slider.get_value())
        elif self.textarea:
            return self.textarea.get_text()
        return ""

    def save_input(self):
        new_value = self._read_value()
        self.setResult(True, {
            "value": new_value,
            "key": self.setting.get("key"),
            "ui": self.setting.get("ui", "textarea"),
        })
        self.finish()
