import task_handler
import _thread
import lvgl as lv

import mpos.ui
import mpos.ui.topmenu

from mpos import AppearanceManager, DisplayMetrics, AppManager, SharedPreferences, TaskManager, DeviceInfo

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
    
    # Show logo
    img = lv.image(screen)
    img.set_src("M:builtin/res/mipmap-mdpi/MicroPythonOS-logo-white-long-w296.png") # from the MPOS-logo repo
    img.set_blend_mode(lv.BLEND_MODE.DIFFERENCE)
    img.center()

def detect_board():
    import sys
    if sys.platform == "linux" or sys.platform == "darwin": # linux and macOS
        return "linux"
    elif sys.platform == "esp32":
        # Force MaTouch for ESP32-S3 with 8MB PSRAM
        # This bypasses unreliable GT911 touch controller detection at boot
        try:
            import esp32
            if hasattr(esp32, 'spiram_size'):
                psram_size = esp32.spiram_size()
                print(f"Detected ESP32-S3 with PSRAM size: {psram_size} bytes ({psram_size // 1048576}MB)")
                if psram_size == 8388608:  # 8MB PSRAM
                    board_name = "matouch_esp32_s3_2_8"
                    print(f"Forcing board selection: {board_name}")
                    return board_name
        except Exception as e:
            print(f"PSRAM detection failed: {e}")
        
        from machine import Pin, I2C
        import time
        
        # Check for MaTouch ESP32-S3 (GT911 touch on I2C0)
        # Correct pins from schematic: SDA=39, SCL=38, INT=40, RST=1
        # GT911 requires specific reset sequence with INT pin control for address selection
        try:
            # GT911 address selection via INT pin during reset:
            # INT=LOW during reset -> address 0x5D
            # INT=HIGH during reset -> address 0x14
            
            # Try address 0x5D first (INT=LOW during reset)
            tp_rst = Pin(1, Pin.OUT)
            tp_int = Pin(40, Pin.OUT)
            
            # Reset sequence for address 0x5D
            tp_int.value(0)  # INT LOW for address 0x5D
            tp_rst.value(0)
            time.sleep_ms(10)
            tp_rst.value(1)
            time.sleep_ms(10)
            tp_int.init(Pin.IN)  # Release INT pin
            time.sleep_ms(100)  # Wait for GT911 to initialize
            
            # Now try I2C communication with correct pins from schematic
            i2c0 = I2C(0, sda=Pin(39), scl=Pin(38), freq=400000)
            devices = set(i2c0.scan())
            print(f"MaTouch I2C scan (SDA=39, SCL=38): {[hex(d) for d in devices]}")
            
            # GT911 touch controller uses addresses 0x5D or 0x14
            if 0x5D in devices or 0x14 in devices:
                print("Detected MaTouch ESP32-S3 (GT911 found)")
                return "matouch_esp32_s3_2_8"
            
            # Clean up pins
            tp_rst.init(Pin.IN)
            tp_int.init(Pin.IN)
        except Exception as e:
            print(f"MaTouch detection failed: {e}")
            import sys
            sys.print_exception(e)
        
        # Check for Waveshare ESP32-S3-Touch-LCD-2
        try:
            i2c0 = I2C(0, sda=Pin(48), scl=Pin(47), freq=400000)
            devices = set(i2c0.scan())
            print(f"Waveshare I2C scan (SDA=48, SCL=47): {[hex(d) for d in devices]}")
            # Filter out invalid addresses (valid I2C range is 0x08-0x77)
            valid_devices = {d for d in devices if 0x08 <= d <= 0x77}
            if {0x15, 0x6B} <= valid_devices: # touch screen and IMU (at least, possibly more)
                print("Detected Waveshare ESP32-S3-Touch-LCD-2")
                return "waveshare_esp32_s3_touch_lcd_2"
        except Exception as e:
            print(f"Waveshare detection failed: {e}")
        
        # Check for Fri3d 2024
        try:
            i2c0 = I2C(0, sda=Pin(9), scl=Pin(18), freq=400000)
            devices = set(i2c0.scan())
            print(f"Fri3d I2C scan (SDA=9, SCL=18): {[hex(d) for d in devices]}")
            if {0x6B} <= devices: # IMU (plus possibly the Communicator's LANA TNY at 0x38)
                print("Detected Fri3d 2024")
                return "fri3d_2024"
            else: # if {0x6A} <= set(i2c0.scan()): # IMU (plus a few others, to be added later, but this should work)
                print("Detected Fri3d 2026")
                return "fri3d_2026"
        except Exception as e:
            print(f"Fri3d detection failed: {e}")
            return "fri3d_2026"  # Default fallback


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
launcher_app = AppManager.get_launcher()
started_launcher = AppManager.start_app(launcher_app.fullname)
# Then start auto_start_app if configured
auto_start_app = prefs.get_string("auto_start_app", None)
if auto_start_app and launcher_app.fullname != auto_start_app:
    result = AppManager.start_app(auto_start_app)
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
