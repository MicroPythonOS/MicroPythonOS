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
    keyboard.add_flag(lv.obj.FLAG.HIDDEN) # shows up when textarea is clicked

"""

import logging
import lvgl as lv

from . import focus_direction
from .appearance_manager import AppearanceManager
from .font_manager import FontManager
from .widget_animator import WidgetAnimator

logger = logging.getLogger(__name__)

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
    LABEL_SPECIALS = "=\\<"
    LABEL_LETTERS = "Abc"
    LABEL_SPACE = " "
    LABEL_EMOJI = "emoji"

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
        LABEL_NUMBERS_SPECIALS, ",", LABEL_SPACE, ".", lv.SYMBOL.OK, lv.SYMBOL.NEW_LINE, None
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
        LABEL_NUMBERS_SPECIALS, ",", LABEL_SPACE, ".", lv.SYMBOL.OK, lv.SYMBOL.NEW_LINE, None
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
        LABEL_LETTERS, ",", LABEL_EMOJI, LABEL_SPACE, ".", lv.SYMBOL.OK, lv.SYMBOL.NEW_LINE, None
    ]
    _numbers_ctrl = [lv.buttonmatrix.CTRL.WIDTH_10] * len(_numbers_map)
    _numbers_ctrl[30] = lv.buttonmatrix.CTRL.WIDTH_5 # comma
    _numbers_ctrl[31] = lv.buttonmatrix.CTRL.WIDTH_5 # emoji
    _numbers_ctrl[32] = lv.buttonmatrix.CTRL.WIDTH_10 # space
    _numbers_ctrl[33] = lv.buttonmatrix.CTRL.WIDTH_5 # dot

    # Additional special characters with emoticons
    _specials_map = [
        "~", "`", "|", "•", "🙂", "😉", "😆", "\n",
        "😒", "😭", "^", "°", "=", "{", "}", "\\", "\n",
        LABEL_NUMBERS_SPECIALS, "%", "😱", "😋", "[", "]", lv.SYMBOL.BACKSPACE, "\n",
        LABEL_LETTERS, "<", LABEL_EMOJI, LABEL_SPACE, ">", lv.SYMBOL.OK, lv.SYMBOL.NEW_LINE, None
    ]
    _specials_ctrl = [lv.buttonmatrix.CTRL.WIDTH_10] * len(_specials_map)
    _specials_ctrl[15] = lv.buttonmatrix.CTRL.WIDTH_15 # LABEL_NUMBERS_SPECIALS is pretty wide
    _specials_ctrl[23] = lv.buttonmatrix.CTRL.WIDTH_5 # <
    _specials_ctrl[24] = lv.buttonmatrix.CTRL.WIDTH_5 # emoji
    _specials_ctrl[25] = lv.buttonmatrix.CTRL.WIDTH_10 # space
    _specials_ctrl[26] = lv.buttonmatrix.CTRL.WIDTH_5 # >

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
    _textarea_emoji_font_applied = False
    # Optional callbacks invoked when the keyboard is shown/hidden.
    _on_show = None
    _on_hide = None

    _EMOJI_COLUMNS = 8

    def __init__(self, parent):
        # Initialize references early: event callbacks (e.g. for the focus
        # overlay) may fire while the constructor is still building the widget.
        self._parent = None
        self._keyboard = None
        self._keyboard_indicator = None
        self._emoji_pane = None
        self._emoji_buttons = None
        self._emoji_indicator = None
        self._textarea = None

        # Create underlying LVGL buttonmatrix widget.
        # We use a plain buttonmatrix (instead of lv.keyboard) so each key
        # can be individually focused by focus_direction like any other widget.
        self._keyboard = lv.buttonmatrix(parent)
        self._parent = parent # store it for later
        keyboard_font = FontManager.getFont(20, emoji=True)
        self._keyboard.set_style_text_font(keyboard_font, lv.PART.MAIN)
        self._keyboard.set_style_text_font(keyboard_font, lv.PART.ITEMS)

        self.set_mode(self.MODE_LOWERCASE)

        # Use the full display width and maximize key size by removing the
        # matrix padding that otherwise shrinks the button area.
        self._keyboard.set_width(lv.pct(100))
        self._keyboard.set_style_pad_all(0, lv.PART.MAIN)
        self._keyboard.set_style_pad_row(2, lv.PART.MAIN)
        self._keyboard.set_style_pad_column(2, lv.PART.MAIN)

        # Add our input handler alongside the default buttonmatrix handler.
        # We keep LVGL's default handler so directional KEY events continue to
        # navigate individual buttons inside the matrix; we suppress the
        # VALUE_CHANGED events it generates during focus_direction navigation.
        self._keyboard.add_event_cb(self._handle_events, lv.EVENT.ALL, None)

        # Apply theme fix for light mode visibility
        AppearanceManager.apply_keyboard_fix(self._keyboard)

        # The default buttonmatrix theme does not draw a per-key focus border,
        # so we overlay a small box on top of the currently selected button.
        self._keyboard_indicator = self._create_matrix_indicator(self._keyboard)
        self._keyboard.add_event_cb(self._on_matrix_event, lv.EVENT.ALL, None)

        # Set good default height
        self._keyboard.set_style_min_height(175, lv.PART.MAIN)

        # Build a scrollable emoji pane layered above the keyboard grid.
        self._emoji_pane = lv.obj(self._keyboard)
        self._emoji_pane.set_size(lv.pct(100), lv.pct(100))
        self._emoji_pane.align(lv.ALIGN.TOP_MID, 0, 0)
        self._emoji_pane.add_flag(lv.obj.FLAG.HIDDEN)
        self._emoji_pane.set_style_bg_color(lv.color_hex(0x202020), lv.PART.MAIN)
        self._emoji_pane.set_style_bg_opa(lv.OPA.COVER, lv.PART.MAIN)
        self._emoji_pane.set_style_pad_all(0, lv.PART.MAIN)
        self._emoji_pane.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        self._emoji_buttons = lv.buttonmatrix(self._emoji_pane)
        self._emoji_buttons.set_size(lv.pct(100), lv.pct(100))
        self._emoji_buttons.set_style_pad_all(0, lv.PART.MAIN)
        self._emoji_buttons.set_style_pad_row(2, lv.PART.MAIN)
        self._emoji_buttons.set_style_pad_column(2, lv.PART.MAIN)
        emoji_font = FontManager.getFont(24, emoji=True)
        self._emoji_buttons.set_style_text_font(emoji_font, lv.PART.ITEMS)
        self._emoji_buttons.set_style_text_font(emoji_font, lv.PART.MAIN)
        self._emoji_buttons.add_event_cb(self._handle_emoji_events, lv.EVENT.ALL, None)
        self._emoji_indicator = self._create_matrix_indicator(self._emoji_buttons)
        self._emoji_buttons.add_event_cb(self._on_matrix_event, lv.EVENT.ALL, None)
        self._build_emoji_map()

    def _build_emoji_map(self):
        """Populate the emoji pane's button matrix from supported emoji strings."""
        emojis = FontManager.getEmojiStrings()
        key_map = [self.LABEL_LETTERS]
        ctrl_map = [lv.buttonmatrix.CTRL.WIDTH_10]
        for emoji in emojis:
            key_map.append(emoji)
            ctrl_map.append(lv.buttonmatrix.CTRL.WIDTH_10)
            if len(key_map) % (self._EMOJI_COLUMNS + 1) == 0:
                key_map.append("\n")
                ctrl_map.append(lv.buttonmatrix.CTRL.WIDTH_10)
        key_map.append(None)
        self._emoji_map = key_map
        self._emoji_ctrl = ctrl_map
        self._emoji_buttons.set_map(self._emoji_map)
        try:
            self._emoji_buttons.set_ctrl_map(self._emoji_ctrl)
        except Exception:
            pass
        focus_direction.register_buttonmatrix(self._emoji_buttons, self._emoji_map, self._emoji_ctrl)
        self._last_emoji_press = 0

    def _handle_emoji_events(self, event):
        code = event.get_code()
        if code == lv.EVENT.READY or code == lv.EVENT.CANCEL:
            self.hide_keyboard()
            return
        # Ignore programmatic selection changes from focus_direction.
        if (code == lv.EVENT.VALUE_CHANGED
                and focus_direction.suppress_keyboard_event(self._emoji_buttons)):
            return
        if code != lv.EVENT.VALUE_CHANGED:
            return

        # Debounce the phantom asynchronous event that set_map() can generate.
        now = lv.tick_get()
        if now - self._last_emoji_press < 50:
            return
        self._last_emoji_press = now

        target_obj = event.get_target_obj()
        if not target_obj:
            return
        button = target_obj.get_selected_button()
        if button is None:
            return
        text = target_obj.get_button_text(button)
        if text is None:
            return

        if text == self.LABEL_LETTERS:
            self._hide_emoji_pane()
            self.set_mode(self.MODE_LOWERCASE)
            return

        ta = self._textarea
        if ta:
            ta.set_text(ta.get_text() + text)
            self._ensure_textarea_emoji_font(ta, text)

    def _set_emoji_focus(self, emoji_active):
        """Swap the default input group between the keyboard and emoji pane."""
        group = lv.group_get_default()
        if not group:
            return
        if emoji_active:
            try:
                lv.group_remove_obj(self._keyboard)
            except Exception:
                pass
            group.add_obj(self._emoji_buttons)
            lv.group_focus_obj(self._emoji_buttons)
        else:
            try:
                lv.group_remove_obj(self._emoji_buttons)
            except Exception:
                pass
            group.add_obj(self._keyboard)
            lv.group_focus_obj(self._keyboard)

    def _show_emoji_pane(self):
        self._emoji_pane.remove_flag(lv.obj.FLAG.HIDDEN)
        self._emoji_pane.move_foreground()
        self._set_emoji_focus(True)

    def _hide_emoji_pane(self):
        self._emoji_pane.add_flag(lv.obj.FLAG.HIDDEN)
        self._set_emoji_focus(False)

    def _handle_events(self, event):
        code = event.get_code()

        if code == lv.EVENT.READY or code == lv.EVENT.CANCEL:
            self.hide_keyboard()
            return
        # Ignore programmatic selection changes from focus_direction.
        if (code == lv.EVENT.VALUE_CHANGED
                and focus_direction.suppress_keyboard_event(self._keyboard)):
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
        elif text == self.LABEL_EMOJI:
            # Show the emoji selection pane
            self._show_emoji_pane()
            return
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
            self._ensure_textarea_emoji_font(ta, text)

        # Update textarea
        ta.set_text(new_text)

    def _create_matrix_indicator(self, parent):
        """Create a focused-button overlay for a buttonmatrix."""
        ind = lv.obj(parent)
        ind.remove_flag(lv.obj.FLAG.SCROLLABLE)
        ind.remove_flag(lv.obj.FLAG.CLICKABLE)
        ind.add_flag(lv.obj.FLAG.FLOATING)
        ind.add_flag(lv.obj.FLAG.HIDDEN)
        ind.set_style_bg_color(lv.palette_main(lv.PALETTE.YELLOW), lv.PART.MAIN)
        ind.set_style_bg_opa(lv.OPA._30, lv.PART.MAIN)
        ind.set_style_border_width(3, lv.PART.MAIN)
        ind.set_style_border_color(lv.palette_main(lv.PALETTE.YELLOW), lv.PART.MAIN)
        ind.set_style_radius(4, lv.PART.MAIN)
        ind.set_style_pad_all(0, lv.PART.MAIN)
        return ind

    def _update_matrix_indicator(self, matrix, indicator):
        """Move/show the overlay to match the matrix's currently selected button."""
        if indicator is None:
            return
        group = lv.group_get_default()
        if not group or group.get_focused() is not matrix:
            indicator.add_flag(lv.obj.FLAG.HIDDEN)
            return
        btn = matrix.get_selected_button()
        if btn is None or btn < 0 or btn >= 0xFFFF:
            indicator.add_flag(lv.obj.FLAG.HIDDEN)
            return
        rect = focus_direction.get_matrix_button_rect(matrix, btn)
        if rect is None:
            indicator.add_flag(lv.obj.FLAG.HIDDEN)
            return
        area = lv.area_t()
        matrix.get_coords(area)
        rel_x = rect[0] - area.x1
        rel_y = rect[1] - area.y1
        indicator.set_pos(rel_x, rel_y)
        indicator.set_size(rect[2] - rect[0] + 1, rect[3] - rect[1] + 1)
        indicator.remove_flag(lv.obj.FLAG.HIDDEN)
        indicator.move_foreground()

    def _on_matrix_event(self, event):
        """Keep the focus indicator aligned with the selected matrix button."""
        code = event.get_code()
        if code not in (
            lv.EVENT.VALUE_CHANGED,
            lv.EVENT.FOCUSED,
            lv.EVENT.DEFOCUSED,
            lv.EVENT.KEY,
        ):
            return
        if self._keyboard_indicator is None or self._emoji_indicator is None:
            return
        target = event.get_target_obj()
        if target is self._keyboard:
            self._update_matrix_indicator(self._keyboard, self._keyboard_indicator)
        elif target is self._emoji_buttons:
            self._update_matrix_indicator(self._emoji_buttons, self._emoji_indicator)

    def _without_newline_key(self, key_map, ctrl_map):
        """
        Return copies of the key/control maps with the bottom-right NEW_LINE
        button removed. Used when the keyboard is attached to a single-line
        textarea.
        """
        key_map = list(key_map)
        ctrl_map = list(ctrl_map)
        # NEW_LINE is always the second-to-last item before the sentinel None.
        if len(key_map) >= 2 and key_map[-2] == lv.SYMBOL.NEW_LINE:
            del key_map[-2]
            del ctrl_map[-2]
        return key_map, ctrl_map

    def _single_line_mode_info(self):
        """Return mode_info maps stripped of the newline key for all modes."""
        return {
            self.MODE_LOWERCASE: self._without_newline_key(self._lowercase_map, self._lowercase_ctrl),
            self.MODE_UPPERCASE: self._without_newline_key(self._uppercase_map, self._uppercase_ctrl),
            self.MODE_NUMBERS: self._without_newline_key(self._numbers_map, self._numbers_ctrl),
            self.MODE_SPECIALS: self._without_newline_key(self._specials_map, self._specials_ctrl),
        }

    def set_textarea(self, textarea, on_show=None, on_hide=None):
        """
        Set the textarea that this keyboard types into.

        IMPORTANT: We store the textarea reference ourselves and DON'T pass
        it to the underlying LVGL keyboard. This prevents LVGL's built-in
        automatic character insertion, which would cause double-character bugs
        (LVGL inserts + our handler inserts = double characters).

        Args:
            textarea: The lv.textarea widget to type into, or None to disconnect
            on_show: Optional callback invoked when the keyboard is shown
            on_hide: Optional callback invoked after the keyboard is hidden
        """
        self._textarea = textarea
        self._textarea_emoji_font_applied = False
        self._on_show = on_show
        self._on_hide = on_hide

        # The newline key is only meaningful for multi-line textareas.
        if textarea is not None and textarea.get_one_line():
            self.mode_info = self._single_line_mode_info()
        else:
            self.mode_info = dict(type(self).mode_info)

        # NOTE: We deliberately DO NOT call self._keyboard.set_textarea()
        # to avoid LVGL's automatic character insertion
        self._textarea.add_event_cb(lambda *args: self.show_keyboard(), lv.EVENT.CLICKED, None)

        # Apply the selected maps by refreshing the current mode.
        self.set_mode(self._current_mode if self._current_mode is not None else self.MODE_LOWERCASE)

    def _ensure_textarea_emoji_font(self, textarea, text):
        if self._textarea_emoji_font_applied:
            return
        if not self._contains_emoji(text):
            return

        current_font = None
        try:
            current_font = textarea.get_style_text_font(lv.PART.MAIN)
        except Exception:
            pass

        family = None
        size = 12
        if current_font is not None:
            base_font = current_font
            try:
                fallback_font = current_font.fallback
                if fallback_font is not None:
                    base_font = fallback_font
            except Exception:
                pass

            for record in FontManager._get_builtin_font_records():
                if record["font"] is base_font:
                    family = record["family"]
                    size = record["size"]
                    break

            if family is None:
                try:
                    size = max(1, int(base_font.get_line_height()))
                except Exception:
                    pass

        emoji_font = FontManager.getFont(size=size, family=family, emoji=True)
        textarea.set_style_text_font(emoji_font, lv.PART.MAIN)
        self._textarea_emoji_font_applied = True

    def _contains_emoji(self, text):
        if not text:
            return False

        emoji_codepoints = FontManager.getEmojiCodepoints()
        if not emoji_codepoints:
            return False

        for char in text:
            if ord(char) in emoji_codepoints:
                return True
        return False

    def get_textarea(self):
        """
        Get the textarea that this keyboard types into.

        Returns:
            The lv.textarea widget, or None if not connected
        """
        return self._textarea

    def set_mode(self, mode):
        self._current_mode = mode
        key_map, ctrl_map = self.mode_info[mode]
        self._keyboard.set_map(key_map)
        # Trim the trailing None sentinel (if any) before passing control widths.
        if ctrl_map and ctrl_map[-1] is None:
            ctrl_map = ctrl_map[:-1]
        self._keyboard.set_ctrl_map(ctrl_map)
        focus_direction.update_buttonmatrix(self._keyboard, key_map, ctrl_map)

    def scroll_after_show(self, timer):
        #self._textarea.scroll_to_view_recursive(True) # makes sense but doesn't work and breaks the keyboard scroll
        self._keyboard.scroll_to_view_recursive(True)

    def focus_on_keyboard(self, timer=None):
        default_group = lv.group_get_default()
        if default_group:
            lv.group_focus_obj(self._keyboard)

    def scroll_back_after_hide(self, timer):
        self._parent.scroll_to_y(self._saved_scroll_y, True)
        if self._on_hide:
            self._on_hide()

    def show_keyboard(self):
        if self._on_show:
            self._on_show()
        self._hide_emoji_pane()
        self._saved_scroll_y = self._parent.get_scroll_y()
        WidgetAnimator.smooth_show(self._keyboard, duration=500)
        # Scroll to view on a timer because it will be hidden initially
        lv.timer_create(self.scroll_after_show, 250, None).set_repeat_count(1)
        # When this is done from a timer, focus styling is not applied so the user doesn't see which button is selected.
        # Maybe because there's no active indev anymore?
        # Maybe it will be fixed in an update of LVGL 9.4 to a later version?
        # lv.timer_create(self.focus_on_keyboard,750,None).set_repeat_count(1)
        # Workaround: show the keyboard immediately and then focus on it - that works, and doesn't seem to flicker as feared:
        self._keyboard.remove_flag(lv.obj.FLAG.HIDDEN)
        self.focus_on_keyboard()

    def hide_keyboard(self):
        self._hide_emoji_pane()
        WidgetAnimator.smooth_hide(self._keyboard, duration=500)
        # Do this after the hide so the scrollbars disappear automatically if not needed
        scroll_timer = lv.timer_create(self.scroll_back_after_hide,550,None).set_repeat_count(1)

    # Python magic method for automatic method forwarding
    def __getattr__(self, name):
        """
        Forward any undefined method/attribute to the underlying LVGL keyboard.

        This allows MposKeyboard to support ALL lv.keyboard methods automatically
        without needing to manually wrap each one. Any method not defined on
        MposKeyboard will be forwarded to self._keyboard.

        Examples:
            keyboard.set_textarea(ta)       # Works
            keyboard.align(lv.ALIGN.CENTER) # Works
            keyboard.set_style_opa(128, lv.PART.MAIN)  # Works
            keyboard.any_lvgl_method()      # Works!
        """
        # Forward to the underlying keyboard object
        return getattr(self._keyboard, name)
