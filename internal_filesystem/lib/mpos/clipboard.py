import lvgl as lv

copied = None

def add(tocopy):
    copied = tocopy

def get():
    return copied

def paste_text(text): # called when CTRL-V is pressed on the keyboard
    print(f"mpos.ui.clipboard.py paste_text adding {text}")
    focusgroup = lv.group_get_default()
    if not focusgroup:
        return
    focused_obj = focusgroup.get_focused()
    if focused_obj and isinstance(focused_obj, lv.textarea):
        focused_obj.add_text(text)
