import lvgl as lv

import mpos
from mpos.apps import Activity, Intent
from mpos.ui.keyboard import MposKeyboard
from .camera_app import CameraApp

"""
SettingActivity is used to edit one setting.
For now, it only supports strings.
"""
class SettingActivity(Activity):

    active_radio_index = -1  # Track active radio button index
    prefs = None # taken from the intent

    # Widgets:
    keyboard = None
    textarea = None
    dropdown = None
    radio_container = None

    def __init__(self):
        super().__init__()
        self.setting = None

    def onCreate(self):
        self.prefs = self.getIntent().extras.get("prefs")
        setting = self.getIntent().extras.get("setting")
        print(setting)

        settings_screen_detail = lv.obj()
        settings_screen_detail.set_style_pad_all(0, lv.PART.MAIN)
        settings_screen_detail.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        top_cont = lv.obj(settings_screen_detail)
        top_cont.set_width(lv.pct(100))
        top_cont.set_style_border_width(0, lv.PART.MAIN)
        top_cont.set_height(lv.SIZE_CONTENT)
        top_cont.set_style_pad_all(0, lv.PART.MAIN)
        top_cont.set_flex_flow(lv.FLEX_FLOW.ROW)
        top_cont.set_style_flex_main_place(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.PART.MAIN)
        top_cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

        setting_label = lv.label(top_cont)
        setting_label.set_text(setting["title"])
        setting_label.align(lv.ALIGN.TOP_LEFT, 0, 0)
        setting_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)

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
        else: # Textarea for other settings
            self.textarea = lv.textarea(settings_screen_detail)
            self.textarea.set_width(lv.pct(100))
            self.textarea.set_style_pad_all(mpos.ui.pct_of_display_width(2), lv.PART.MAIN)
            self.textarea.set_style_margin_left(mpos.ui.pct_of_display_width(2), lv.PART.MAIN)
            self.textarea.set_style_margin_right(mpos.ui.pct_of_display_width(2), lv.PART.MAIN)
            self.textarea.set_one_line(True)
            if current_setting:
                self.textarea.set_text(current_setting)
            placeholder = setting.get("placeholder")
            if placeholder:
                self.textarea.set_placeholder_text(placeholder)
            self.keyboard = MposKeyboard(settings_screen_detail)
            self.keyboard.add_flag(lv.obj.FLAG.HIDDEN)
            self.keyboard.set_textarea(self.textarea)

        # Button container
        btn_cont = lv.obj(settings_screen_detail)
        btn_cont.set_width(lv.pct(100))
        btn_cont.set_style_border_width(0, lv.PART.MAIN)
        btn_cont.set_height(lv.SIZE_CONTENT)
        btn_cont.set_flex_flow(lv.FLEX_FLOW.ROW)
        btn_cont.set_style_flex_main_place(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.PART.MAIN)
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

        if setting.get("enable_qr"): # Scan QR button for text settings
            cambutton = lv.button(settings_screen_detail)
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

    def gotqr_result_callback(self, result):
        print(f"QR capture finished, result: {result}")
        if result.get("result_code"):
            data = result.get("data")
            print(f"Setting textarea data: {data}")
            self.textarea.set_text(data)

    def cambutton_cb(self, event):
        print("cambutton clicked!")
        self.startActivityForResult(Intent(activity_class=CameraApp).putExtra("scanqr_intent", True), self.gotqr_result_callback)

    def save_setting(self, setting):
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

        # Save it
        if setting.get("dont_persist") is not True:
            editor = self.prefs.edit()
            editor.put_string(setting["key"], new_value)
            editor.commit()

        # Update model for UI
        value_label = setting.get("value_label")
        if value_label:
            value_label.set_text(new_value if new_value else "(not set)")

        # self.finish (= back action) should happen before callback, in case it happens to start a new activity
        self.finish()

        # Call changed_callback if set
        changed_callback = setting.get("changed_callback")
        if changed_callback and old_value != new_value:
            print(f"Setting {setting['key']} changed from {old_value} to {new_value}, calling changed_callback...")
            changed_callback(new_value)
