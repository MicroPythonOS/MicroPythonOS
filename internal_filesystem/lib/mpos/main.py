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

def detect_lilygo_t_hmi():
    from machine import Pin, SoftSPI
    import time

    try:
        sck = Pin(1)
        mosi = Pin(3)
        miso = Pin(4)
        cs = Pin(2, Pin.OUT, value=1)
        irq = Pin(9, Pin.IN, Pin.PULL_UP)

        spi = SoftSPI(
            baudrate=500000,
            polarity=0,
            phase=0,
            sck=sck,
            mosi=mosi,
            miso=miso,
        )

        def read_cmd(cmd):
            tx = bytearray([cmd, 0x00, 0x00])
            rx = bytearray(3)

            cs(0)
            spi.write_readinto(tx, rx)
            cs(1)

            return ((rx[1] << 8) | rx[2]) >> 3

        samples = []
        for _ in range(5):
            vals = (
                read_cmd(0xD0),  # X
                read_cmd(0x90),  # Y
                read_cmd(0xB0),  # Z1
                irq.value(),
            )
            samples.append(vals)
            print("T-HMI touch sample:", vals)
            time.sleep_ms(20)

        # Observed stable idle signature on LilyGO T-HMI:
        # X=0, Y=4095, Z1=0/1, IRQ=1
        signature_hits = sum(
            x == 0 and y == 4095 and z in (0, 1) and irqv == 1
            for x, y, z, irqv in samples
        )

        print(f"T-HMI signature hits: {signature_hits}/5")

        if signature_hits >= 4:
            print("LilyGO T-HMI touch signature matched")
            return True

    except Exception as e:
        print(f"LilyGO T-HMI detection failed: {e}")

    finally:
        try:
            Pin(1, Pin.IN, pull=None)
            Pin(2, Pin.IN, pull=None)
            Pin(3, Pin.IN, pull=None)
            Pin(4, Pin.IN, pull=None)
            Pin(9, Pin.IN, pull=None)
        except Exception:
            pass

    return False

def fail_save_i2c(sda, scl):
    from machine import I2C, Pin

    print(f"Try to I2C initialized on {sda=} {scl=}")
    try:
        i2c0 = I2C(0, sda=Pin(sda), scl=Pin(scl))
    except Exception as e:
        print(f"fail_save_i2c failed: {e}")
        return None
    else:
        print("fail_save_i2c ok")
        return i2c0

def restore_i2c(sda, scl):
    from machine import Pin

    Pin(sda, Pin.IN, pull=None)
    Pin(scl, Pin.IN, pull=None)

def detect_board():
    import sys
    if sys.platform == "linux" or sys.platform == "darwin": # linux and macOS
        return "linux"
    elif sys.platform == "esp32":

        '''
        # Reading and storing all pinstates can be useful for board detection
        # But reading some pins can break peripherals
        # So it's disabled by default - it's more for development
        try:
            import mpos
            from mpos.board import pinstates
            mpos.pinstates = pinstates.read_all_pins(skiplist = [7,8])
        except Exception as e:
            print("pinstates: WARNING: failed to read pins:", e)
        '''

        # First do unique_id-based board detections because they're fast and don't mess with actual hardware configurations
        import machine
        unique_id_prefixes = machine.unique_id()[0:3]

        print("unPhone ?")
        if unique_id_prefixes == b'\x30\x30\xf9':
            return "unphone"

        print("odroid_go ?")
        if unique_id_prefixes == b'\x30\xae\xa4':
            return "odroid_go"

        print("lilygo_t_hmi ?")
        if detect_lilygo_t_hmi():
            return "lilygo_t_hmi"

        # Do I2C-based board detection
        print("lilygo_t_watch_s3_plus ?")
        if i2c0 := fail_save_i2c(sda=10, scl=11):
            if single_address_i2c_scan(i2c0, 0x19): # IMU on 0x19, vibrator on 0x5A and scan also shows: [52, 81]
                return "lilygo_t_watch_s3_plus" # example MAC address: D0:CF:13:33:36:306
            restore_i2c(sda=10, scl=11)

        print("matouch_esp32_s3_spi_ips_2_8_with_camera_ov3660 ?")
        if i2c0 := fail_save_i2c(sda=39, scl=38):
            if single_address_i2c_scan(i2c0, 0x14) or single_address_i2c_scan(i2c0, 0x5D): # "ghost" or real GT911 touch screen
                return "matouch_esp32_s3_spi_ips_2_8_with_camera_ov3660"
            restore_i2c(sda=39, scl=38) # fix pin 39 (data0) breaking lilygo_t_display_s3's display

        print("waveshare_esp32_s3_touch_lcd_2 ?")
        if i2c0 := fail_save_i2c(sda=48, scl=47):
            # IO48 is floating on matouch_esp32_s3_spi_ips_2_8_with_camera_ov3660 and therefore, using that for I2C will find many devices, so do this after matouch_esp32_s3_spi_ips_2_8_with_camera_ov3660
            if single_address_i2c_scan(i2c0, 0x15) and single_address_i2c_scan(i2c0, 0x6B): # CST816S touch screen and IMU
                return "waveshare_esp32_s3_touch_lcd_2"
            restore_i2c(sda=48, scl=47) # fix pin 47 (data6) and 48 (data7) breaking lilygo_t_display_s3's display

        print("m5stack_fire ?")
        if i2c0 := fail_save_i2c(sda=21, scl=22):
            if single_address_i2c_scan(i2c0, 0x68): # IMU (MPU6886)
                return "m5stack_fire"
            restore_i2c(sda=21, scl=22)

        print("fri3d_2024 ?")
        if i2c0 := fail_save_i2c(sda=9, scl=18):
            if single_address_i2c_scan(i2c0, 0x6A): # ) 0x15: CST8 touch, 0x6A: IMU
                return "fri3d_2026"
            if single_address_i2c_scan(i2c0, 0x6B): # IMU (plus possibly the Communicator's LANA TNY at 0x38)
                return "fri3d_2024"
            restore_i2c(sda=9, scl=18)

        # On devices without I2C, we use known GPIO states
        from machine import Pin

        print("(emulated) lilygo_t_display_s3 ?")
        try:
            # 2 buttons have PCB pull-ups so they'll be high unless pressed
            pin0 = Pin(0, Pin.IN)
            pin14 = Pin(14, Pin.IN)
            if pin0.value() == 1 and pin14.value() == 1:
                return "lilygo_t_display_s3" # display gets confused by the i2c stuff below
        except Exception as e:
            print(f"lilygo_t_display_s3 detection got exception: {e}")

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

prefs = SharedPreferences("com.micropythonos.settings") # if not value is set, it will start the HowTo app

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

import task_handler
# 5ms is recommended for MicroPython+LVGL on desktop (less results in lower framerate but still okay)
# 1ms gives highest framerate on esp32-s3's but might have side effects?
mpos.ui.task_handler = task_handler.TaskHandler(duration=1, exception_hook=custom_exception_handler)
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
# Then start auto_start_app_early if configured
auto_start_app_early = prefs.get_string("auto_start_app_early", "com.micropythonos.howto")
if auto_start_app_early and launcher_app.fullname != auto_start_app_early:
    result = AppManager.start_app(auto_start_app_early)
    if result is not True:
        print(f"WARNING: could not run {auto_start_app_early} app")
else: # if no auto_start_app_early was configured (this could be improved to start it *after* auto_start_app_early finishes)
    auto_start_app = prefs.get_string("auto_start_app", None)
    if auto_start_app and launcher_app.fullname != auto_start_app and auto_start_app_early != auto_start_app:
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
    from mpos import WebServer
    WebServer.auto_start()
except Exception as e:
    print(f"Could not start webserver - this is normal on desktop systems: {e}")

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
