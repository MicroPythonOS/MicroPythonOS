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

"""

import lvgl as lv
import mpos.ui.theme
from .widget_animator import WidgetAnimator

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
    LABEL_LETTERS = "Abc"
    LABEL_SPACE = " "

    # Keyboard modes - use USER modes for our API
    # We'll also register to standard modes to catch LVGL's internal switches
    MODE_LOWERCASE = lv.keyboard.MODE.USER_1
    MODE_UPPERCASE = lv.keyboard.MODE.USER_2
    MODE_NUMBERS = lv.keyboard.MODE.USER_3
    MODE_SPECIALS = lv.keyboard.MODE.USER_4

    # Lowercase letters
    _lowercase_map = [
        "q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "\n",
        "a", "s", "d", "f", "g", "h", "j", "k", "l", "\n",
        lv.SYMBOL.UP, "z", "x", "c", "v", "b", "n", "m", lv.SYMBOL.BACKSPACE, "\n",
        LABEL_NUMBERS_SPECIALS, ",", LABEL_SPACE, ".", lv.SYMBOL.OK, None
    ]
    _lowercase_ctrl = [lv.buttonmatrix.CTRL.WIDTH_10] * len(_lowercase_map)
    _lowercase_ctrl[29] = lv.buttonmatrix.CTRL.WIDTH_5 # comma
    _lowercase_ctrl[30] = lv.buttonmatrix.CTRL.WIDTH_15 # space
    _lowercase_ctrl[31] = lv.buttonmatrix.CTRL.WIDTH_5 # dot

    # Uppercase letters
    _uppercase_map = [
        "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "\n",
        "A", "S", "D", "F", "G", "H", "J", "K", "L", "\n",
        lv.SYMBOL.DOWN, "Z", "X", "C", "V", "B", "N", "M", lv.SYMBOL.BACKSPACE, "\n",
        LABEL_NUMBERS_SPECIALS, ",", LABEL_SPACE, ".", lv.SYMBOL.OK, None
    ]
    _uppercase_ctrl = [lv.buttonmatrix.CTRL.WIDTH_10] * len(_uppercase_map)
    _uppercase_ctrl[29] = lv.buttonmatrix.CTRL.WIDTH_5 # comma
    _uppercase_ctrl[30] = lv.buttonmatrix.CTRL.WIDTH_15 # space
    _uppercase_ctrl[31] = lv.buttonmatrix.CTRL.WIDTH_5 # dot

    # Numbers and common special characters
    _numbers_map = [
        "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "\n",
        "@", "#", "$", "_", "&", "-", "+", "(", ")", "/", "\n",
        LABEL_SPECIALS, "*", "\"", "'", ":", ";", "!", "?", lv.SYMBOL.BACKSPACE, "\n",
        LABEL_LETTERS, ",", LABEL_SPACE, ".", lv.SYMBOL.OK, None
    ]
    _numbers_ctrl = [lv.buttonmatrix.CTRL.WIDTH_10] * len(_numbers_map)
    _numbers_ctrl[30] = lv.buttonmatrix.CTRL.WIDTH_5 # comma
    _numbers_ctrl[31] = lv.buttonmatrix.CTRL.WIDTH_15 # space
    _numbers_ctrl[32] = lv.buttonmatrix.CTRL.WIDTH_5 # dot

    # Additional special characters with emoticons
    _specials_map = [
        "~", "`", "|", "•", ":-)", ";-)", ":-D", "\n",
        ":-(" , ":'-(", "^", "°", "=", "{", "}", "\\", "\n",
        LABEL_NUMBERS_SPECIALS, "%", ":-o", ":-P", "[", "]", lv.SYMBOL.BACKSPACE, "\n",
        LABEL_LETTERS, "<", LABEL_SPACE, ">", lv.SYMBOL.OK, None
    ]
    _specials_ctrl = [lv.buttonmatrix.CTRL.WIDTH_10] * len(_specials_map)
    _specials_ctrl[15] = lv.buttonmatrix.CTRL.WIDTH_15 # LABEL_NUMBERS_SPECIALS is pretty wide
    _specials_ctrl[23] = lv.buttonmatrix.CTRL.WIDTH_5 # <
    _specials_ctrl[24] = lv.buttonmatrix.CTRL.WIDTH_15 # space
    _specials_ctrl[25] = lv.buttonmatrix.CTRL.WIDTH_5 # >

    # Map modes to their layouts
    mode_info = {
        MODE_LOWERCASE: (_lowercase_map, _lowercase_ctrl),
        MODE_UPPERCASE: (_uppercase_map, _uppercase_ctrl),
        MODE_NUMBERS: (_numbers_map, _numbers_ctrl),
        MODE_SPECIALS: (_specials_map, _specials_ctrl),
    }

    _current_mode = None
    _parent = None # used for scroll_to_y
    _saved_scroll_y = 0
    # Store textarea reference (we DON'T pass it to LVGL to avoid double-typing)
    _textarea = None

    def __init__(self, parent):
        # Create underlying LVGL keyboard widget
        self._keyboard = lv.keyboard(parent)
        self._parent = parent # store it for later
        # self._keyboard.set_popovers(True) # disabled for now because they're quite ugly on LVGL 9.3 - maybe better on 9.4?
        self._keyboard.set_style_text_font(lv.font_montserrat_20,0)

        self.set_mode(self.MODE_LOWERCASE)

        # Remove default event handler(s)
        for index in range(self._keyboard.get_event_count()):
            self._keyboard.remove_event(index)
        self._keyboard.add_event_cb(self._handle_events, lv.EVENT.ALL, None)

        # Apply theme fix for light mode visibility
        mpos.ui.theme.fix_keyboard_button_style(self._keyboard)

        # Set good default height
        self._keyboard.set_style_min_height(175, 0)

    def _handle_events(self, event):
        code = event.get_code()
        #print(f"keyboard event code = {code}")
        if code == lv.EVENT.READY or code == lv.EVENT.CANCEL:
            self.hide_keyboard()
            return
        # Process VALUE_CHANGED events for actual typing
        if code != lv.EVENT.VALUE_CHANGED:
            return

        # Get the pressed button and its text
        target_obj=event.get_target_obj() # keyboard
        if not target_obj:
            return
        button = target_obj.get_selected_button()
        if button is None:
            return
        text = target_obj.get_button_text(button)
        #print(f"[KBD] btn={button}, mode={self._current_mode}, text='{text}'")

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
        elif text ==  lv.SYMBOL.OK:
            self._keyboard.send_event(lv.EVENT.READY, None)
            return
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
        self._textarea.add_event_cb(lambda *args: self.show_keyboard(), lv.EVENT.CLICKED, None)

    def get_textarea(self):
        """
        Get the textarea that this keyboard types into.

        Returns:
            The lv.textarea widget, or None if not connected
        """
        return self._textarea

    def set_mode(self, mode):
        #print(f"[kbc] setting mode to {mode}")
        self._current_mode = mode
        key_map, ctrl_map = self.mode_info[mode]
        self._keyboard.set_map(mode, key_map, ctrl_map)
        self._keyboard.set_mode(mode)

    def scroll_after_show(self, timer):
        #self._textarea.scroll_to_view_recursive(True) # makes sense but doesn't work and breaks the keyboard scroll
        self._keyboard.scroll_to_view_recursive(True)

    def focus_on_keyboard(self, timer=None):
        default_group = lv.group_get_default()
        if default_group:
            from .focus_direction import emulate_focus_obj, move_focus_direction
            emulate_focus_obj(default_group, self._keyboard)

    def scroll_back_after_hide(self, timer):
        self._parent.scroll_to_y(self._saved_scroll_y, True)

    def show_keyboard(self):
        self._saved_scroll_y = self._parent.get_scroll_y()
        WidgetAnimator.smooth_show(self._keyboard, duration=500)
        # Scroll to view on a timer because it will be hidden initially
        lv.timer_create(self.scroll_after_show, 250, None).set_repeat_count(1)
        # When this is done from a timer, focus styling is not applied so the user doesn't see which button is selected.
        # Maybe because there's no active indev anymore?
        # Maybe it will be fixed in an update of LVGL 9.3?
        # focus_timer = lv.timer_create(self.focus_on_keyboard,750,None).set_repeat_count(1)
        # Workaround: show the keyboard immediately and then focus on it - that works, and doesn't seem to flicker as feared:
        self._keyboard.remove_flag(lv.obj.FLAG.HIDDEN)
        self.focus_on_keyboard()

    def hide_keyboard(self):
        WidgetAnimator.smooth_hide(self._keyboard, duration=500)
        # Do this after the hide so the scrollbars disappear automatically if not needed
        scroll_timer = lv.timer_create(self.scroll_back_after_hide,550,None).set_repeat_count(1)

    # Python magic method for automatic method forwarding
    def __getattr__(self, name):
        #print(f"[kbd] __getattr__ {name}")
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
