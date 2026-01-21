import lvgl as lv
import mpos.config

# Global style for keyboard button fix
_keyboard_button_fix_style = None
_is_light_mode = True

def get_keyboard_button_fix_style():
    """
    Get the keyboard button fix style for light mode.

    The LVGL default theme applies bg_color_white to keyboard buttons,
    which makes them white-on-white (invisible) in light mode.
    This function returns a custom style to override that.

    Returns:
        lv.style_t: Style to apply to keyboard buttons, or None if not needed
    """
    global _keyboard_button_fix_style, _is_light_mode

    # Only return style in light mode
    if not _is_light_mode:
        return None

    # Create style if it doesn't exist
    if _keyboard_button_fix_style is None:
        _keyboard_button_fix_style = lv.style_t()
        _keyboard_button_fix_style.init()

        # Set button background to light gray (matches LVGL's intended design)
        # This provides contrast against white background
        # Using palette_lighten gives us the same gray as used in the theme
        gray_color = lv.palette_lighten(lv.PALETTE.GREY, 2)
        _keyboard_button_fix_style.set_bg_color(gray_color)
        _keyboard_button_fix_style.set_bg_opa(lv.OPA.COVER)

    return _keyboard_button_fix_style

# On ESP32, the keyboard buttons in light mode have no color, just white,
# which makes them hard to see on the white background. Probably a bug in the
# underlying LVGL or MicroPython or lvgl_micropython.
def fix_keyboard_button_style(keyboard):
    """
    Apply keyboard button visibility fix to a keyboard instance.

    Call this function after creating a keyboard to ensure buttons
    are visible in light mode.

    Args:
        keyboard: The lv.keyboard instance to fix
    """
    style = get_keyboard_button_fix_style()
    if style:
        keyboard.add_style(style, lv.PART.ITEMS)
        print(f"Applied keyboard button fix for light mode to keyboard instance")

def set_theme(prefs):
    global _is_light_mode

    # Load and set theme:
    theme_light_dark = prefs.get_string("theme_light_dark", "light") # default to a light theme
    theme_dark_bool = ( theme_light_dark == "dark" )
    _is_light_mode = not theme_dark_bool  # Track for keyboard button fix

    primary_color = lv.theme_get_color_primary(None)
    color_string = prefs.get_string("theme_primary_color")
    if color_string:
        try:
            color_string = color_string.replace("0x", "").replace("#", "").strip().lower()
            color_int = int(color_string, 16)
            print(f"Setting primary color: {color_int}")
            primary_color = lv.color_hex(color_int)
        except Exception as e:
            print(f"Converting color setting '{color_string}' to lv_color_hex() got exception: {e}")

    lv.theme_default_init(mpos.ui.main_display._disp_drv, primary_color, lv.color_hex(0xFBDC05), theme_dark_bool, lv.font_montserrat_12)
    #mpos.ui.main_display.set_theme(theme) # not needed, default theme is applied immediately

    # Recreate keyboard button fix style if mode changed
    global _keyboard_button_fix_style
    _keyboard_button_fix_style = None  # Force recreation with new theme colors

def is_light_mode():
    global _is_light_mode
    return _is_light_mode