# lib/mpos/ui/util.py
import lvgl as lv
import sys
from ..apps import restart_launcher

_foreground_app_name = None

def set_foreground_app(name):
    global _foreground_app_name
    _foreground_app_name = name
    print(f"Foreground app: {name}")

def get_foreground_app():
    global _foreground_app_name
    return _foreground_app_name

def shutdown():
    print("Shutting down...")
    lv.deinit()
    sys.exit(0)

def close_top_layer_msgboxes():
    top = lv.layer_top()
    if not top:
        return
    i = 0
    while i < top.get_child_count_by_type(lv.msgbox_backdrop_class):
        child = top.get_child_by_type(i, lv.msgbox_backdrop_class)
        msgbox = child.get_child_by_type(0, lv.msgbox_class)
        if msgbox:
            msgbox.close()
        i += 1
