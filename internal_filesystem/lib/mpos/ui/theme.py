import lvgl as lv
import mpos.config

def set_theme(prefs):
    # Load and set theme:
    theme_light_dark = prefs.get_string("theme_light_dark", "light") # default to a light theme
    theme_dark_bool = ( theme_light_dark == "dark" )
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
