# lib/mpos/ui/appearance_manager.py
"""
AppearanceManager - Android-inspired appearance management singleton.

Manages all aspects of the app's visual appearance:
- Light/dark mode (UI appearance)
- Theme colors (primary, secondary, accent)
- UI dimensions (notification bar height, etc.)
- LVGL theme initialization
- Keyboard styling workarounds

This is a singleton implemented using class methods and class variables.
No instance creation is needed - all methods are class methods.

Example:
    from mpos import AppearanceManager
    
    # Check light/dark mode
    if AppearanceManager.is_light_mode():
        print("Light mode enabled")
    
    # Get UI dimensions
    bar_height = AppearanceManager.get_notification_bar_height()
    
    # Initialize appearance from preferences
    AppearanceManager.init(prefs)
"""

import lvgl as lv


class AppearanceManager:
    """
    Android-inspired appearance management singleton.
    
    Centralizes all UI appearance settings including theme colors, light/dark mode,
    and UI dimensions. Follows the singleton pattern using class methods and class
    variables, similar to Android's Configuration and Resources classes.
    
    All methods are class methods - no instance creation needed.
    """
    
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
    
    # ========== Initialization ==========
    
    @classmethod
    def init(cls, prefs):
        """
        Initialize AppearanceManager from preferences.
        
        Called during system startup to load theme settings from SharedPreferences
        and initialize the LVGL theme. This should be called once during boot.
        
        Args:
            prefs: SharedPreferences object containing theme settings
                - "theme_light_dark": "light" or "dark" (default: "light")
                - "theme_primary_color": hex color string like "0xFF5722" or "#FF5722"
        
        Example:
            from mpos import AppearanceManager
            import mpos.config
            
            prefs = mpos.config.get_shared_preferences()
            AppearanceManager.init(prefs)
        """
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
            print(f"[AppearanceManager] Setting primary color: {color_int}")
            primary_color = lv.color_hex(color_int)
            cls._primary_color = primary_color
        except Exception as e:
            print(f"[AppearanceManager] Converting color setting '{color_string}' failed: {e}")

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
        
        print(f"[AppearanceManager] Initialized: light_mode={cls._is_light_mode}, primary_color={primary_color}")
    
    # ========== Light/Dark Mode ==========
    
    @classmethod
    def is_light_mode(cls):
        """
        Check if light mode is currently enabled.
        
        Returns:
            bool: True if light mode is enabled, False if dark mode is enabled
        
        Example:
            from mpos import AppearanceManager
            
            if AppearanceManager.is_light_mode():
                print("Using light theme")
            else:
                print("Using dark theme")
        """
        return cls._is_light_mode
    
    @classmethod
    def set_light_mode(cls, is_light, prefs=None):
        """
        Set light/dark mode and update the theme.
        
        Args:
            is_light (bool): True for light mode, False for dark mode
            prefs (SharedPreferences, optional): If provided, saves the setting
        
        Example:
            from mpos import AppearanceManager
            
            AppearanceManager.set_light_mode(False)  # Switch to dark mode
        """
        cls._is_light_mode = is_light
        
        # Save to preferences if provided
        if prefs:
            theme_str = "light" if is_light else "dark"
            prefs.set_string("theme_light_dark", theme_str)
        
        # Reinitialize LVGL theme with new mode
        if prefs:
            cls.init(prefs)
        
        print(f"[AppearanceManager] Light mode set to: {is_light}")
    
    @classmethod
    def set_theme(cls, prefs):
        """
        Set the theme from preferences and reinitialize LVGL theme.
        
        This is a convenience method that loads theme settings from SharedPreferences
        and applies them. It's equivalent to calling init() with the preferences.
        
        Args:
            prefs: SharedPreferences object containing theme settings
        
        Example:
            from mpos import AppearanceManager
            import mpos.config
            
            prefs = mpos.config.SharedPreferences("theme_settings")
            AppearanceManager.set_theme(prefs)
        """
        cls.init(prefs)
    
    # ========== Theme Colors ==========
    
    @classmethod
    def get_primary_color(cls):
        """
        Get the primary theme color.
        
        Returns:
            lv.color_t: The primary color, or None if not set
        
        Example:
            from mpos import AppearanceManager
            
            color = AppearanceManager.get_primary_color()
            if color:
                button.set_style_bg_color(color, lv.PART.MAIN)
        """
        return cls._primary_color
    
    @classmethod
    def set_primary_color(cls, color, prefs=None):
        """
        Set the primary theme color.
        
        Args:
            color (lv.color_t or int): The new primary color
            prefs (SharedPreferences, optional): If provided, saves the setting
        
        Example:
            from mpos import AppearanceManager
            import lvgl as lv
            
            AppearanceManager.set_primary_color(lv.color_hex(0xFF5722))
        """
        cls._primary_color = color
        
        # Save to preferences if provided
        if prefs and isinstance(color, int):
            prefs.set_string("theme_primary_color", f"0x{color:06X}")
        
        print(f"[AppearanceManager] Primary color set to: {color}")
    
    # ========== UI Dimensions ==========
    
    @classmethod
    def get_notification_bar_height(cls):
        """
        Get the height of the notification bar.
        
        The notification bar is the top bar that displays system information
        (time, battery, signal, etc.). This method returns its height in pixels.
        
        Returns:
            int: Height of the notification bar in pixels (default: 24)
        
        Example:
            from mpos import AppearanceManager
            
            bar_height = AppearanceManager.get_notification_bar_height()
            content_y = bar_height  # Position content below the bar
        """
        return cls.NOTIFICATION_BAR_HEIGHT
    
    # ========== Keyboard Styling Workarounds ==========
    
    @classmethod
    def get_keyboard_button_fix_style(cls):
        """
        Get the keyboard button fix style for light mode.
        
        The LVGL default theme applies bg_color_white to keyboard buttons,
        which makes them white-on-white (invisible) in light mode.
        This method returns a custom style to override that.
        
        Returns:
            lv.style_t: Style to apply to keyboard buttons, or None if not needed
        
        Note:
            This is a workaround for an LVGL/MicroPython issue. It only applies
            in light mode. In dark mode, the default LVGL styling is fine.
        
        Example:
            from mpos import AppearanceManager
            
            style = AppearanceManager.get_keyboard_button_fix_style()
            if style:
                keyboard.add_style(style, lv.PART.ITEMS)
        """
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
        """
        Apply keyboard button visibility fix to a keyboard instance.
        
        Call this function after creating a keyboard to ensure buttons
        are visible in light mode.
        
        Args:
            keyboard: The lv.keyboard instance to fix
        
        Example:
            from mpos import AppearanceManager
            import lvgl as lv
            
            keyboard = lv.keyboard(screen)
            AppearanceManager.apply_keyboard_fix(keyboard)
        """
        style = cls.get_keyboard_button_fix_style()
        if style:
            keyboard.add_style(style, lv.PART.ITEMS)
            print(f"[AppearanceManager] Applied keyboard button fix for light mode")
