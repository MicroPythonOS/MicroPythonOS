import task_handler
import _thread
import lvgl as lv
import mpos
import mpos.apps
import mpos.config
import mpos.ui
import mpos.ui.topmenu
from mpos.ui.display import init_rootscreen
from mpos.content.package_manager import PackageManager

# Auto-detect and initialize hardware
import sys
if sys.platform == "linux" or sys.platform == "darwin": # linux and macOS
    board = "linux"
elif sys.platform == "esp32":
    from machine import Pin, I2C
    i2c0 = I2C(0, sda=Pin(48), scl=Pin(47))
    if {0x15, 0x6B} <= set(i2c0.scan()): # touch screen and IMU (at least, possibly more)
        board = "waveshare_esp32_s3_touch_lcd_2"
    else:
        i2c0 = I2C(0, sda=Pin(9), scl=Pin(18))
        if {0x6B} <= set(i2c0.scan()): # IMU (plus possibly the Communicator's LANA TNY at 0x38)
            board = "fri3d_2024"
        else:
            print("Unable to identify board, defaulting...")
            board = "fri3d_2024" # default fallback

print(f"Initializing {board} hardware")
import mpos.info
mpos.info.set_hardware_id(board)
__import__(f"mpos.board.{board}")

# Allow LVGL M:/path/to/file or M:relative/path/to/file to work for image set_src etc
import mpos.fs_driver
fs_drv = lv.fs_drv_t()
mpos.fs_driver.fs_register(fs_drv, 'M')

prefs = mpos.config.SharedPreferences("com.micropythonos.settings")

mpos.ui.set_theme(prefs)
init_rootscreen()
mpos.ui.topmenu.create_notification_bar()
mpos.ui.topmenu.create_drawer(mpos.ui.display)
mpos.ui.handle_back_swipe()
mpos.ui.handle_top_swipe()

# Clear top menu, notification bar, swipe back and swipe down buttons
# Ideally, these would be stored in a different focusgroup that is used when the user opens the drawer
focusgroup = lv.group_get_default()
if focusgroup: # on esp32 this may not be set
    focusgroup.remove_all_objs() #  might be better to save and restore the group for "back" actions

# Can be passed to TaskHandler, currently unused:
def custom_exception_handler(e):
    print(f"custom_exception_handler called: {e}")
    mpos.ui.task_handler.deinit()
    # otherwise it does focus_next and then crashes while doing lv.deinit()
    focusgroup.remove_all_objs()
    focusgroup.delete()
    lv.deinit()

import sys
if sys.platform == "esp32":
    mpos.ui.task_handler = task_handler.TaskHandler(duration=5) # 1ms gives highest framerate on esp32-s3's but might have side effects?
else:
    mpos.ui.task_handler = task_handler.TaskHandler(duration=5) # 5ms is recommended for MicroPython+LVGL on desktop (less results in lower framerate)

try:
    import freezefs_mount_builtin
except Exception as e:
    # This will throw an exception if there is already a "/builtin" folder present
    print("main.py: WARNING: could not import/run freezefs_mount_builtin: ", e)

try:
    from mpos.net.wifi_service import WifiService
    _thread.stack_size(mpos.apps.good_stack_size())
    _thread.start_new_thread(WifiService.auto_connect, ())
except Exception as e:
    print(f"Couldn't start WifiService.auto_connect thread because: {e}")

# Start launcher so it's always at bottom of stack
launcher_app = PackageManager.get_launcher()
started_launcher = mpos.apps.start_app(launcher_app.fullname)
# Then start auto_start_app if configured
auto_start_app = prefs.get_string("auto_start_app", None)
if auto_start_app and launcher_app.fullname != auto_start_app:
    mpos.apps.start_app(auto_start_app)

# Create limited aiorepl because it's better than nothing:
import aiorepl
print("Starting very limited asyncio REPL task. Use sys.exit() to stop all asyncio tasks and go to real REPL...")
mpos.TaskManager.create_task(aiorepl.task()) # only gets started when mpos.TaskManager() is created

async def ota_rollback_cancel():
    try:
        import ota.rollback
        ota.rollback.cancel()
    except Exception as e:
        print("main.py: warning: could not mark this update as valid:", e)

if not started_launcher:
    print(f"WARNING: launcher {launcher_app} failed to start, not cancelling OTA update rollback")
else:
    mpos.TaskManager.create_task(ota_rollback_cancel()) # only gets started when mpos.TaskManager() is created 

while True:
    try:
        mpos.TaskManager() # do this at the end because it doesn't return
    except KeyboardInterrupt as k:
        print(f"mpos.TaskManager() got KeyboardInterrupt, falling back to REPL shell...") # only works if no aiorepl is running
        break
    except Exception as e:
        print(f"mpos.TaskManager() got exception: {e}")
        print("Restarting mpos.TaskManager() after 10 seconds...")
        import time
        time.sleep(10)
