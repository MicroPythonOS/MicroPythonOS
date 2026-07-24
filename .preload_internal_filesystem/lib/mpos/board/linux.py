# Hardware initialization for Unix and MacOS systems
import logging

logger = logging.getLogger(__name__)

import lcd_bus
import lvgl as lv
import sdl_display

from drivers.indev.sdl_keyboard import MposSDLKeyboard

import mpos.clipboard
import mpos.ui
import mpos.ui.focus_direction
from mpos import InputManager

# Same as Waveshare ESP32-S3-Touch-LCD-2 and Fri3d Camp 2026 Badge
TFT_HOR_RES=320
TFT_VER_RES=240

# Fri3d Camp 2024 Badge:
#TFT_HOR_RES=296
#TFT_VER_RES=240

# Makerfabs / Matouch
#TFT_HOR_RES=240
#TFT_VER_RES=320

# LilyGo T-Display-S3
#TFT_HOR_RES=320
#TFT_VER_RES=170

# 4:3 DVD resolution:
#TFT_HOR_RES=720
#TFT_VER_RES=576

# 16:9 resolution:
#TFT_HOR_RES=1024
#TFT_VER_RES=576

# 16:9 good resolution but fairly small icons:
#TFT_HOR_RES=1280
#TFT_VER_RES=720

# Even HD works:
#TFT_HOR_RES=1920
#TFT_VER_RES=1080

bus = lcd_bus.SDLBus(flags=0)

buf1 = bus.allocate_framebuffer(TFT_HOR_RES * TFT_VER_RES * 2, 0)

mpos.ui.main_display = sdl_display.SDLDisplay(data_bus=bus,display_width=TFT_HOR_RES,display_height=TFT_VER_RES,frame_buffer1=buf1,color_space=lv.COLOR_FORMAT.RGB565)
# display.set_dpi(65) # doesn't seem to change the default 130...
mpos.ui.main_display.init()
# main_display.set_dpi(65) # doesn't seem to change the default 130...
import sdl_pointer
mouse = sdl_pointer.SDLPointer()
InputManager.register_indev(mouse)


def catch_escape_key(indev, indev_data):
    global sdlkeyboard
    #key = indev.get_key() # always 0
    #key = indev_data.key
    #state = indev_data.state
    pressed, code = sdlkeyboard._get_key() # get the current key and state
    if __debug__: logger.debug("catch_escape_key caught: %s, %s" % (pressed, code))
    if pressed == 1 and code == 27: # ESCAPE
        mpos.ui.back_screen()
    elif pressed == 1 and code == 2: # HOME
        from mpos.ui import topmenu as topmenu
        topmenu.toggle_drawer()
    elif pressed == 1 and code == lv.KEY.RIGHT:
        mpos.ui.focus_direction.move_focus_direction(90)
    elif pressed == 1 and code == lv.KEY.LEFT:
        mpos.ui.focus_direction.move_focus_direction(270)
    elif pressed == 1 and code == lv.KEY.UP:
        mpos.ui.focus_direction.move_focus_direction(0)
    elif pressed == 1 and code == lv.KEY.DOWN:
        mpos.ui.focus_direction.move_focus_direction(180)

    sdlkeyboard._read(indev, indev_data)

sdlkeyboard = MposSDLKeyboard()
sdlkeyboard._indev_drv.set_read_cb(catch_escape_key) # check for escape
InputManager.register_indev(sdlkeyboard)
try:
    sdlkeyboard.set_paste_text_callback(mpos.clipboard.paste_text)
except Exception as e:
    logger.warning("Warning: could not set paste_text callback for sdlkeyboard, copy-paste won't work")


#def keyboard_cb(event):
 #   global canvas
  #  event_code=event.get_code()
#keyboard.add_event_cb(keyboard_cb, lv.EVENT.ALL, None)


# Simulated battery voltage ADC measuring
from mpos import BatteryManager

def adc_to_voltage(adc_value):
    """Convert simulated ADC value to voltage."""
    return adc_value * (3.3 / 4095) * 2

BatteryManager.init_adc(999, adc_to_voltage)

# === AUDIO HARDWARE ===
from mpos import AudioManager

# Desktop builds have no real audio hardware, but we simulate microphone
# recording with a 440Hz sine wave for testing WAV file generation
# The i2s_pins dict with 'sd_in' enables microphone simulation

output_i2s_pins = {
    'sck': 0,       # Simulated - not used on desktop
    'ws': 0,        # Simulated - not used on desktop
    'sd': 0,        # Simulated - not used on desktop
}
input_i2s_pins = {
    'sck_in': 0,    # Simulated - not used on desktop
    'ws': 0,        # Simulated - not used on desktop
    'sd_in': 0,     # Simulated - enables microphone simulation
}

AudioManager.add(AudioManager.Output("speaker", "i2s", i2s_pins=output_i2s_pins))
AudioManager.add(AudioManager.Input("mic", "i2s", i2s_pins=input_i2s_pins))

# === LED HARDWARE ===
# Desktop builds have no LED hardware; the web (Emscripten) build emulates
# 5 NeoPixels on the page via the _webio bridge + staged neopixel shim.
# On native unix/macOS `_webio` doesn't exist, so this stays a no-op and
# LightsManager functions return False.
try:
    import _webio
except ImportError:
    _webio = None

if _webio:
    from mpos import LightsManager
    LightsManager.init(neopixel_pin=12)
    LightsManager.set_led_num(5)

# === WEB BADGE BUTTONS + JOYSTICK ===
# The web page (shell.html) renders a Fri3d-2026-style joystick and
# X/Y/A/B/MENU buttons. Their state is exposed through _webio as an
# expander-compatible `digital` tuple, so the REAL badge indev driver
# (Fri3d2026Expander) runs unchanged: same key mapping, long-press repeat
# and navigation hooks as physical hardware.
if _webio:
    try:
        from web_expander import WebExpander
        from drivers.indev.fri3d_2026_expander import Fri3d2026Expander

        web_expander = WebExpander()
        web_buttons_indev = Fri3d2026Expander(web_expander)
        group = lv.group_get_default()
        if group:
            web_buttons_indev.set_group(group)
        web_buttons_indev.enable(True)
        InputManager.register_indev(web_buttons_indev)

        # START button: on the physical badge this is GPIO 0 (not on the
        # expander) mapped to lv.KEY.END by a separate keypad indev.
        # Mirror that here using the web expander's start_button property.
        _web_start_last_key = None

        def _web_start_read_cb(indev, data):
            global _web_start_last_key
            data.continue_reading = False
            if web_expander.start_button:
                data.key = lv.KEY.END
                data.state = lv.INDEV_STATE.PRESSED
                _web_start_last_key = lv.KEY.END
            else:
                data.key = _web_start_last_key if _web_start_last_key is not None else lv.KEY.ENTER
                data.state = lv.INDEV_STATE.RELEASED
                _web_start_last_key = None

        web_start_indev = lv.indev_create()
        web_start_indev.set_type(lv.INDEV_TYPE.KEYPAD)
        web_start_indev.set_read_cb(_web_start_read_cb)
        if group:
            web_start_indev.set_group(group)
        web_start_indev.set_display(lv.display_get_default())
        web_start_indev.enable(True)
        web_start_indev.set_long_press_time(400)
        web_start_indev.set_long_press_repeat_time(100)
        InputManager.register_indev(web_start_indev)
    except Exception as e:
        logger.error("web badge buttons init got exception: %s" % (e))

# === SENSOR HARDWARE ===
from mpos import SensorManager

SensorManager.init_iio()

# === CAMERA HARDWARE ===

def init_cam(width, height, colormode):
    try:
        # Try to initialize webcam to verify it's available
        import webcam
        return webcam.init("/dev/video0", width=width, height=height)
    except Exception as e:
        logger.error("Info: webcam initialization failed, camera will not be available: %s" % (e))

def deinit_cam(cam_obj):
    import webcam
    webcam.deinit(cam_obj)

def capture_cam(cam_obj, colormode):
    import webcam
    return webcam.capture_frame(cam_obj, "rgb565" if colormode else "grayscale")

def apply_cam_settings(cam_obj, prefs):
    if __debug__: logger.debug("V4L Camera doesn't support settings for now, skipping...")

from mpos import CameraManager
CameraManager.add_camera(CameraManager.Camera(
    lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_FRONT,
    name="Video4Linux2 Camera",
    vendor="ACME",
    init=init_cam,
    deinit=deinit_cam,
    capture=capture_cam,
    apply_settings=apply_cam_settings
))


if __debug__: logger.debug("linux.py finished")



