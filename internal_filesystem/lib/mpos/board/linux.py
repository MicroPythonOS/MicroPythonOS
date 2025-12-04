# Hardware initialization for Unix and MacOS systems
import lcd_bus
import lvgl as lv
import sdl_display

import mpos.clipboard
import mpos.indev.mpos_sdl_keyboard
import mpos.ui
import mpos.ui.focus_direction

# Same as Waveshare ESP32-S3-Touch-LCD-2 and Fri3d Camp 2026 Badge
TFT_HOR_RES=320
TFT_VER_RES=240

# Fri3d Camp 2024 Badge:
#TFT_HOR_RES=296
#TFT_VER_RES=240

# Bigger screen
#TFT_HOR_RES=640
#TFT_VER_RES=480

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

def catch_escape_key(indev, indev_data):
    global sdlkeyboard
    #print(f"keypad_cb {indev} {indev_data}")
    #key = indev.get_key() # always 0
    #print(f"key {key}")
    #key = indev_data.key
    #state = indev_data.state
    #print(f"indev_data: {state} and {key}") # this catches the previous key release instead of the next key press
    pressed, code = sdlkeyboard._get_key() # get the current key and state
    #print(f"catch_escape_key caught: {pressed}, {code}")
    if pressed == 1 and code == 27:
        mpos.ui.back_screen()
    elif pressed == 1 and code == lv.KEY.RIGHT:
        mpos.ui.focus_direction.move_focus_direction(90)
    elif pressed == 1 and code == lv.KEY.LEFT:
        mpos.ui.focus_direction.move_focus_direction(270)
    elif pressed == 1 and code == lv.KEY.UP:
        mpos.ui.focus_direction.move_focus_direction(0)
    elif pressed == 1 and code == lv.KEY.DOWN:
        mpos.ui.focus_direction.move_focus_direction(180)

    sdlkeyboard._read(indev, indev_data)

#import sdl_keyboard
sdlkeyboard = mpos.indev.mpos_sdl_keyboard.MposSDLKeyboard()
sdlkeyboard._indev_drv.set_read_cb(catch_escape_key) # check for escape
try:
    sdlkeyboard.set_paste_text_callback(mpos.clipboard.paste_text)
except Exception as e:
    print("Warning: could not set paste_text callback for sdlkeyboard, copy-paste won't work")

#def keyboard_cb(event):
 #   global canvas
  #  event_code=event.get_code()
   # print(f"boot_unix: code={event_code}") # target={event.get_target()}, user_data={event.get_user_data()}, param={event.get_param()}
#keyboard.add_event_cb(keyboard_cb, lv.EVENT.ALL, None)


# Simulated battery voltage ADC measuring
import mpos.battery_voltage

def adc_to_voltage(adc_value):
    """Convert simulated ADC value to voltage."""
    return adc_value * (3.3 / 4095) * 2

mpos.battery_voltage.init_adc(999, adc_to_voltage)

# === AUDIO HARDWARE ===
import mpos.audio.audioflinger as AudioFlinger

# Note: Desktop builds have no audio hardware
# AudioFlinger functions will return False (no-op)
AudioFlinger.init(
    device_type=AudioFlinger.DEVICE_NULL,
    i2s_pins=None,
    buzzer_instance=None
)

# === LED HARDWARE ===
# Note: Desktop builds have no LED hardware
# LightsManager will not be initialized (functions will return False)

# === SENSOR HARDWARE ===
# Note: Desktop builds have no sensor hardware
import mpos.sensor_manager as SensorManager
# Don't call init() - SensorManager functions will return None/False

print("linux.py finished")



