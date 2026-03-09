import lvgl as lv
from mpos import Activity, DisplayMetrics, InputManager

indev_error_x = 160
indev_error_y = 120

DARKPINK = lv.color_hex(0xEC048C)

import sys
if sys.platform == "esp32":
    import mpong_xtensawin as mpong
else:
    import mpong_x64 as mpong

class MPong(Activity):

    hor_res = 0
    ver_res = 0
    paddle_move_step = None
    layer = None
    buffer = None
    touch_active = False
    touch_last_x = None

    # Widgets:
    screen = None
    canvas = None
    leftbutton = None
    rightbutton = None

    def onCreate(self):
        self.screen = lv.obj()
        self.canvas = lv.canvas(self.screen)
        d = lv.display_get_default()
        self.hor_res = d.get_horizontal_resolution()
        self.paddle_move_step = round(self.hor_res/16)
        self.ver_res = d.get_vertical_resolution()
        self.canvas.set_size(self.hor_res, self.ver_res)
        self.buffer = bytearray(self.hor_res * self.ver_res * 2)
        self.canvas.set_buffer(self.buffer, self.hor_res, self.ver_res, lv.COLOR_FORMAT.NATIVE)
        self.canvas.add_flag(lv.obj.FLAG.CLICKABLE)
        self.canvas.add_event_cb(self.touch_cb, lv.EVENT.ALL, None)
        self.layer = lv.layer_t()
        self.canvas.init_layer(self.layer)

        self.leftbutton = lv.button(self.screen)
        self.leftbutton.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        leftlabel = lv.label(self.leftbutton)
        leftlabel.set_text("<")
        self.leftbutton.add_event_cb(lambda e: self.move_left(),lv.EVENT.FOCUSED,None)
        self.leftbutton.add_event_cb(lambda e: self.move_left(),lv.EVENT.CLICKED,None)

        self.rightbutton = lv.button(self.screen)
        self.rightbutton.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        rightlabel = lv.label(self.rightbutton)
        rightlabel.set_text(">")
        self.rightbutton.add_event_cb(lambda e: self.move_right(),lv.EVENT.FOCUSED,None)
        self.rightbutton.add_event_cb(lambda e: self.move_right(),lv.EVENT.CLICKED,None)

        self.setContentView(self.screen)

    def onResume(self, screen):
        mpong.init(self.buffer, self.hor_res, self.ver_res)
        self.refresh_timer = lv.timer_create(self.run_mpong, 10, None)

    def onPause(self, screen):
        if self.refresh_timer:
            self.refresh_timer.delete()

    def move_left(self):
        mpong.move_paddle(-self.paddle_move_step)

    def move_right(self):
        mpong.move_paddle(self.paddle_move_step)

    def run_mpong(self, timer=None):
        mpong.render()
        self.canvas.invalidate() # force redraw

    def touch_cb(self, event):
        event_code = event.get_code()
        if event_code == lv.EVENT.PRESSED:
            x, y = InputManager.pointer_xy()
            self.touch_active = True
            self.touch_last_x = x
            return

        if event_code == lv.EVENT.PRESSING:
            if not self.touch_active:
                x, y = InputManager.pointer_xy()
                self.touch_active = True
                self.touch_last_x = x
                return
            x, y = InputManager.pointer_xy()
            if self.touch_last_x is not None:
                delta = x - self.touch_last_x
                if delta:
                    mpong.move_paddle(delta)
            self.touch_last_x = x
            return

        if event_code == lv.EVENT.RELEASED:
            self.touch_active = False
            self.touch_last_x = None
            return
