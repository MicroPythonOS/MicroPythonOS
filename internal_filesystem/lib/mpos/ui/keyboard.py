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
    LABEL_LETTERS = "Abc" # using abc here will trigger the default lv.keyboard() mode switch
    LABEL_SPACE = "     "

    # Keyboard modes - use USER modes for our API
    # We'll also register to standard modes to catch LVGL's internal switches
    CUSTOM_MODE_LOWERCASE = lv.keyboard.MODE.USER_1
    CUSTOM_MODE_UPPERCASE = lv.keyboard.MODE.USER_2
    CUSTOM_MODE_NUMBERS = lv.keyboard.MODE.USER_3
    CUSTOM_MODE_SPECIALS = lv.keyboard.MODE.USER_4

    # Lowercase letters
    _lowercase_map = [
        "q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "\n",
        "a", "s", "d", "f", "g", "h", "j", "k", "l", "\n",
        lv.SYMBOL.UP, "z", "x", "c", "v", "b", "n", "m", lv.SYMBOL.BACKSPACE, "\n",
        LABEL_NUMBERS_SPECIALS, ",", LABEL_SPACE, ".", lv.SYMBOL.NEW_LINE, None
    ]
    _lowercase_ctrl = [10] * len(_lowercase_map)

    # Uppercase letters
    _uppercase_map = [
        "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "\n",
        "A", "S", "D", "F", "G", "H", "J", "K", "L", "\n",
        lv.SYMBOL.DOWN, "Z", "X", "C", "V", "B", "N", "M", lv.SYMBOL.BACKSPACE, "\n",
        LABEL_NUMBERS_SPECIALS, ",", LABEL_SPACE, ".", lv.SYMBOL.NEW_LINE, None
    ]
    _uppercase_ctrl = [10] * len(_uppercase_map)

    # Numbers and common special characters
    _numbers_map = [
        "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "\n",
        "@", "#", "$", "_", "&", "-", "+", "(", ")", "/", "\n",
        LABEL_SPECIALS, "*", "\"", "'", ":", ";", "!", "?", lv.SYMBOL.BACKSPACE, "\n",
        LABEL_LETTERS, ",", LABEL_SPACE, ".", lv.SYMBOL.NEW_LINE, None
    ]
    _numbers_ctrl = [10] * len(_numbers_map)

    # Additional special characters with emoticons
    _specials_map = [
        "~", "`", "|", "•", ":-)", ";-)", ":-D", "\n",
        ":-(" , ":'-(", "^", "°", "=", "{", "}", "\\", "\n",
        LABEL_NUMBERS_SPECIALS, ":-o", ":-P", "[", "]", lv.SYMBOL.BACKSPACE, "\n",
        LABEL_LETTERS, "<", LABEL_SPACE, ">", lv.SYMBOL.NEW_LINE, None
    ]
    _specials_ctrl = [10] * len(_specials_map)

    # Map modes to their layouts
    mode_info = {
        CUSTOM_MODE_LOWERCASE: (_lowercase_map, _lowercase_ctrl),
        CUSTOM_MODE_UPPERCASE: (_uppercase_map, _uppercase_ctrl),
        CUSTOM_MODE_NUMBERS: (_numbers_map, _numbers_ctrl),
        CUSTOM_MODE_SPECIALS: (_specials_map, _specials_ctrl),
    }

    _current_mode = None

    def __init__(self, parent):
        # Create underlying LVGL keyboard widget
        self._keyboard = lv.keyboard(parent)

        # Store textarea reference (we DON'T pass it to LVGL to avoid double-typing)
        self._textarea = None

        self.set_mode(self.CUSTOM_MODE_LOWERCASE)

        self._keyboard.add_event_cb(self._handle_events, lv.EVENT.ALL, None)

        # Apply theme fix for light mode visibility
        mpos.ui.theme.fix_keyboard_button_style(self._keyboard)

        # Set good default height
        self._keyboard.set_style_min_height(165, 0)

    def _handle_events(self, event):
        # Only process VALUE_CHANGED events for actual typing
        if event.get_code() != lv.EVENT.VALUE_CHANGED:
            return

        # Get the pressed button and its text
        target_obj=event.get_target_obj() # keyboard
        if not target_obj:
            return
        button = target_obj.get_selected_button()
        if not button:
            return
        text = target_obj.get_button_text(button)
        print(f"[KBD] btn={button}, mode={self._current_mode}, text='{text}'")

        # Ignore if no valid button text (can happen during mode switching)
        if text is None:
            return

        # Get current textarea content (from our own reference, not LVGL's)
        ta = self._textarea
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
            self.set_mode(self.CUSTOM_MODE_UPPERCASE)
            return  # Don't modify text
        elif text == lv.SYMBOL.DOWN or text == self.LABEL_LETTERS:
            # Switch to lowercase
            self.set_mode(self.CUSTOM_MODE_LOWERCASE)
            return  # Don't modify text
        elif text == self.LABEL_NUMBERS_SPECIALS:
            # Switch to numbers/specials
            self.set_mode(self.CUSTOM_MODE_NUMBERS)
            return  # Don't modify text
        elif text == self.LABEL_SPECIALS:
            # Switch to additional specials
            self.set_mode(self.CUSTOM_MODE_SPECIALS)
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

    def set_textarea(self, textarea):
        """
        Set the textarea that this keyboard types into.

        IMPORTANT: We store the textarea reference ourselves and DON'T pass
        it to the underlying LVGL keyboard. This prevents LVGL's built-in
        automatic character insertion, which would cause double-character bugs
        (LVGL inserts + our handler inserts = double characters).

        Args:
            textarea: The lv.textarea widget to type into, or None to disconnect
        """
        self._textarea = textarea
        # NOTE: We deliberately DO NOT call self._keyboard.set_textarea()
        # to avoid LVGL's automatic character insertion

    def get_textarea(self):
        """
        Get the textarea that this keyboard types into.

        Returns:
            The lv.textarea widget, or None if not connected
        """
        return self._textarea

    def set_mode(self, mode):
        print(f"[kbc] setting mode to {mode}")
        self._current_mode = mode
        key_map, ctrl_map = self.mode_info[mode]
        self._keyboard.set_map(mode, key_map, ctrl_map)
        self._keyboard.set_mode(mode)


    # Python magic method for automatic method forwarding
    def __getattr__(self, name):
        print(f"[kbd] __getattr__ {name}")
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
