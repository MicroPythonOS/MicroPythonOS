import lvgl as lv
from mpos import Activity, AppearanceManager


class MessageInputActivity(Activity):
    def onCreate(self):
        screen = lv.obj()
        screen.set_style_pad_all(0, lv.PART.MAIN)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        self.input_textarea = lv.textarea(screen)
        self.input_textarea.set_width(lv.pct(100))
        self.input_textarea.set_one_line(True)
        self.input_textarea.set_placeholder_text("Message ...")
        self.input_textarea.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)

        keyboard = lv.keyboard(screen)
        keyboard.set_style_text_font(lv.font_montserrat_20, lv.PART.MAIN)
        keyboard.set_style_min_height(175, lv.PART.MAIN)
        AppearanceManager.apply_keyboard_fix(keyboard)
        keyboard.set_textarea(self.input_textarea)
        keyboard.add_event_cb(self.keyboard_cb, lv.EVENT.READY, None)

        self.setContentView(screen)

    def keyboard_cb(self, event):
        text = self.input_textarea.get_text()
        self.setResult(result_code="text", data=text)
        self.finish()
