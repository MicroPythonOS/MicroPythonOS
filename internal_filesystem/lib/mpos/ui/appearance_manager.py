import logging
import lvgl as lv

logger = logging.getLogger(__name__)

class AppearanceManager:
    
    # ========== UI Dimensions ==========
    # These are constants that define the layout of the UI
    NOTIFICATION_BAR_HEIGHT = 24  # Height of the notification bar in pixels
    DEFAULT_PRIMARY_COLOR = "f0a010"
    
    # ========== Private Class Variables ==========
    # State variables shared across all "instances" (there is only one logical instance)
    _is_light_mode = True
    _primary_color = None
    _accent_color = None
    _keyboard_button_fix_style = None
    
    # ========== Utility Colors ==========

    @staticmethod
    def percent_to_rainbow_color(value: float) -> tuple[int, int, int]:
        return AppearanceManager.rainbow_color(
            max(0.0, min(1.0, value / 100.0))
        ) # normalized 0.0 to 1.0

    @staticmethod
    def rainbow_color(t: float) -> tuple[int, int, int]:
        hue = t * 300.0
        h = hue / 60.0
        i = int(h)
        f = h - i                               # fractional part

        if i == 0:
            r, g, b = 1.0, f, 0.0
        elif i == 1:
            r, g, b = 1.0 - f, 1.0, 0.0
        elif i == 2:
            r, g, b = 0.0, 1.0, f
        elif i == 3:
            r, g, b = 0.0, 1.0 - f, 1.0
        elif i == 4:
            r, g, b = f, 0.0, 1.0
        else:  # i == 5
            r, g, b = 1.0, 0.0, 1.0 - f

        return (int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5))

    # ========== Initialization ==========
    
    @classmethod
    def init(cls, prefs):
        # Load light/dark mode preference
        theme_light_dark = prefs.get_string("theme_light_dark", "light")
        theme_dark_bool = (theme_light_dark == "dark")
        cls._is_light_mode = not theme_dark_bool

        primary_color = lv.theme_get_color_primary(None) # Load primary color from LVGL default

        # Try to get a valid color from the preferences
        color_string = prefs.get_string("theme_primary_color", cls.DEFAULT_PRIMARY_COLOR)
        try:
            color_string = color_string.replace("0x", "").replace("#", "").strip().lower()
            color_int = int(color_string, 16)
            if __debug__: logger.debug("Setting primary color: %s", color_int)
            primary_color = lv.color_hex(color_int)
            cls._primary_color = primary_color
        except Exception as e:
            logger.error("Converting color setting '%s' failed: %s", color_string, e)

        # Initialize LVGL theme with loaded settings
        # Get the display driver from the active screen
        screen = lv.screen_active()
        disp = screen.get_display()
        lv.theme_default_init(
            disp,
            primary_color,
            lv.color_hex(0xFBDC05),  # Accent color (yellow)
            theme_dark_bool,
            lv.font_montserrat_12
        )
        # Reset keyboard button fix style so it's recreated with new theme colors
        cls._keyboard_button_fix_style = None
        
        if __debug__: logger.debug("Initialized: light_mode=%s, primary_color=%s", cls._is_light_mode, primary_color)
    
    # ========== Light/Dark Mode ==========
    
    @classmethod
    def is_light_mode(cls):
        return cls._is_light_mode
    
    @classmethod
    def set_light_mode(cls, is_light, prefs=None):
        cls._is_light_mode = is_light

        # Save to preferences if provided, then reinitialise LVGL theme.
        # SharedPreferences doesn't have a set_string() — writes go through
        # edit().put_string().commit().
        if prefs:
            theme_str = "light" if is_light else "dark"
            editor = prefs.edit()
            editor.put_string("theme_light_dark", theme_str)
            editor.commit()
            cls.init(prefs)

        if __debug__: logger.debug("Light mode set to: %s", is_light)
    
    @classmethod
    def set_theme(cls, prefs):
        cls.init(prefs)

    @classmethod
    def get_primary_color(cls):
        return cls._primary_color

    @classmethod
    def set_primary_color(cls, color, prefs=None):
        cls._primary_color = color

        # Save to preferences if provided, then reinitialise LVGL theme so the
        # new colour is actually applied. SharedPreferences doesn't have a
        # set_string() — writes go through edit().put_string().commit().
        if prefs and isinstance(color, int):
            editor = prefs.edit()
            editor.put_string("theme_primary_color", f"0x{color:06X}")
            editor.commit()
            cls.init(prefs)

        if __debug__: logger.debug("Primary color set to: %s", color)
    
    # ========== UI Dimensions ==========
    
    @classmethod
    def get_notification_bar_height(cls):
        return cls.NOTIFICATION_BAR_HEIGHT
    
    # ========== Keyboard Styling Workarounds ==========
    
    @classmethod
    def get_keyboard_button_fix_style(cls):
        # Only return style in light mode
        if not cls._is_light_mode:
            return None
        
        # Create style if it doesn't exist
        if cls._keyboard_button_fix_style is None:
            cls._keyboard_button_fix_style = lv.style_t()
            cls._keyboard_button_fix_style.init()
            
            # Set button background to light gray (matches LVGL's intended design)
            # This provides contrast against white background
            # Using palette_lighten gives us the same gray as used in the theme
            gray_color = lv.palette_lighten(lv.PALETTE.GREY, 2)
            cls._keyboard_button_fix_style.set_bg_color(gray_color)
            cls._keyboard_button_fix_style.set_bg_opa(lv.OPA.COVER)
        
        return cls._keyboard_button_fix_style
    
    @classmethod
    def apply_keyboard_fix(cls, keyboard):
        style = cls.get_keyboard_button_fix_style()
        if style:
            keyboard.add_style(style, lv.PART.ITEMS)
            if __debug__: logger.debug("Applied keyboard button fix for light mode")
