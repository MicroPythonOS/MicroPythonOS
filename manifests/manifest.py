# Freeze at -O3. The code is written for it (AGENTS.md: a debug call inside
# `if __debug__:` is expected to disappear from a release build), and it is
# what keeps the classic esp32 image inside its 3.5 MB app slot: without it
# every one of the tree's 751 `if __debug__:` blocks and every docstring sits
# in flash. It only drops __debug__ code, docstrings and asserts.
OPT = 3

freeze('../internal_filesystem/', 'main.py', OPT) # Hardware initialization
freeze('../internal_filesystem/lib', '', OPT) # Additional libraries
freeze('../freezeFS/', 'freezefs_mount_builtin.py', OPT) # Built-in apps
import os
# USB host builds (MPOS_NO_USBDEV=1, see scripts/build_mpos.sh
# --usb) compile out the TinyUSB *device* stack, so its pure-Python
# framework would be dead flash. Nothing in the tree imports it.
if not os.getenv("MPOS_NO_USBDEV"):
    package("usb", base_path="../lvgl_micropython/lib/micropython/lib/micropython-lib/micropython/usb/usb-device", opt=OPT)
    package("usb", base_path="../lvgl_micropython/lib/micropython/lib/micropython-lib/micropython/usb/usb-device-midi", opt=OPT)
