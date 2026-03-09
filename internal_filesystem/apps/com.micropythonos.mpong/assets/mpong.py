import lvgl as lv
from mpos import Activity, DisplayMetrics, InputManager

indev_error_x = 160
indev_error_y = 120

DARKPINK = lv.color_hex(0xEC048C)

import sys
if sys.platform == "esp32":
    import mpong_esp32 as mpong
else:
    import mpong_amd64 as mpong

class MPong(Activity):

    hor_res = 0
    ver_res = 0
    layer = None
    buffer = None

    # Widgets:
    screen = None
    canvas = None

    def onCreate(self):
        self.screen = lv.obj()
        self.canvas = lv.canvas(self.screen)
        d = lv.display_get_default()
        self.hor_res = d.get_horizontal_resolution()
        self.ver_res = d.get_vertical_resolution()
        self.canvas.set_size(self.hor_res, self.ver_res)
        #self.canvas.set_style_bg_color(lv.color_white(), lv.PART.MAIN)
        self.buffer = bytearray(self.hor_res * self.ver_res * 2)
        self.canvas.set_buffer(self.buffer, self.hor_res, self.ver_res, lv.COLOR_FORMAT.NATIVE)
        #self.canvas.fill_bg(lv.color_white(), lv.OPA.COVER)
        self.canvas.add_flag(lv.obj.FLAG.CLICKABLE)
        self.canvas.add_event_cb(self.touch_cb, lv.EVENT.ALL, None)
        self.layer = lv.layer_t()
        self.canvas.init_layer(self.layer)
        self.setContentView(self.screen)

    def onResume(self, screen):
        mpong.init(self.buffer, self.hor_res, self.ver_res)
        self.refresh_timer = lv.timer_create(self.run_mpong, 10, None)

    def onPause(self, screen):
        print("stopping it!")
        if self.refresh_timer:
            self.refresh_timer.delete()

    def run_mpong(self, timer=None):
        mpong.render()
        self.canvas.invalidate() # force redraw

    def touch_cb(self, event):
        event_code=event.get_code()
        if event_code not in [19,23,25,26,27,28,29,30,49]:
            if event_code == lv.EVENT.PRESSING: # this is probably enough
                x, y = InputManager.pointer_xy()
                mpong.move_paddle(-10)
                return
