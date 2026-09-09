freeze('../internal_filesystem/', 'main.py') # Hardware initialization
freeze('../internal_filesystem/lib', '') # Additional libraries
freeze('../freezeFS/', 'freezefs_mount_builtin.py') # Built-in apps
import os
# USB display adapter builds (MPOS_NO_USBDEV=1, see scripts/build_mpos.sh
# --usbdisplay) compile out the TinyUSB *device* stack, so its pure-Python
# framework would be dead flash. Nothing in the tree imports it.
if not os.getenv("MPOS_NO_USBDEV"):
    package("usb", base_path="../lvgl_micropython/lib/micropython/lib/micropython-lib/micropython/usb/usb-device")
    package("usb", base_path="../lvgl_micropython/lib/micropython/lib/micropython-lib/micropython/usb/usb-device-midi")
