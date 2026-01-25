import lvgl as lv
from mpos import Activity, DisplayMetrics

indev_error_x = 160
indev_error_y = 120

DARKPINK = lv.color_hex(0xEC048C)

class Draw(Activity):

    hor_res = 0
    ver_res = 0
    layer = None

    # Widgets:
    canvas = None

    def onCreate(self):
        screen = lv.obj()
        self.canvas = lv.canvas(screen)
        d = lv.display_get_default()
        self.hor_res = d.get_horizontal_resolution()
        self.ver_res = d.get_vertical_resolution()
        self.canvas.set_size(self.hor_res, self.ver_res)
        self.canvas.set_style_bg_color(lv.color_white(), 0)
        buffer = bytearray(self.hor_res * self.ver_res * 4)
        self.canvas.set_buffer(buffer, self.hor_res, self.ver_res, lv.COLOR_FORMAT.NATIVE)
        self.canvas.fill_bg(lv.color_white(), lv.OPA.COVER)
        self.canvas.add_flag(lv.obj.FLAG.CLICKABLE)
        self.canvas.add_event_cb(self.touch_cb, lv.EVENT.ALL, None)
        self.layer = lv.layer_t()
        self.canvas.init_layer(self.layer)
        self.setContentView(screen)

    def touch_cb(self, event):
        event_code=event.get_code()
        if event_code not in [19,23,25,26,27,28,29,30,49]:
            #name = ui.get_event_name(event_code)
            #print(f"lv_event_t: code={event_code}, name={name}") # target={event.get_target()}, user_data={event.get_user_data()}, param={event.get_param()}
            if event_code == lv.EVENT.PRESSING: # this is probably enough
            #if event_code in [lv.EVENT.PRESSED, lv.EVENT.PRESSING, lv.EVENT.LONG_PRESSED, lv.EVENT.LONG_PRESSED_REPEAT]:
                x, y = DisplayMetrics.pointer_xy()
                #canvas.set_px(x,y,lv.color_black(),lv.OPA.COVER) # draw a tiny point
                self.draw_rect(x,y)
                #self.draw_line(x,y)
                return

    def draw_line(self, x, y):
        dsc = lv.draw_line_dsc_t()
        lv.draw_line_dsc_t.init(dsc)
        dsc.color = DARKPINK
        dsc.width = 4
        dsc.round_end = 1
        dsc.round_start = 1
        dsc.p1 = lv.point_precise_t()
        dsc.p1.x = x
        dsc.p1.y = y
        dsc.p2 = lv.point_precise_t()
        dsc.p2.x = 100
        dsc.p2.y = 200
        lv.draw_line(self.layer,dsc)
        self.canvas.finish_layer(self.layer)

    # @micropython.viper # "invalid micropython decorator" on macOS
    def draw_rect(self, x: int, y: int):
        draw_dsc = lv.draw_rect_dsc_t()
        lv.draw_rect_dsc_t.init(draw_dsc)
        draw_dsc.bg_color = lv.color_hex(0xffaaaa)
        draw_dsc.radius = lv.RADIUS_CIRCLE
        draw_dsc.border_color = lv.color_hex(0xff5555)
        draw_dsc.border_width = 2
        draw_dsc.outline_color = lv.color_hex(0xff0000)
        draw_dsc.outline_pad = 3
        draw_dsc.outline_width = 2
        a = lv.area_t()
        a.x1 = x-10
        a.y1 = y-10
        a.x2 = x+10
        a.y2 = y+10
        lv.draw_rect(self.layer, draw_dsc, a)
        self.canvas.finish_layer(self.layer)
