import logging
import lvgl as lv

logger = logging.getLogger(__name__)

copied = None

def add(tocopy):
    copied = tocopy

def get():
    return copied

def paste_text(text): # called when CTRL-V is pressed on the keyboard
    if __debug__: logger.debug("paste_text adding %s", text)
    focusgroup = lv.group_get_default()
    if not focusgroup:
        return
    focused_obj = focusgroup.get_focused()
    if focused_obj and isinstance(focused_obj, lv.textarea):
        focused_obj.add_text(text)
