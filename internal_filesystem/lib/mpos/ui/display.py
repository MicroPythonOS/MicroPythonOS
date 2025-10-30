# lib/mpos/ui/display.py
import lvgl as lv

_horizontal_resolution = None
_vertical_resolution = None

def init_rootscreen():
    global _horizontal_resolution, _vertical_resolution
    screen = lv.screen_active()
    disp = screen.get_display()
    _horizontal_resolution = disp.get_horizontal_resolution()
    _vertical_resolution = disp.get_vertical_resolution()
    print(f"init_rootscreen set _vertical_resolution to {_vertical_resolution}")

    style = lv.style_t()
    style.init()
    style.set_bg_opa(lv.OPA.TRANSP)
    style.set_border_width(0)
    style.set_outline_width(0)
    style.set_shadow_width(0)
    style.set_pad_all(0)
    style.set_radius(0)
    screen.add_style(style, 0)
    screen.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    screen.set_scroll_dir(lv.DIR.NONE)

    label = lv.label(screen)
    label.set_text("Welcome to MicroPythonOS")
    label.center()

def get_pointer_xy():
    indev = lv.indev_active()
    if indev:
        p = lv.point_t()
        indev.get_point(p)
        return p.x, p.y
    return -1, -1

def pct_of_display_width(pct):
    return round(_horizontal_resolution * pct / 100)

def pct_of_display_height(pct):
    return round(_vertical_resolution * pct / 100)

def min_resolution():
    return min(_horizontal_resolution, _vertical_resolution)

def max_resolution():
    return max(_horizontal_resolution, _vertical_resolution)

def get_display_width():
    if _horizontal_resolution is None:
        _init_resolution()
    return _horizontal_resolution

def get_display_height():
    if _vertical_resolution is None:
        _init_resolution()
    return _vertical_resolution
