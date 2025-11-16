"""
Custom keyboard for MicroPythonOS.

This module provides an enhanced on-screen keyboard with better layout,
more characters (including emoticons), and improved usability compared
to the default LVGL keyboard.

Usage:
    from mpos.ui.keyboard import MposKeyboard

    # Create keyboard
    keyboard = MposKeyboard(parent_obj)
    keyboard.set_textarea(my_textarea)
    keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)

    # Or use factory function for drop-in replacement
    from mpos.ui.keyboard import create_keyboard
    keyboard = create_keyboard(parent_obj, custom=True)
"""

import lvgl as lv
import mpos.ui.theme


class MposKeyboard:
    """
    Enhanced keyboard widget with multiple layouts and emoticons.

    Features:
    - Lowercase and uppercase letter modes
    - Numbers and special characters
    - Additional special characters with emoticons
    - Automatic mode switching
    - Compatible with LVGL keyboard API
    """

    # Keyboard layout labels
    LABEL_NUMBERS_SPECIALS = "?123"
    LABEL_SPECIALS = "=\<"
    LABEL_LETTERS = "abc"
    LABEL_SPACE = "     "

    # Keyboard modes (using LVGL's USER modes)
    MODE_LOWERCASE = lv.keyboard.MODE.USER_1
    MODE_UPPERCASE = lv.keyboard.MODE.USER_2
    MODE_NUMBERS = lv.keyboard.MODE.USER_3
    MODE_SPECIALS = lv.keyboard.MODE.USER_4

    def __init__(self, parent):
        """
        Create a custom keyboard.

        Args:
            parent: Parent LVGL object to attach keyboard to
        """
        # Create underlying LVGL keyboard widget
        self._keyboard = lv.keyboard(parent)

        # Configure layouts
        self._setup_layouts()

        # Set default mode to lowercase
        self._keyboard.set_map(self.MODE_LOWERCASE, self._lowercase_map, self._lowercase_ctrl)
        self._keyboard.set_mode(self.MODE_LOWERCASE)

        # Add event handler for custom behavior
        self._keyboard.add_event_cb(self._handle_events, lv.EVENT.VALUE_CHANGED, None)

        # Apply theme fix for light mode visibility
        mpos.ui.theme.fix_keyboard_button_style(self._keyboard)

        # Set reasonable default height
        self._keyboard.set_style_min_height(145, 0)

    def _setup_layouts(self):
        """Configure all keyboard layout modes."""

        # Lowercase letters
        self._lowercase_map = [
            "q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "\n",
            "a", "s", "d", "f", "g", "h", "j", "k", "l", "\n",
            lv.SYMBOL.UP, "z", "x", "c", "v", "b", "n", "m", lv.SYMBOL.BACKSPACE, "\n",
            self.LABEL_NUMBERS_SPECIALS, ",", self.LABEL_SPACE, ".", lv.SYMBOL.NEW_LINE, None
        ]
        self._lowercase_ctrl = [10] * len(self._lowercase_map)

        # Uppercase letters
        self._uppercase_map = [
            "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "\n",
            "A", "S", "D", "F", "G", "H", "J", "K", "L", "\n",
            lv.SYMBOL.DOWN, "Z", "X", "C", "V", "B", "N", "M", lv.SYMBOL.BACKSPACE, "\n",
            self.LABEL_NUMBERS_SPECIALS, ",", self.LABEL_SPACE, ".", lv.SYMBOL.NEW_LINE, None
        ]
        self._uppercase_ctrl = [10] * len(self._uppercase_map)

        # Numbers and common special characters
        self._numbers_map = [
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "\n",
            "@", "#", "$", "_", "&", "-", "+", "(", ")", "/", "\n",
            self.LABEL_SPECIALS, "*", "\"", "'", ":", ";", "!", "?", lv.SYMBOL.BACKSPACE, "\n",
            self.LABEL_LETTERS, ",", self.LABEL_SPACE, ".", lv.SYMBOL.NEW_LINE, None
        ]
        self._numbers_ctrl = [10] * len(self._numbers_map)

        # Additional special characters with emoticons
        self._specials_map = [
            "~", "`", "|", "•", ":-)", ";-)", ":-D", "\n",
            ":-(" , ":'-(", "^", "°", "=", "{", "}", "\\", "\n",
            self.LABEL_NUMBERS_SPECIALS, ":-o", ":-P", "[", "]", lv.SYMBOL.BACKSPACE, "\n",
            self.LABEL_LETTERS, "<", self.LABEL_SPACE, ">", lv.SYMBOL.NEW_LINE, None
        ]
        self._specials_ctrl = [10] * len(self._specials_map)

    def _handle_events(self, event):
        """
        Handle keyboard button presses.

        Args:
            event: LVGL event object
        """
        # Get the pressed button and its text
        button = self._keyboard.get_selected_button()
        text = self._keyboard.get_button_text(button)

        # Get current textarea content
        ta = self._keyboard.get_textarea()
        if not ta:
            return

        current_text = ta.get_text()
        new_text = current_text

        # Handle special keys
        if text == lv.SYMBOL.BACKSPACE:
            # Delete last character
            new_text = current_text[:-1]

        elif text == lv.SYMBOL.UP:
            # Switch to uppercase
            self._keyboard.set_map(self.MODE_UPPERCASE, self._uppercase_map, self._uppercase_ctrl)
            self._keyboard.set_mode(self.MODE_UPPERCASE)
            return  # Don't modify text

        elif text == lv.SYMBOL.DOWN or text == self.LABEL_LETTERS:
            # Switch to lowercase
            self._keyboard.set_map(self.MODE_LOWERCASE, self._lowercase_map, self._lowercase_ctrl)
            self._keyboard.set_mode(self.MODE_LOWERCASE)
            return  # Don't modify text

        elif text == self.LABEL_NUMBERS_SPECIALS:
            # Switch to numbers/specials
            self._keyboard.set_map(self.MODE_NUMBERS, self._numbers_map, self._numbers_ctrl)
            self._keyboard.set_mode(self.MODE_NUMBERS)
            return  # Don't modify text

        elif text == self.LABEL_SPECIALS:
            # Switch to additional specials
            self._keyboard.set_map(self.MODE_SPECIALS, self._specials_map, self._specials_ctrl)
            self._keyboard.set_mode(self.MODE_SPECIALS)
            return  # Don't modify text

        elif text == self.LABEL_SPACE:
            # Space bar
            new_text = current_text + " "

        elif text == lv.SYMBOL.NEW_LINE:
            # Handle newline (only for multi-line textareas)
            if ta.get_one_line():
                # For single-line, trigger READY event
                self._keyboard.send_event(lv.EVENT.READY, None)
                return
            else:
                new_text = current_text + "\n"

        else:
            # Regular character
            new_text = current_text + text

        # Update textarea
        ta.set_text(new_text)

    def set_mode(self, mode):
        """
        Set keyboard mode with proper map configuration.

        This method ensures set_map() is called before set_mode() to prevent
        LVGL crashes when switching between custom keyboard modes.

        Args:
            mode: One of MODE_LOWERCASE, MODE_UPPERCASE, MODE_NUMBERS, MODE_SPECIALS
        """
        # Map mode constants to their corresponding map arrays
        mode_maps = {
            self.MODE_LOWERCASE: (self._lowercase_map, self._lowercase_ctrl),
            self.MODE_UPPERCASE: (self._uppercase_map, self._uppercase_ctrl),
            self.MODE_NUMBERS: (self._numbers_map, self._numbers_ctrl),
            self.MODE_SPECIALS: (self._specials_map, self._specials_ctrl),
        }

        if mode in mode_maps:
            key_map, ctrl_map = mode_maps[mode]
            self._keyboard.set_map(mode, key_map, ctrl_map)

        self._keyboard.set_mode(mode)

    # ========================================================================
    # Python magic method for automatic method forwarding
    # ========================================================================

    def __getattr__(self, name):
        """
        Forward any undefined method/attribute to the underlying LVGL keyboard.

        This allows MposKeyboard to support ALL lv.keyboard methods automatically
        without needing to manually wrap each one. Any method not defined on
        MposKeyboard will be forwarded to self._keyboard.

        Examples:
            keyboard.set_textarea(ta)       # Works
            keyboard.align(lv.ALIGN.CENTER) # Works
            keyboard.set_style_opa(128, 0)  # Works
            keyboard.any_lvgl_method()      # Works!
        """
        # Forward to the underlying keyboard object
        return getattr(self._keyboard, name)

    def get_lvgl_obj(self):
        """
        Get the underlying LVGL keyboard object.

        This is now rarely needed since __getattr__ forwards everything automatically.
        Kept for backwards compatibility.
        """
        return self._keyboard


def create_keyboard(parent, custom=False):
    """
    Factory function to create a keyboard.

    This provides a simple way to switch between standard LVGL keyboard
    and custom keyboard.

    Args:
        parent: Parent LVGL object
        custom: If True, create MposKeyboard; if False, create standard lv.keyboard

    Returns:
        MposKeyboard instance or lv.keyboard instance

    Example:
        # Use custom keyboard
        keyboard = create_keyboard(screen, custom=True)

        # Use standard LVGL keyboard
        keyboard = create_keyboard(screen, custom=False)
    """
    if custom:
        return MposKeyboard(parent)
    else:
        keyboard = lv.keyboard(parent)
        mpos.ui.theme.fix_keyboard_button_style(keyboard)
        return keyboard
