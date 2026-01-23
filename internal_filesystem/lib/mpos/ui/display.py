# lib/mpos/ui/display.py
"""
Display initialization module.

Handles LVGL display initialization and sets up DisplayMetrics.
"""

import lvgl as lv
from .display_metrics import DisplayMetrics

# White text on black logo works (for dark mode) and can be inverted (for light mode)
logo_white = "M:builtin/res/mipmap-mdpi/MicroPythonOS-logo-white-long-w296.png" # from the MPOS-logo repo

# Black text on transparent logo works (for light mode) but can't be inverted (for dark mode)
# Even when trying different blend modes (SUBTRACTIVE, ADDITIVE, MULTIPLY)
# Even when it's on a white (instead of transparent) background
#logo_black = "M:builtin/res/mipmap-mdpi/MicroPythonOS-logo-black-long-w240.png"


def init_rootscreen():
    """Initialize the root screen and set display metrics."""
    screen = lv.screen_active()
    disp = screen.get_display()
    width = disp.get_horizontal_resolution()
    height = disp.get_vertical_resolution()
    dpi = disp.get_dpi()
    
    # Initialize DisplayMetrics with actual display values
    DisplayMetrics.set_resolution(width, height)
    DisplayMetrics.set_dpi(dpi)
    
    print(f"init_rootscreen set resolution to {width}x{height} at {dpi} DPI")
    
    try:
        img = lv.image(screen)
        img.set_src(logo_white)
        img.set_blend_mode(lv.BLEND_MODE.DIFFERENCE)
        img.center()
    except Exception as e:  # if image loading fails
        print(f"ERROR: logo image failed, LVGL will be in a bad state and the UI will hang: {e}")
        import sys
        sys.print_exception(e)
        print("Trying to fall back to a simple text-based 'logo' but it won't showup because the UI broke...")
        label = lv.label(screen)
        label.set_text("MicroPythonOS")
        label.set_style_text_font(lv.font_montserrat_20, lv.PART.MAIN)
        label.center()
