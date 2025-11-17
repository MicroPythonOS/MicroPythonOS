"""
Manual test for the "abc" button bug with DEBUG OUTPUT.

Run with: ./scripts/run_desktop.sh tests/manual_test_abc_button_debug.py

This will show debug output when you click the "abc" button.
Watch the terminal to see what's happening!
"""

import lvgl as lv
from mpos.ui.keyboard import MposKeyboard

# Get active screen
screen = lv.screen_active()
screen.clean()

# Create title
title = lv.label(screen)
title.set_text("ABC Button Debug Test")
title.align(lv.ALIGN.TOP_MID, 0, 5)

# Create instructions
instructions = lv.label(screen)
instructions.set_text(
    "Watch the TERMINAL output!\n"
    "\n"
    "1. Click '?123' to go to numbers mode\n"
    "2. Click 'abc' to go back to lowercase\n"
    "3. Check terminal for debug output\n"
    "4. Check if comma appears in textarea"
)
instructions.set_style_text_align(lv.TEXT_ALIGN.LEFT, 0)
instructions.align(lv.ALIGN.TOP_LEFT, 10, 30)

# Create textarea
textarea = lv.textarea(screen)
textarea.set_size(280, 30)
textarea.set_one_line(True)
textarea.align(lv.ALIGN.TOP_MID, 0, 120)
textarea.set_placeholder_text("Type here...")

# Create keyboard
keyboard = MposKeyboard(screen)
keyboard.set_textarea(textarea)
keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)

print("\n" + "="*70)
print("ABC BUTTON DEBUG TEST")
print("="*70)
print("Instructions:")
print("1. The keyboard starts in LOWERCASE mode")
print("2. Click the '?123' button (bottom left) to switch to NUMBERS mode")
print("3. Click the 'abc' button (bottom left) to switch back to LOWERCASE")
print("4. Watch this terminal for [KEYBOARD DEBUG] messages")
print("5. Check if a comma appears in the textarea")
print("="*70)
print("\nWaiting for button clicks...")
print()
