import unittest

import sdl_display
import lcd_bus
import lvgl as lv
import mpos.ui
import task_handler
import mpos.apps
import mpos.ui.topmenu
import mpos.config
from mpos.ui.display import init_rootscreen

class TestStartApp(unittest.TestCase):

    def __init__(self):
        
        TFT_HOR_RES=320
        TFT_VER_RES=240
        
        bus = lcd_bus.SDLBus(flags=0)
        buf1 = bus.allocate_framebuffer(320 * 240 * 2, 0)
        display = sdl_display.SDLDisplay(data_bus=bus,display_width=TFT_HOR_RES,display_height=TFT_VER_RES,frame_buffer1=buf1,color_space=lv.COLOR_FORMAT.RGB565)
        display.init()
        init_rootscreen()
        mpos.ui.topmenu.create_notification_bar()
        mpos.ui.topmenu.create_drawer(display)
        mpos.ui.th = task_handler.TaskHandler(duration=5) # 5ms is recommended for MicroPython+LVGL on desktop (less results in lower framerate)


    def test_normal(self):
        self.assertTrue(mpos.apps.start_app("com.micropythonos.launcher"), "com.micropythonos.launcher should start")

    def test_nonexistent(self):
        self.assertFalse(mpos.apps.start_app("com.micropythonos.nonexistent"), "com.micropythonos.nonexistent should not start")

    def test_restart_launcher(self):
        self.assertTrue(mpos.apps.restart_launcher(), "restart_launcher() should succeed")
