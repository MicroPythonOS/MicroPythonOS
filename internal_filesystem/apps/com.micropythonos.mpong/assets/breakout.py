# This gets just 7.5 FPS on actual ESP32S3 hardware
# Probably because the double buffer copies.
# With a direct buffer, it's still only 10 FPS. (and flickering buttons on black screen)
# direct framebuffer + without self.canvas.invalidate() and self.canvas.center(), it's still only 13.5 FPS (and black screen)
# AHA! with a send_to_display() it is running at 21.5 FPS but with heavy flicker
# adding a wait for the render of 10ms gives a non-flicker 17.5 FPS

import lvgl as lv

import time

import mpos.ui
from mpos import Activity, DisplayMetrics, InputManager

import sys
if sys.platform == "esp32":
    import mpong_xtensawin as mpong
else:
    import mpong_x64 as mpong

class Breakout(Activity):

    hor_res = 0
    ver_res = 0
    paddle_move_step = None
    layer = None
    buffer = None
    touch_active = False
    touch_last_x = None
    last_fps = 0
    average_fps = 0

    # Widgets:
    screen = None
    canvas = None
    leftbutton = None
    playbutton = None
    rightbutton = None

    def onCreate(self):
        self.screen = lv.obj()
        self.screen.add_flag(lv.obj.FLAG.CLICKABLE)
        self.screen.add_event_cb(self.touch_cb, lv.EVENT.ALL, None)

        d = lv.display_get_default()
        self.hor_res = d.get_horizontal_resolution()
        self.paddle_move_step = round(self.hor_res/16)
        self.ver_res = d.get_vertical_resolution()

        '''
        self.canvas = lv.canvas(self.screen)
        self.canvas.set_size(self.hor_res, self.ver_res)
        #self.buffer = bytearray(self.hor_res * self.ver_res * 2)
        #self.canvas.set_buffer(self.buffer, self.hor_res, self.ver_res, lv.COLOR_FORMAT.NATIVE)
        #self.canvas.set_buffer(mpos.ui.main_display._frame_buffer1, self.hor_res, self.ver_res, lv.COLOR_FORMAT.NATIVE)
        #self.canvas.add_flag(lv.obj.FLAG.CLICKABLE)
        #self.canvas.add_event_cb(self.touch_cb, lv.EVENT.ALL, None)
        self.layer = lv.layer_t()
        self.canvas.init_layer(self.layer)
        '''

        self.leftbutton = lv.button(self.screen)
        self.leftbutton.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        leftlabel = lv.label(self.leftbutton)
        leftlabel.set_text("<")
        self.leftbutton.add_event_cb(lambda e: self.move_left_unfocus(),lv.EVENT.FOCUSED,None)
        self.leftbutton.add_event_cb(lambda e: self.move_left(),lv.EVENT.CLICKED,None)

        # Invisible button, just for defocusing the left and right buttons:
        self.play_button = lv.button(self.screen)
        self.play_button.align(lv.ALIGN.BOTTOM_MID,0,0)
        self.play_button.set_size(1,1)
        self.play_button.set_style_opa(lv.OPA.TRANSP, lv.PART.MAIN)

        self.rightbutton = lv.button(self.screen)
        self.rightbutton.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        rightlabel = lv.label(self.rightbutton)
        rightlabel.set_text(">")
        self.rightbutton.add_event_cb(lambda e: self.move_right_unfocus(),lv.EVENT.FOCUSED,None)
        self.rightbutton.add_event_cb(lambda e: self.move_right(),lv.EVENT.CLICKED,None)

        self.setContentView(self.screen)

    def onResume(self, screen):
        lv.log_register_print_cb(self.log_callback)
        #mpong.init(self.buffer, self.hor_res, self.ver_res)
        mpong.init(mpos.ui.main_display._frame_buffer1, self.hor_res, self.ver_res) # stays black

        #self.refresh_timer = lv.timer_create(self.run_mpong, 16, None) # max 1000ms/60fps = 16ms/frame
        self.refresh_timer = lv.timer_create(self.run_mpong, 33, None) # max 1000ms/30fps = 33ms/frame
        #mpos.ui.task_handler.add_event_cb(self.run_mpong, mpos.ui.task_handler.TASK_HANDLER_STARTED)
        #mpos.ui.task_handler.add_event_cb(self.run_mpong, mpos.ui.task_handler.TASK_HANDLER_FINISHED)

        #mpos.ui.main_display.delete_refr_timer() # how to enable after? also it doesnt help

    def onPause(self, screen):
        if self.refresh_timer:
            self.refresh_timer.delete()
        lv.log_register_print_cb(None)

    def move_left(self):
        mpong.move_paddle(-self.paddle_move_step)

    def move_right(self):
        mpong.move_paddle(self.paddle_move_step)

    def move_left_unfocus(self):
        self.unfocus()
        mpong.move_paddle(-self.paddle_move_step)

    def move_right_unfocus(self):
        self.unfocus()
        mpong.move_paddle(self.paddle_move_step)

    # This only works with the PREV/pageup and NEXT/pagedown buttons,
    # because the focus_direction handling of the arrow keys uses a trick to move focus (focus_next)
    # which conflicts with the focus_next below...
    def unfocus(self):
        focusgroup = lv.group_get_default()
        if not focusgroup:
            print("WARNING: imageview.py could not get default focus group")
            return
        focused = focusgroup.get_focused()
        if focused:
            #print(f"got focus button: {focused}")
            #label = focused.get_child(0)
            #print(f"got label for button: {label.get_text()}")
            #focused.remove_state(lv.STATE.FOCUSED) # this doesn't seem to work to remove focus
            #print("checking which button is focused")
            if focused == self.rightbutton:
                #print("next is focused")
                focusgroup.focus_prev()
            elif focused == self.leftbutton:
                #print("prev is focused")
                focusgroup.focus_next()
            else:
                print("focus isn't on next or previous, leaving it...")

    def send_to_display(self):
        # full-screen area
        x1, y1 = 0, 0
        x2 = mpos.ui.main_display.get_horizontal_resolution() - 1
        x2 = x2 + mpos.ui.main_display._offset_x
        x1 = x1 + mpos.ui.main_display._offset_x
        y2 = mpos.ui.main_display.get_vertical_resolution() - 1
        y2 = y2 + mpos.ui.main_display._offset_y
        y1 = y1 + mpos.ui.main_display._offset_y

        cmd = mpos.ui.main_display._set_memory_location(x1, y1, x2, y2)
        data_view = mpos.ui.main_display._frame_buffer1

        mpos.ui.main_display._data_bus.tx_color(
            cmd,
            data_view,
            x1, y1, x2, y2,
            mpos.ui.main_display._rotation,
            True,
        )

    def run_mpong(self, arg1=None, arg2=None):
        mpong.render()
        #self.play_button.set_style_opa(lv.OPA.TRANSP, lv.PART.MAIN) # works to force refresh on desktop but not esp32
        #self.screen.invalidate()
        #lv.refr_now(None)
        #self.canvas.invalidate() # force redraw
        #self.canvas.center()
        #self.canvas.refre
        #self.screen.invalidate()
        #self.screen.center()
        #mpong.render()
        '''
        import lvgl as lv
        area = lv.area_t()
        area.x1 = 0
        area.y1 = 0
        area.x2 = 170
        area.y2 = 170
        import mpos.ui
        mpos.ui.main_display._flush_cb(None, area, mpos.ui.main_display._frame_buffer1) # color_p should be pointer, not memoryview
        '''
        self.send_to_display()
        time.sleep_ms(10) # give it time to flush, otherwise there's heavy flicker. 5ms is fine!

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

    average_samples = 20
    fps_buffer = [0.0] * average_samples
    fps_index = 0
    fps_sum = 0.0
    fps_count = 0  # Number of valid samples (0 to average_samples)
    def moving_average(self, value):
        if self.fps_count == self.average_samples:
            self.fps_sum -= self.fps_buffer[self.fps_index]
        else:
            self.fps_count += 1
        self.fps_sum += value
        self.fps_buffer[self.fps_index] = value
        self.fps_index = (self.fps_index + 1) % self.average_samples
        return self.fps_sum / self.fps_count

    # Custom log callback to capture FPS
    def log_callback(self, level, log_str):
        log_str = log_str.decode() if isinstance(log_str, bytes) else log_str
        if "sysmon:" in log_str and "FPS" in log_str:
            try:
                fps_part = log_str.split("FPS")[0].split("sysmon:")[1].strip()
                self.last_fps = int(fps_part)
                self.average_fps = self.moving_average(self.last_fps)
                print(f"Current FPS: {self.last_fps} - Average FPS: {self.average_fps}")
            except (IndexError, ValueError):
                pass
