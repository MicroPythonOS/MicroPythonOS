"""
Manual test for the "abc" button bug.

This test creates a keyboard and lets you manually switch modes to observe the bug.

Run with: ./scripts/run_desktop.sh tests/manual_test_abc_button.py

Steps to reproduce the bug:
1. Keyboard starts in lowercase mode
2. Click "?123" button to switch to numbers mode
3. Click "abc" button to switch back to lowercase
4. OBSERVE: Does it show "?123" (correct) or "1#" (wrong/default LVGL)?
"""

import lvgl as lv
from mpos.ui.keyboard import MposKeyboard

# Get active screen
screen = lv.screen_active()
screen.clean()

# Create title
title = lv.label(screen)
title.set_text("ABC Button Test")
title.align(lv.ALIGN.TOP_MID, 0, 5)

# Create instructions
instructions = lv.label(screen)
instructions.set_text(
    "1. Start in lowercase (has ?123 button)\n"
    "2. Click '?123' to switch to numbers\n"
    "3. Click 'abc' to switch back\n"
    "4. CHECK: Do you see '?123' or '1#'?\n"
    "   - '?123' = CORRECT (custom keyboard)\n"
    "   - '1#' = BUG (default LVGL keyboard)"
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

print("\n" + "="*60)
print("ABC Button Bug Test")
print("="*60)
print("Instructions:")
print("1. Keyboard starts in LOWERCASE mode")
print("   - Look for '?123' button (bottom left area)")
print("2. Click '?123' to switch to NUMBERS mode")
print("   - Should show numbers 1,2,3, etc.")
print("   - Should have 'abc' button (bottom left)")
print("3. Click 'abc' to return to lowercase")
print("4. CRITICAL CHECK:")
print("   - If you see '?123' button → CORRECT (custom keyboard)")
print("   - If you see '1#' button → BUG (default LVGL keyboard)")
print("="*60 + "\n")
