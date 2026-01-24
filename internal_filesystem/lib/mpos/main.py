import task_handler
import _thread
import lvgl as lv

import mpos.apps
import mpos.ui
import mpos.ui.topmenu

from mpos import AppearanceManager, DisplayMetrics, PackageManager, SharedPreferences, TaskManager, DeviceInfo

# White text on black logo works (for dark mode) and can be inverted (for light mode)
logo_white = "M:builtin/res/mipmap-mdpi/MicroPythonOS-logo-white-long-w296.png" # from the MPOS-logo repo

# Black text on transparent logo works (for light mode) but can't be inverted (for dark mode)
# Even when trying different blend modes (SUBTRACTIVE, ADDITIVE, MULTIPLY)
# Even when it's on a white (instead of transparent) background
#logo_black = "M:builtin/res/mipmap-mdpi/MicroPythonOS-logo-black-long-w240.png"


def init_rootscreen():
    """Initialize the root screen and set display metrics."""
    screen = lv.screen_active()
    disp = screen.get_display()
    width = disp.get_horizontal_resolution()
    height = disp.get_vertical_resolution()
    dpi = disp.get_dpi()
    
    # Initialize DisplayMetrics with actual display values
    DisplayMetrics.set_resolution(width, height)
    DisplayMetrics.set_dpi(dpi)
    
    print(f"init_rootscreen set resolution to {width}x{height} at {dpi} DPI")
    
    try:
        img = lv.image(screen)
        img.set_src(logo_white)
        img.set_blend_mode(lv.BLEND_MODE.DIFFERENCE)
        img.center()
    except Exception as e:  # if image loading fails
        print(f"ERROR: logo image failed, LVGL will be in a bad state and the UI will hang: {e}")
        import sys
        sys.print_exception(e)
        print("Trying to fall back to a simple text-based 'logo' but it won't showup because the UI broke...")
        label = lv.label(screen)
        label.set_text("MicroPythonOS")
        label.set_style_text_font(lv.font_montserrat_20, lv.PART.MAIN)
        label.center()

def detect_board():
    import sys
    if sys.platform == "linux" or sys.platform == "darwin": # linux and macOS
        return "linux"
    elif sys.platform == "esp32":
        from machine import Pin, I2C
        i2c0 = I2C(0, sda=Pin(48), scl=Pin(47))
        if {0x15, 0x6B} <= set(i2c0.scan()): # touch screen and IMU (at least, possibly more)
            return "waveshare_esp32_s3_touch_lcd_2"
        else:
            i2c0 = I2C(0, sda=Pin(9), scl=Pin(18))
            if {0x6A} <= set(i2c0.scan()): # IMU (plus a few others, to be added later, but this should work)
                return "fri3d_2026"
            else: # if {0x6B} <= set(i2c0.scan()): # IMU (plus possibly the Communicator's LANA TNY at 0x38)
                return "fri3d_2024"


board = detect_board()
print(f"Initializing {board} hardware")
DeviceInfo.set_hardware_id(board)
__import__(f"mpos.board.{board}")

# Allow LVGL M:/path/to/file or M:relative/path/to/file to work for image set_src etc
import mpos.fs_driver
fs_drv = lv.fs_drv_t()
mpos.fs_driver.fs_register(fs_drv, 'M')

# Needed to load the logo from storage:
try:
    import freezefs_mount_builtin
except Exception as e:
    # This will throw an exception if there is already a "/builtin" folder present
    print("main.py: WARNING: could not import/run freezefs_mount_builtin: ", e)

prefs = SharedPreferences("com.micropythonos.settings")

AppearanceManager.init(prefs)
init_rootscreen() # shows the boot logo
mpos.ui.topmenu.create_notification_bar()
mpos.ui.topmenu.create_drawer()
mpos.ui.handle_back_swipe()
mpos.ui.handle_top_swipe()

# Clear top menu, notification bar, swipe back and swipe down buttons
# Ideally, these would be stored in a different focusgroup that is used when the user opens the drawer
focusgroup = lv.group_get_default()
if focusgroup: # on esp32 this may not be set
    focusgroup.remove_all_objs() #  might be better to save and restore the group for "back" actions

# Custom exception handler that does not deinit() the TaskHandler because then the UI hangs:
def custom_exception_handler(e):
    print(f"TaskHandler's custom_exception_handler called: {e}")
    import sys
    sys.print_exception(e)  # NOQA
    # No need to deinit() and re-init LVGL:
    #mpos.ui.task_handler.deinit() # default task handler does this, but then things hang
    # otherwise it does focus_next and then crashes while doing lv.deinit()
    #focusgroup.remove_all_objs()
    #focusgroup.delete()
    #lv.deinit()

import sys
if sys.platform == "esp32":
    mpos.ui.task_handler = task_handler.TaskHandler(duration=5, exception_hook=custom_exception_handler) # 1ms gives highest framerate on esp32-s3's but might have side effects?
else:
    mpos.ui.task_handler = task_handler.TaskHandler(duration=5, exception_hook=custom_exception_handler) # 5ms is recommended for MicroPython+LVGL on desktop (less results in lower framerate)

# Convenient for apps to be able to access these:
mpos.ui.task_handler.TASK_HANDLER_STARTED = task_handler.TASK_HANDLER_STARTED
mpos.ui.task_handler.TASK_HANDLER_FINISHED = task_handler.TASK_HANDLER_FINISHED

try:
    from mpos.net.wifi_service import WifiService
    _thread.stack_size(TaskManager.good_stack_size())
    _thread.start_new_thread(WifiService.auto_connect, ())
except Exception as e:
    print(f"Couldn't start WifiService.auto_connect thread because: {e}")

# Start launcher so it's always at bottom of stack
launcher_app = PackageManager.get_launcher()
started_launcher = mpos.apps.start_app(launcher_app.fullname)
# Then start auto_start_app if configured
auto_start_app = prefs.get_string("auto_start_app", None)
if auto_start_app and launcher_app.fullname != auto_start_app:
    result = mpos.apps.start_app(auto_start_app)
    if result is not True:
        print(f"WARNING: could not run {auto_start_app} app")

# Create limited aiorepl because it's better than nothing:
import aiorepl
async def asyncio_repl():
    print("Starting very limited asyncio REPL task. To stop all asyncio tasks and go to real REPL, do: import mpos ; mpos.TaskManager.stop()")
    await aiorepl.task()
TaskManager.create_task(asyncio_repl()) # only gets started after TaskManager.start()

async def ota_rollback_cancel():
    try:
        from esp32 import Partition
        Partition.mark_app_valid_cancel_rollback()
    except Exception as e:
        print("main.py: warning: could not mark this update as valid:", e)

if not started_launcher:
    print(f"WARNING: launcher {launcher_app} failed to start, not cancelling OTA update rollback")
else:
    TaskManager.create_task(ota_rollback_cancel()) # only gets started after TaskManager.start()

try:
    TaskManager.start() # do this at the end because it doesn't return
except KeyboardInterrupt as k:
    print(f"TaskManager.start() got KeyboardInterrupt, falling back to REPL shell...") # only works if no aiorepl is running
except Exception as e:
    print(f"TaskManager.start() got exception: {e}")
