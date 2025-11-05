import time
import _thread

from mpos.apps import Activity
import mpos.ui

indev_error_x = 160
indev_error_y = 120

DARKPINK = lv.color_hex(0xEC048C)

class Benchmark(Activity):

    hor_res = 0
    ver_res = 0
    layer = None
    fps_buffer = [0] # Buffer to store FPS

    # Widgets:
    canvas = None

    def onCreate(self):
        screen = lv.obj()
        self.canvas = lv.canvas(screen)
        disp = lv.display_get_default()
        self.hor_res = disp.get_horizontal_resolution()
        self.ver_res = disp.get_vertical_resolution()
        self.canvas.set_size(self.hor_res, self.ver_res)
        self.canvas.set_style_bg_color(lv.color_white(), 0)
        buffer = bytearray(self.hor_res * self.ver_res * 4)
        self.canvas.set_buffer(buffer, self.hor_res, self.ver_res, lv.COLOR_FORMAT.NATIVE)
        self.canvas.fill_bg(lv.color_white(), lv.OPA.COVER)
        self.layer = lv.layer_t()
        self.canvas.init_layer(self.layer)
        self.canvas.add_flag(lv.obj.FLAG.CLICKABLE)
        self.canvas.add_event_cb(self.touch_cb, lv.EVENT.ALL, None)
        self.setContentView(screen)

    def onResume(self, screen):
        #lv.perf_monitor_create(10, NULL, NULL)
        lv.log_register_print_cb(self.log_callback)
        #try:
        #    _thread.stack_size(mpos.apps.good_stack_size())
        #    _thread.start_new_thread(self.runall, ())
        #except Exception as e:
        #    print("Could not start thread: ", e)
    
    def onStop(self, screen):
        super().onStop(screen)
        lv.log_register_print_cb(None)

    def touch_cb(self, event):
        event_code=event.get_code()
        #print(f"lv_event_t: code={event_code}")
        if event_code == lv.EVENT.PRESSING:
            self.runall()

    # Custom log callback to capture FPS
    def log_callback(self,level, log_str):
        # Convert log_str to string if it's a bytes object
        log_str = log_str.decode() if isinstance(log_str, bytes) else log_str
        # Optional: Print for debugging
        #print(f"Level: {level}, Log: {log_str}")
        # Log message format: "sysmon: 25 FPS (refr_cnt: 8 | redraw_cnt: 1), ..."
        if "sysmon:" in log_str and "FPS" in log_str:
            try:
                # Extract FPS value (e.g., "25" from "sysmon: 25 FPS ...")
                fps_part = log_str.split("FPS")[0].split("sysmon:")[1].strip()
                fps = int(fps_part)
                print("Current FPS:", fps)
                self.fps_buffer[0] = fps
            except (IndexError, ValueError):
                pass

    def runall(self):
        print("Waiting a bit before starting...")
        time.sleep(1) # wait for top bar to go away
        for _ in range(5):
            self.draw_n_squares(10000)

    def draw_n_squares(self, n):
        start = time.ticks_ms()
        for _ in range(n):
            self.draw_rect(100, 100)
        end = time.ticks_ms()
        diff = end - start
        print(f"draw_rect x {n} took {diff}ms")
        start = time.ticks_ms()
        for _ in range(n):
            self.draw_rect_viper(100, 100)
        end = time.ticks_ms()
        diff = end - start
        print(f"draw_rect_viper x {n} took {diff}ms")

    def draw_rect(self, x: int, y: int):
        draw_dsc = lv.draw_rect_dsc_t()
        lv.draw_rect_dsc_t.init(draw_dsc)
        draw_dsc.bg_color = lv.color_hex(0xffaaaa)
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

    @micropython.viper # make it with native compilation
    def draw_rect_viper(self, x: int, y: int):
        draw_dsc = lv.draw_rect_dsc_t()
        lv.draw_rect_dsc_t.init(draw_dsc)
        draw_dsc.bg_color = lv.color_hex(0xffaaaa)
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
