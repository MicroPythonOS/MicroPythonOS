import lvgl as lv
from mpos import Activity, AppearanceManager
from mpos import Activity, DisplayMetrics, BuildInfo, DeviceInfo
try:
    import network
except ImportError:
    network = None

class ChannelActivity(Activity):
    def onCreate(self):
        screen = lv.obj()
        screen.set_style_pad_all(0, lv.PART.MAIN)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        self._add_label(screen, 'Current Network settings:', is_header=True)
        if network:
            sta = network.WLAN(network.WLAN.IF_STA)
            self.current_config = sta.config
        else:
            self.current_config={
                'essid': '<no network>',
                'channel': None
            }

        self._add_label(screen, f'channel: {self.current_config["channel"]}')
        self._add_label(screen, f'essid: {self.current_config["essid"]}')

        #
        # self.input_textarea = lv.textarea(screen)
        # self.input_textarea.set_width(lv.pct(100))
        # self.input_textarea.set_placeholder_text("Message ...")
        # self.input_textarea.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
        #
        # keyboard = lv.keyboard(screen)
        # keyboard.set_style_text_font(lv.font_montserrat_20, lv.PART.MAIN)
        # keyboard.set_style_min_height(175, lv.PART.MAIN)
        # AppearanceManager.apply_keyboard_fix(keyboard)
        # keyboard.set_textarea(self.input_textarea)
        # keyboard.add_event_cb(self.keyboard_cb, lv.EVENT.READY, None)

        self.setContentView(screen)

    def keyboard_cb(self, event):
        text = self.input_textarea.get_text()
        self.setResult(result_code="text", data=text)
        self.finish()

    def _add_label(self, parent, text, is_header=False, margin_top=DisplayMetrics.pct_of_height(5)):
        """
        Based on About._add_label()
        """
        label = lv.label(parent)
        label.set_text(text)

        if is_header:
            primary_color = lv.theme_get_color_primary(None)
            label.set_style_text_color(primary_color, lv.PART.MAIN)
            label.set_style_text_font(lv.font_montserrat_14, lv.PART.MAIN)
            label.set_style_margin_top(margin_top, lv.PART.MAIN)
            label.set_style_margin_bottom(DisplayMetrics.pct_of_height(2), lv.PART.MAIN)
        else:
            label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
            label.set_style_margin_bottom(2, lv.PART.MAIN)
        return label
