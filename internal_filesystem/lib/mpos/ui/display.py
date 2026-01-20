# lib/mpos/ui/display.py
import lvgl as lv
from mpos.ui.theme import _is_light_mode

_horizontal_resolution = None
_vertical_resolution = None
_dpi = None

logo_url = "M:builtin/res/mipmap-mdpi/MicroPythonOS_logo_white_on_black_240x54.png"

def init_rootscreen():
    global _horizontal_resolution, _vertical_resolution, _dpi
    screen = lv.screen_active()
    disp = screen.get_display()
    _horizontal_resolution = disp.get_horizontal_resolution()
    _vertical_resolution = disp.get_vertical_resolution()
    _dpi = disp.get_dpi()
    print(f"init_rootscreen set resolution to {_horizontal_resolution}x{_vertical_resolution} at {_dpi} DPI")
    try:
        img = lv.image(screen)
        img.set_src(logo_url)
        if _is_light_mode:
            img.set_blend_mode(lv.BLEND_MODE.DIFFERENCE) # invert the logo color 
        img.center()
    except Exception as e: # if image loading fails
        print(f"Falling back to text-based logo because image loading failed: {e}")
        screen.clean()
        label = lv.label(screen)
        label.set_text("MicroPythonOS")
        label.set_style_text_font(lv.font_montserrat_20, lv.PART.MAIN)
        label.center()

def get_pointer_xy():
    indev = lv.indev_active()
    if indev:
        p = lv.point_t()
        indev.get_point(p)
        return p.x, p.y
    return -1, -1

def pct_of_display_width(pct):
    if pct == 100:
        return _horizontal_resolution
    return round(_horizontal_resolution * pct / 100)

def pct_of_display_height(pct):
    if pct == 100:
        return _vertical_resolution
    return round(_vertical_resolution * pct / 100)

def min_resolution():
    return min(_horizontal_resolution, _vertical_resolution)

def max_resolution():
    return max(_horizontal_resolution, _vertical_resolution)

def get_display_width():
    return _horizontal_resolution

def get_display_height():
    return _vertical_resolution

def get_dpi():
    print(f"get_dpi_called {_dpi}")
    return _dpi
    
