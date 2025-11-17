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
import time


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

    # Keyboard modes - use USER modes for our API
    # We'll also register to standard modes to catch LVGL's internal switches
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

        # Store textarea reference (we DON'T pass it to LVGL to avoid double-typing)
        self._textarea = None

        # Track last mode switch time to prevent race conditions
        # When user rapidly clicks mode buttons, button indices can get confused
        # because index 29 is "abc" in numbers mode but "," in lowercase mode
        self._last_mode_switch_time = 0

        # Re-entrancy guard to prevent recursive event processing during mode switches
        self._in_mode_switch = False

        # Configure layouts
        self._setup_layouts()

        # Set default mode to lowercase
        # IMPORTANT: We do NOT call set_map() here in __init__.
        # Instead, set_mode() will call set_map() immediately before set_mode().
        # This matches the proof-of-concept pattern and prevents crashes from
        # calling set_map() multiple times which can corrupt button matrix state.
        self.set_mode(self.MODE_LOWERCASE)

        # Add event handler for custom behavior
        # We need to handle ALL events to catch mode changes that LVGL might trigger
        self._keyboard.add_event_cb(self._handle_events, lv.EVENT.ALL, None)

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
        event_code = event.get_code()

        # Intercept READY event to prevent LVGL from changing modes
        if event_code == lv.EVENT.READY:
            # Stop LVGL from processing READY (which might trigger mode changes)
            event.stop_processing()
            # Forward READY event to external handlers if needed
            return

        # Intercept CANCEL event similarly
        if event_code == lv.EVENT.CANCEL:
            event.stop_processing()
            return

        # Only process VALUE_CHANGED events for actual typing
        if event_code != lv.EVENT.VALUE_CHANGED:
            return

        # Stop event propagation FIRST, before doing anything else
        # This prevents LVGL's default handler from interfering
        event.stop_processing()

        # Re-entrancy guard: Skip processing if we're currently switching modes
        # This prevents set_mode() from triggering recursive event processing
        if self._in_mode_switch:
            return

        # Get the pressed button and its text
        button = self._keyboard.get_selected_button()
        current_mode = self._keyboard.get_mode()
        text = self._keyboard.get_button_text(button)

        # DEBUG
        print(f"[KBD] btn={button}, mode={current_mode}, text='{text}'")

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
            self.set_mode(self.MODE_UPPERCASE)
            return  # Don't modify text

        elif text == lv.SYMBOL.DOWN or text == self.LABEL_LETTERS:
            # Switch to lowercase
            self.set_mode(self.MODE_LOWERCASE)
            return  # Don't modify text

        elif text == self.LABEL_NUMBERS_SPECIALS:
            # Switch to numbers/specials
            self.set_mode(self.MODE_NUMBERS)
            return  # Don't modify text

        elif text == self.LABEL_SPECIALS:
            # Switch to additional specials
            self.set_mode(self.MODE_SPECIALS)
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
        """
        Set keyboard mode with proper map configuration.

        This method ensures set_map() is called before set_mode() to prevent
        LVGL crashes when switching between custom keyboard modes.

        Args:
            mode: One of MODE_LOWERCASE, MODE_UPPERCASE, MODE_NUMBERS, MODE_SPECIALS
                  (can also accept standard LVGL modes)
        """
        # Map modes to their layouts
        mode_info = {
            self.MODE_LOWERCASE: (self._lowercase_map, self._lowercase_ctrl),
            self.MODE_UPPERCASE: (self._uppercase_map, self._uppercase_ctrl),
            self.MODE_NUMBERS: (self._numbers_map, self._numbers_ctrl),
            self.MODE_SPECIALS: (self._specials_map, self._specials_ctrl),
        }

        # Set re-entrancy guard to block any events triggered during mode switch
        self._in_mode_switch = True

        try:
            # Set the map for the new mode BEFORE calling set_mode()
            # This prevents crashes from set_mode() being called with no map set
            if mode in mode_info:
                key_map, ctrl_map = mode_info[mode]
                self._keyboard.set_map(mode, key_map, ctrl_map)

            # Now switch to the new mode
            self._keyboard.set_mode(mode)
        finally:
            # Always clear the guard, even if an exception occurs
            self._in_mode_switch = False

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
