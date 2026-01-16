import lvgl as lv

from mpos import Activity, min_resolution

class FullscreenQR(Activity):
    # No __init__() so super.__init__() will be called automatically

    def onCreate(self):
        receive_qr_data = self.getIntent().extras.get("receive_qr_data")
        qr_screen = lv.obj()
        qr_screen.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        qr_screen.set_scroll_dir(lv.DIR.NONE)
        qr_screen.add_event_cb(lambda e: self.finish(),lv.EVENT.CLICKED,None)
        big_receive_qr = lv.qrcode(qr_screen)
        big_receive_qr.set_size(min_resolution())
        big_receive_qr.set_dark_color(lv.color_black())
        big_receive_qr.set_light_color(lv.color_white())
        big_receive_qr.center()
        big_receive_qr.set_style_border_color(lv.color_white(), 0)
        big_receive_qr.set_style_border_width(0, 0);
        big_receive_qr.update(receive_qr_data, len(receive_qr_data))
        self.setContentView(qr_screen)
