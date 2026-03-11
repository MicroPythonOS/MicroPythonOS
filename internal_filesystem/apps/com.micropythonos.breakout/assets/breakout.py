import lvgl as lv
import time
import mpos.ui
from mpos import Activity, DisplayMetrics, InputManager

import sys
if sys.platform == "esp32":
    import breakout_xtensawin as breakout
else:
    import breakout_x64 as breakout

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

    old_callback = None

    render_next = True
    flush_ready = False
    chunk_in_progress = False
    chunk_waiting = False
    chunk_rows_per = 0
    chunk_total = 0
    chunk_index = 0

    refresh_timer = None

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
        lv.timer_create(self.startit, 4000, None).set_repeat_count(1) # this needs to be delayed, otherwise the whole thing hangs

    def onPause(self, screen):
        if self.refresh_timer:
            self.refresh_timer.delete()
        mpos.ui.task_handler.remove_event_cb(self.drawframe)
        lv.log_register_print_cb(None)
        mpos.ui.main_display._data_bus.register_callback(mpos.ui.main_display._flush_ready_cb)

    def startit(self, arg1=None):
        print("starting it!")
        breakout.init(mpos.ui.main_display._frame_buffer1, self.hor_res, self.ver_res)
        mpos.ui.main_display._data_bus.register_callback(self.flush_ready_cb)
        mpos.ui.task_handler.add_event_cb(self.drawframe, mpos.ui.task_handler.TASK_HANDLER_STARTED)

    def flush_ready_cb(self, arg1=None, arg2=None):
        mpos.ui.main_display._disp_drv.flush_ready() # with this, it hangs, and without it, the device crashes
        self.flush_ready = True

    def move_left(self):
        breakout.move_paddle(-self.paddle_move_step)

    def move_right(self):
        breakout.move_paddle(self.paddle_move_step)

    def move_left_unfocus(self):
        self.unfocus()
        breakout.move_paddle(-self.paddle_move_step)

    def move_right_unfocus(self):
        self.unfocus()
        breakout.move_paddle(self.paddle_move_step)

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
            if focused == self.rightbutton:
                focusgroup.focus_prev()
            elif focused == self.leftbutton:
                focusgroup.focus_next()
            else:
                print("focus isn't on next or previous, leaving it...")

    def send_to_display(self, y_offset=0, rows=None, is_last=True):
        x1 = 0
        x2 = mpos.ui.main_display.get_horizontal_resolution() - 1
        x2 = x2 + mpos.ui.main_display._offset_x
        x1 = x1 + mpos.ui.main_display._offset_x

        if rows is None:
            rows = mpos.ui.main_display.get_vertical_resolution()
        y1 = y_offset
        y2 = y_offset + rows - 1
        y1 = y1 + mpos.ui.main_display._offset_y
        y2 = y2 + mpos.ui.main_display._offset_y

        cmd = mpos.ui.main_display._set_memory_location(x1, y1, x2, y2)
        bytes_needed = rows * mpos.ui.main_display.get_horizontal_resolution() * 2
        data_view = memoryview(mpos.ui.main_display._frame_buffer1)[:bytes_needed]

        tx_last = True
        mpos.ui.main_display._data_bus.tx_color(
            cmd,
            data_view,
            x1, y1, x2, y2,
            mpos.ui.main_display._rotation,
            tx_last,
        )

    def drawframe(self, arg1=None, arg2=None):
        if self.chunk_waiting:
            if self.flush_ready:
                self.flush_ready = False
                self.chunk_waiting = False
                self.chunk_index += 1
                if self.chunk_index >= self.chunk_total:
                    self.chunk_in_progress = False
                    self.render_next = True
                else:
                    self._render_and_send_chunk()
            return

        if self.chunk_in_progress or not self.render_next:
            return

        self.render_next = False

        buffer_len = len(mpos.ui.main_display._frame_buffer1)
        bytes_per_row = self.hor_res * 2
        if bytes_per_row <= 0:
            self.render_next = True
            return

        rows_per_chunk = buffer_len // bytes_per_row
        if rows_per_chunk <= 0:
            self.render_next = True
            return

        if rows_per_chunk >= self.ver_res:
            self.chunk_rows_per = self.ver_res
            self.chunk_index = 0
            self.chunk_total = 1
        else:
            self.chunk_rows_per = rows_per_chunk
            self.chunk_index = 0
            self.chunk_total = (self.ver_res + rows_per_chunk - 1) // rows_per_chunk

        self.chunk_in_progress = True
        self.chunk_waiting = False
        self.flush_ready = False
        self._render_and_send_chunk()

    def _render_and_send_chunk(self):
        if not self.chunk_in_progress:
            return
        if self.chunk_waiting:
            return
        if self.chunk_index >= self.chunk_total:
            self.chunk_in_progress = False
            self.render_next = True
            return

        y_offset = self.chunk_index * self.chunk_rows_per
        rows = min(self.chunk_rows_per, self.ver_res - y_offset)
        advance = (self.chunk_index == 0)
        is_last = (self.chunk_index + 1) == self.chunk_total

        self.chunk_waiting = True
        breakout.render(y_offset, rows, advance)
        self.send_to_display(y_offset, rows, is_last)

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
                    breakout.move_paddle(delta)
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
