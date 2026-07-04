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

from . import focus
from .appearance_manager import AppearanceManager
from .font_manager import FontManager
from .widget_animator import WidgetAnimator

logger = logging.getLogger(__name__)


def _key_text(token):
    """Return the display text for a key layout token."""
    if isinstance(token, tuple):
        return token[0]
    return token


def _key_grow(token):
    """Return the flex-grow weight for a key layout token."""
    if isinstance(token, tuple) and len(token) > 1:
        return token[1]
    return 1


def _clear_bg_border_padding(obj):
    """Remove theme padding, margins, borders and background from a container."""
    obj.set_style_pad_all(0, lv.PART.MAIN)
    obj.set_style_pad_row(0, lv.PART.MAIN)
    obj.set_style_pad_column(0, lv.PART.MAIN)
    obj.set_style_margin_all(0, lv.PART.MAIN)
    obj.set_style_border_width(0, lv.PART.MAIN)
    obj.set_style_outline_width(0, lv.PART.MAIN)
    obj.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)


def _strip_button_theme(btn):
    """Remove theme margins, borders and shadows that create gaps around a key."""
    btn.set_style_margin_all(0, lv.PART.MAIN)
    btn.set_style_border_width(0, lv.PART.MAIN)
    btn.set_style_outline_width(0, lv.PART.MAIN)
    btn.set_style_outline_pad(0, lv.PART.MAIN)
    btn.set_style_shadow_width(0, lv.PART.MAIN)
    btn.set_style_shadow_spread(0, lv.PART.MAIN)
    return btn


def _key_normal_bg_color():
    """Return the unfocused key background color for the current theme."""
    if AppearanceManager.is_light_mode():
        return lv.palette_lighten(lv.PALETTE.GREY, 2)
    return lv.palette_darken(lv.PALETTE.GREY, 3)


def _key_focus_bg_color():
    """Return the focused key background color."""
    color = AppearanceManager.get_primary_color()
    if color is None:
        color = lv.theme_get_color_primary(None)
    return color


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

    # Keyboard modes
    MODE_LOWERCASE = lv.keyboard.MODE.USER_1
    MODE_UPPERCASE = lv.keyboard.MODE.USER_2
    MODE_NUMBERS = lv.keyboard.MODE.USER_3
    MODE_SPECIALS = lv.keyboard.MODE.USER_4

    # Width numbers are flex-grow weights, not pixels or percentages.
    _lowercase_layout = (
        ("q", "w", "e", "r", "t", "y", "u", "i", "o", "p"),
        ("a", "s", "d", "f", "g", "h", "j", "k", "l"),
        ((lv.SYMBOL.UP, 2), "z", "x", "c", "v", "b", "n", "m", (lv.SYMBOL.BACKSPACE, 2)),
        ((LABEL_NUMBERS_SPECIALS, 2), (",", 1), (LABEL_SPACE, 4), (".", 1), (lv.SYMBOL.OK, 1), (lv.SYMBOL.NEW_LINE, 1)),
    )

    _uppercase_layout = (
        ("Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"),
        ("A", "S", "D", "F", "G", "H", "J", "K", "L"),
        ((lv.SYMBOL.DOWN, 2), "Z", "X", "C", "V", "B", "N", "M", (lv.SYMBOL.BACKSPACE, 2)),
        ((LABEL_NUMBERS_SPECIALS, 2), (",", 1), (LABEL_SPACE, 4), (".", 1), (lv.SYMBOL.OK, 1), (lv.SYMBOL.NEW_LINE, 1)),
    )

    _numbers_layout = (
        ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0"),
        ("@", "#", "$", "_", "&", "-", "+", "(", ")", "/"),
        ((LABEL_SPECIALS, 2), "*", "\"", "'", ":", ";", "!", "?", (lv.SYMBOL.BACKSPACE, 2)),
        ((LABEL_LETTERS, 2), (",", 1), (LABEL_EMOJI, 1), (LABEL_SPACE, 3), (".", 1), (lv.SYMBOL.OK, 1), (lv.SYMBOL.NEW_LINE, 1)),
    )

    _specials_layout = (
        ("~", "`", "|", "•", "🙂", "😉", "😆"),
        ("😒", "😭", "^", "°", "=", "{", "}", "\\"),
        ((LABEL_NUMBERS_SPECIALS, 2), "%", "😱", "😋", "[", "]", lv.SYMBOL.BACKSPACE),
        ((LABEL_LETTERS, 2), ("<", 1), (LABEL_EMOJI, 1), (LABEL_SPACE, 2), (">", 1), (lv.SYMBOL.OK, 1), (lv.SYMBOL.NEW_LINE, 1)),
    )

    mode_info = {
        MODE_LOWERCASE: _lowercase_layout,
        MODE_UPPERCASE: _uppercase_layout,
        MODE_NUMBERS: _numbers_layout,
        MODE_SPECIALS: _specials_layout,
    }

    _current_mode = None
    _parent = None  # used for scroll_to_y
    _saved_scroll_y = 0
    # Store textarea reference (we DON'T pass it to LVGL to avoid double-typing)
    _textarea = None
    _textarea_emoji_font_applied = False
    # Optional callbacks invoked when the keyboard is shown/hidden.
    _on_show = None
    _on_hide = None

    _EMOJI_COLUMNS = 8

    def __init__(self, parent):
        self._parent = parent
        self._current_mode = None
        self._textarea = None
        self._textarea_emoji_font_applied = False
        self._on_show = None
        self._on_hide = None
        self._saved_scroll_y = 0

        # Keyboard key state
        self._keys = []
        self._row_containers = []

        # Emoji pane state
        self._emoji_pane = None
        self._emoji_buttons = []

        # Create underlying LVGL container widget.
        self._keyboard = lv.obj(parent)
        self._keyboard.set_width(lv.pct(100))
        self._keyboard.set_height(lv.SIZE_CONTENT)
        self._keyboard.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        _clear_bg_border_padding(self._keyboard)

        self.mode_info = dict(type(self).mode_info)

        keyboard_font = FontManager.getFont(20, emoji=True)
        self._keyboard.set_style_text_font(keyboard_font, lv.PART.MAIN)

        self.set_mode(self.MODE_LOWERCASE)

        # Apply theme fix for light mode visibility
        AppearanceManager.apply_keyboard_fix(self._keyboard)

        # Build the emoji pane in the same slot as the keyboard rows.
        self._emoji_pane = lv.obj(self._keyboard)
        self._emoji_pane.set_width(lv.pct(100))
        self._emoji_pane.set_height(lv.SIZE_CONTENT)
        self._emoji_pane.add_flag(lv.obj.FLAG.HIDDEN)
        self._emoji_pane.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        _clear_bg_border_padding(self._emoji_pane)

        self._build_emoji_pane()

    def _build_emoji_pane(self):
        """Populate the emoji pane: Abc button plus clickable emoji labels."""
        # Clear any previous widgets (used when rebuilding)
        for btn in self._emoji_buttons:
            btn.delete()
        self._emoji_buttons = []
        while self._emoji_pane.get_child_count():
            self._emoji_pane.get_child(0).delete()

        emoji_font = FontManager.getFont(24, emoji=True)

        def make_row():
            row = lv.obj(self._emoji_pane)
            row.set_width(lv.pct(100))
            row.set_height(lv.SIZE_CONTENT)
            row.set_flex_flow(lv.FLEX_FLOW.ROW)
            row.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.START)
            _clear_bg_border_padding(row)
            row.set_style_pad_column(2, lv.PART.MAIN)
            return row

        row = make_row()
        self._add_emoji_button(row, self.LABEL_LETTERS, emoji_font,
                               on_press=lambda: (self._hide_emoji_pane(), self.set_mode(self.MODE_LOWERCASE)))

        for emoji in FontManager.getEmojiStrings():
            if len(self._emoji_buttons) % self._EMOJI_COLUMNS == 0:
                row = make_row()
            self._add_emoji_label(row, emoji, emoji_font,
                                  on_press=lambda text=emoji: self._insert_emoji(text))

    def _add_emoji_button(self, row, text, font, on_press):
        """Create one emoji key button with a centered label."""
        normal_bg = _key_normal_bg_color()
        focus_bg = _key_focus_bg_color()
        btn = lv.button(row)
        btn.set_flex_grow(1)
        btn.set_height(lv.SIZE_CONTENT)
        btn.set_style_bg_color(normal_bg, lv.PART.MAIN)
        btn.remove_flag(lv.obj.FLAG.SCROLLABLE)
        _strip_button_theme(btn)
        label = lv.label(btn)
        label.set_text(text)
        label.set_style_text_font(font, lv.PART.MAIN)
        label.center()
        btn.add_event_cb(lambda e: on_press(), lv.EVENT.CLICKED, None)
        focus.add_focus_border(btn, width=0, bg_color=focus_bg, bg_color_unfocused=normal_bg)
        self._emoji_buttons.append(btn)

    def _add_emoji_label(self, row, text, font, on_press):
        """Create one clickable emoji label and add it to the focus group."""
        normal_bg = _key_normal_bg_color()
        focus_bg = _key_focus_bg_color()
        label = lv.label(row)
        label.set_text(text)
        label.set_flex_grow(1)
        label.set_style_text_font(font, lv.PART.MAIN)
        label.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)
        label.set_style_margin_all(0, lv.PART.MAIN)
        label.set_style_pad_all(4, lv.PART.MAIN)
        label.set_style_radius(4, lv.PART.MAIN)
        label.set_style_bg_color(normal_bg, lv.PART.MAIN)
        label.set_style_bg_opa(lv.OPA.COVER, lv.PART.MAIN)
        label.add_flag(lv.obj.FLAG.CLICKABLE)
        label.remove_flag(lv.obj.FLAG.SCROLLABLE)
        label.add_event_cb(lambda e: on_press(), lv.EVENT.CLICKED, None)
        focus.add_focus_border(label, width=0, bg_color=focus_bg, bg_color_unfocused=normal_bg, radius=4)
        self._emoji_buttons.append(label)

    def _insert_emoji(self, emoji):
        """Append an emoji to the textarea."""
        ta = self._textarea
        if ta:
            ta.set_text(ta.get_text() + emoji)
            self._ensure_textarea_emoji_font(ta, emoji)

    def _build_keyboard(self, mode):
        """Create key buttons for the requested mode."""
        # Clean up previous keys
        for row in self._row_containers:
            row.delete()
        self._row_containers = []
        self._keys = []

        layout = self.mode_info[mode]
        keyboard_font = FontManager.getFont(20, emoji=True)
        normal_bg = _key_normal_bg_color()
        focus_bg = _key_focus_bg_color()

        for row_spec in layout:
            row = lv.obj(self._keyboard)
            row.set_width(lv.pct(100))
            row.set_height(lv.SIZE_CONTENT)
            row.set_flex_flow(lv.FLEX_FLOW.ROW)
            row.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.START)
            _clear_bg_border_padding(row)

            for token in row_spec:
                text = _key_text(token)
                grow = _key_grow(token)
                btn = lv.button(row)
                btn.set_flex_grow(grow)
                btn.set_height(lv.SIZE_CONTENT)
                btn.set_style_bg_color(normal_bg, lv.PART.MAIN)
                btn.remove_flag(lv.obj.FLAG.SCROLLABLE)
                _strip_button_theme(btn)
                label = lv.label(btn)
                label.set_text(text)
                label.set_style_text_font(keyboard_font, lv.PART.MAIN)
                label.set_style_margin_all(0, lv.PART.MAIN)
                label.center()
                btn.add_event_cb(lambda e, key=text: self._on_key_press(key), lv.EVENT.CLICKED, None)
                focus.add_focus_border(btn, width=0, bg_color=focus_bg, bg_color_unfocused=normal_bg)
                self._keys.append(btn)

            self._row_containers.append(row)

        # The emoji pane is never shown at the same time as the keyboard rows.
        if self._emoji_pane is not None:
            self._emoji_pane.add_flag(lv.obj.FLAG.HIDDEN)

    def _on_key_press(self, text):
        """Handle a keyboard key press."""
        ta = self._textarea
        if text == lv.SYMBOL.UP:
            self.set_mode(self.MODE_UPPERCASE)
            return
        if text == lv.SYMBOL.DOWN or text == self.LABEL_LETTERS:
            self.set_mode(self.MODE_LOWERCASE)
            return
        if text == self.LABEL_NUMBERS_SPECIALS:
            self.set_mode(self.MODE_NUMBERS)
            return
        if text == self.LABEL_SPECIALS:
            self.set_mode(self.MODE_SPECIALS)
            return
        if text == self.LABEL_EMOJI:
            self._show_emoji_pane()
            return
        if not ta:
            return
        current_text = ta.get_text()
        if text == lv.SYMBOL.BACKSPACE:
            ta.set_text(current_text[:-1])
        elif text == lv.SYMBOL.OK:
            self._keyboard.send_event(lv.EVENT.READY, None)
        elif text == lv.SYMBOL.NEW_LINE:
            if ta.get_one_line():
                self._keyboard.send_event(lv.EVENT.READY, None)
            else:
                ta.set_text(current_text + "\n")
        elif text == self.LABEL_SPACE:
            ta.set_text(current_text + " ")
        else:
            ta.set_text(current_text + text)
            self._ensure_textarea_emoji_font(ta, text)

    def _set_emoji_focus(self, emoji_active):
        """Swap the default input group between the keyboard and emoji pane."""
        group = lv.group_get_default()
        if not group:
            return
        if emoji_active:
            for btn in self._keys:
                try:
                    lv.group_remove_obj(btn)
                except Exception:
                    pass
            for btn in self._emoji_buttons:
                group.add_obj(btn)
            if self._emoji_buttons:
                lv.group_focus_obj(self._emoji_buttons[0])
        else:
            for btn in self._emoji_buttons:
                try:
                    lv.group_remove_obj(btn)
                except Exception:
                    pass
            for btn in self._keys:
                group.add_obj(btn)
            if self._keys:
                lv.group_focus_obj(self._keys[0])

    def _clear_keyboard_rows(self):
        """Remove the normal keyboard row widgets."""
        for row in self._row_containers:
            row.delete()
        self._row_containers = []
        self._keys = []

    def _show_emoji_pane(self):
        """Show the emoji pane and remove the normal keyboard rows."""
        self._clear_keyboard_rows()
        self._emoji_pane.remove_flag(lv.obj.FLAG.HIDDEN)
        self._set_emoji_focus(True)

    def _hide_emoji_pane(self):
        """Hide the emoji pane and rebuild the normal keyboard rows."""
        self._emoji_pane.add_flag(lv.obj.FLAG.HIDDEN)
        self.set_mode(self._current_mode if self._current_mode is not None else self.MODE_LOWERCASE)
        self._set_emoji_focus(False)

    def _without_newline_key_layout(self, layout):
        """Return a layout copy with the NEW_LINE key removed from each row."""
        new_rows = []
        for row in layout:
            filtered = []
            for token in row:
                if _key_text(token) == lv.SYMBOL.NEW_LINE:
                    continue
                filtered.append(token)
            new_rows.append(tuple(filtered))
        return tuple(new_rows)

    def set_textarea(self, textarea, on_show=None, on_hide=None):
        """
        Set the textarea that this keyboard types into.

        IMPORTANT: We store the textarea reference ourselves and DON'T pass
        it to LVGL's keyboard. This prevents double-character bugs.

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
            self.mode_info = {
                self.MODE_LOWERCASE: self._without_newline_key_layout(type(self)._lowercase_layout),
                self.MODE_UPPERCASE: self._without_newline_key_layout(type(self)._uppercase_layout),
                self.MODE_NUMBERS: self._without_newline_key_layout(type(self)._numbers_layout),
                self.MODE_SPECIALS: self._without_newline_key_layout(type(self)._specials_layout),
            }
        else:
            self.mode_info = dict(type(self).mode_info)

        # Open the keyboard when the textarea is clicked.
        if textarea:
            textarea.add_event_cb(lambda *args: self.show_keyboard(), lv.EVENT.CLICKED, None)

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
            The lv.textarea widget, or None if it has been disconnected
        """
        return self._textarea

    def set_mode(self, mode):
        """Switch to a different keyboard layout mode."""
        old_x, old_y = None, None
        group = lv.group_get_default()
        if group and self._keys:
            focused = group.get_focused()
            if focused in self._keys:
                area = lv.area_t()
                focused.get_coords(area)
                old_x = (area.x1 + area.x2) / 2
                old_y = (area.y1 + area.y2) / 2

        self._current_mode = mode
        self._build_keyboard(mode)

        if old_x is not None:
            # Layout is not ready yet while we are still inside an event handler
            # (e.g. the user tapped the uppercase-key). Defer the coordinate-based
            # focus restore until the next LVGL tick so buttons have valid coords.
            def _restore_focus(timer, x=old_x, y=old_y):
                focus.focus_coordinates(x, y)

            lv.timer_create(_restore_focus, 1, None).set_repeat_count(1)

        # Rebuild scrolling to keep the linked textarea in view, not the keyboard
        # at the top of the screen.
        if self._textarea:
            self._textarea.scroll_to_view_recursive(True)

    def scroll_after_show(self, timer):
        self._keyboard.scroll_to_view_recursive(True)

    def focus_on_keyboard(self, timer=None):
        """Move the input focus to the first keyboard key."""
        default_group = lv.group_get_default()
        if not default_group:
            return
        if self._keys:
            lv.group_focus_obj(self._keys[0])

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
        # Show the keyboard immediately and then focus on it - that works, and doesn't seem to flicker as feared:
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
        Forward any undefined method/attribute to the underlying LVGL container.

        This allows MposKeyboard to support LVGL widget methods automatically
        without needing to manually wrap each one. Any method not defined on
        MposKeyboard will be forwarded to self._keyboard.
        """
        # Forward to the underlying keyboard container object
        return getattr(self._keyboard, name)
