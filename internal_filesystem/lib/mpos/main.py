import _thread
import lvgl as lv

import mpos.ui
import mpos.ui.topmenu

from mpos import AppearanceManager, AppManager, BuildInfo, DeviceInfo, DisplayMetrics, SharedPreferences, TaskManager

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
    if width < 296:
        img.set_scale(int(256 * width/296))
    img.set_blend_mode(lv.BLEND_MODE.DIFFERENCE)
    img.center()

def single_address_i2c_scan(i2c_bus, address):
    """
    Scan a specific I2C address to check if a device is present.

    Args:
        i2c_bus: An I2C bus object (machine.I2C instance)
        address: Integer address to scan (0-127)

    Returns:
        True if a device responds at the specified address, False otherwise
    """
    print(f"Attempt to write a single byte to I2C bus address 0x{address:02x}...")
    try:
        # Attempt to write a single byte to the address
        # This will raise an exception if no device responds
        i2c_bus.writeto(address, b"")
        print("Write test successful")
        return True
    except OSError as e:
        print(f"No device at this address: {e}")
        return False
    except Exception as e:
        # Handle any other exceptions gracefully
        print(f"scan error: {e}")
        return False


def fail_save_i2c(sda, scl):
    from machine import I2C, Pin

    print(f"Try to I2C initialized on {sda=} {scl=}")
    try:
        i2c0 = I2C(0, sda=Pin(sda), scl=Pin(scl))
    except Exception as e:
        print(f"Failed: {e}")
        return None
    else:
        print("OK")
        return i2c0


def check_pins(*pins):
    from machine import Pin

    print(f"Test {pins=}...")
    for pin in pins:
        try:
            Pin(pin)
        except Exception as e:
            print(f"Failed to initialize {pin=}: {e}")
            return True
    print("All pins initialized successfully")
    return True


def detect_board():
    import sys
    if sys.platform == "linux" or sys.platform == "darwin": # linux and macOS
        return "linux"
    elif sys.platform == "esp32":

        # First do unique_id-based board detections because they're fast and don't mess with actual hardware configurations
        import machine
        unique_id_prefixes = machine.unique_id()[0:3]

        print("(emulated) lilygo_t_display_s3 ?")
        if unique_id_prefixes == b'\x10\x01\x00' or unique_id_prefixes == b'\xc0\x4e\x30':
            return "lilygo_t_display_s3" # display gets confused by the i2c stuff below

        print("odroid_go ?")
        if unique_id_prefixes[0] == 0x30:
            return "odroid_go"

        print("fri3d_2026 ?")
        if unique_id_prefixes == b'\xdc\xb4\xd9':
            # or: if single_address_i2c_scan(i2c0, 0x6A): # IMU currently not installed on prototype board
            return "fri3d_2026"

        print("lilygo_t_watch_s3_plus ?")
        if i2c0 := fail_save_i2c(sda=10, scl=11):
            if single_address_i2c_scan(i2c0, 0x19): # IMU on 0x19, scan shows: [25, 52, 81, 90]
                return "lilygo_t_watch_s3_plus" # example MAC address: D0:CF:13:33:36:306

        # Then do I2C-based board detection
        print("matouch_esp32_s3_spi_ips_2_8_with_camera_ov3660 ?")
        if i2c0 := fail_save_i2c(sda=39, scl=38):
            if single_address_i2c_scan(i2c0, 0x14) or single_address_i2c_scan(i2c0, 0x5D): # "ghost" or real GT911 touch screen
                return "matouch_esp32_s3_spi_ips_2_8_with_camera_ov3660"

        print("waveshare_esp32_s3_touch_lcd_2 ?")
        if i2c0 := fail_save_i2c(sda=48, scl=47):
            # IO48 is floating on matouch_esp32_s3_spi_ips_2_8_with_camera_ov3660 and therefore, using that for I2C will find many devices, so do this after matouch_esp32_s3_spi_ips_2_8_with_camera_ov3660
            if single_address_i2c_scan(i2c0, 0x15) and single_address_i2c_scan(i2c0, 0x6B): # CST816S touch screen and IMU
                return "waveshare_esp32_s3_touch_lcd_2"

        print("m5stack_fire ?")
        if i2c0 := fail_save_i2c(sda=21, scl=22):
            if single_address_i2c_scan(i2c0, 0x68): # IMU (MPU6886)
                return "m5stack_fire"

        print("fri3d_2024 ?")
        if i2c0 := fail_save_i2c(sda=9, scl=18):
            if single_address_i2c_scan(i2c0, 0x6B): # IMU (plus possibly the Communicator's LANA TNY at 0x38)
                return "fri3d_2024"


        print("Unknown board: couldn't detect known I2C devices or unique_id prefix")


# EXECUTION STARTS HERE

print(f"MicroPythonOS {BuildInfo.version.release} running lib/mpos/main.py")
board = detect_board()
if board:
    print(f"Detected {board} system, importing mpos.board.{board}")
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
    #focusgroup = lv.group_get_default()
    #if focusgroup: # on esp32 this may not be set
        # otherwise it does focus_next and then crashes while doing lv.deinit()
        #focusgroup.remove_all_objs()
        #focusgroup.delete()
    #lv.deinit()

import sys
import task_handler
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

# Start launcher first so it's always at bottom of stack
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

try:
    import webrepl
    webrepl.start(port=7890,password="MPOSweb26") # password is max 9 characters
except Exception as e:
    print(f"Could not start webrepl - this is normal on desktop systems: {e}")

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
