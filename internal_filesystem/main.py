import task_handler

import mpos.ui


RED = lv.palette_main(lv.PALETTE.RED)

DARKPINK = lv.color_hex(0xEC048C)
MEDIUMPINK = lv.color_hex(0xF480C5)
LIGHTPINK = lv.color_hex(0xF9E9F2)
DARKYELLOW = lv.color_hex(0xFBDC05)
LIGHTYELLOW = lv.color_hex(0xFBE499)

theme = lv.theme_default_init(display._disp_drv, DARKPINK, DARKYELLOW, False, lv.font_montserrat_12)
#theme = lv.theme_default_init(display._disp_drv, DARKPINK, DARKYELLOW, True, lv.font_montserrat_12)

#display.set_theme(theme)

mpos.ui.init_rootscreen()
mpos.ui.create_notification_bar()
mpos.ui.create_drawer(display)
mpos.ui.handle_back_swipe()
mpos.ui.handle_top_swipe()
mpos.ui.th = task_handler.TaskHandler(duration=5) # 5ms is recommended for MicroPython+LVGL on desktop

# Maybe this should only be done if there is not already a "builtin" folder... with the expected apps/4apps
try:
    import freezefs_mount_builtin
except Exception as e:
    print("main.py: WARNING: could not import/run freezefs_mount_builtin: ", e)

from mpos import apps
apps.execute_script("builtin/system/button.py", True) # Install button handler through IRQ

apps.auto_connect()

apps.restart_launcher()

# If we got this far without crashing, then no need to rollback the update:
try:
    import ota.rollback
    ota.rollback.cancel()
except Exception as e:
    print("main.py: warning: could not mark this update as valid:", e)
