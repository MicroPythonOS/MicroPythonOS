import lvgl as lv
from mpos import Activity


class MessageInputActivity(Activity):
    def onCreate(self):
        main_content = lv.obj()
        main_content.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        # main_content.set_size(lv.pct(100), lv.SIZE_CONTENT)
        main_content.set_width(lv.pct(100))
        main_content.set_style_pad_gap(1, 1)

        input_column = lv.obj(main_content)
        input_column.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        input_column.set_size(lv.pct(100), lv.SIZE_CONTENT)
        input_column.set_style_pad_gap(0, 0)

        self.input_textarea = lv.textarea(input_column)
        self.input_textarea.set_placeholder_text("Message ...")
        self.input_textarea.set_one_line(True)
        self.input_textarea.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)

        keyboard_column = lv.obj(main_content)
        keyboard_column.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        keyboard_column.set_width(lv.pct(100))
        keyboard_column.set_style_pad_gap(0, 0)

        self.keyboard = lv.keyboard(keyboard_column)
        self.keyboard.set_textarea(self.input_textarea)
        self.keyboard.add_event_cb(self.keyboard_cb, lv.EVENT.READY, None)

        btn_column = lv.obj(main_content)
        btn_column.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        btn_column.set_size(lv.pct(100), lv.SIZE_CONTENT)
        btn_column.set_style_pad_gap(0, 0)

        cancel_btn = lv.button(btn_column)
        cancel_label = lv.label(cancel_btn)
        cancel_label.set_text("Cancel")
        cancel_label.align(lv.ALIGN.BOTTOM_RIGHT, -2, -2)
        cancel_btn.add_event_cb(self.cancel_clicked, lv.EVENT.CLICKED, None)

        self.setContentView(main_content)

    def keyboard_cb(self, event):
        text = self.input_textarea.get_text()
        self.setResult(result_code="text", data=text)
        self.finish()

    def cancel_clicked(self, event):
        self.setResult(None)
        self.finish()
