"""
Manual test for MposKeyboard typing behavior.

This test allows you to manually type on the keyboard and verify:
1. Only one character is added per button press (not doubled)
2. Mode switching works correctly
3. Special characters work

Run with: ./scripts/run_desktop.sh tests/manual_test_keyboard_typing.py
"""

import lvgl as lv
from mpos.ui.keyboard import MposKeyboard

# Get active screen
screen = lv.screen_active()
screen.clean()

# Create a textarea to type into
textarea = lv.textarea(screen)
textarea.set_size(280, 60)
textarea.align(lv.ALIGN.TOP_MID, 0, 20)
textarea.set_placeholder_text("Type here to test keyboard...")

# Create instructions label
label = lv.label(screen)
label.set_text("Test keyboard typing:\n"
               "- Each key should add ONE character\n"
               "- Try mode switching (UP/DOWN, ?123)\n"
               "- Check backspace works\n"
               "- Press ESC to exit")
label.set_size(280, 80)
label.align(lv.ALIGN.TOP_MID, 0, 90)
label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

# Create the keyboard
keyboard = MposKeyboard(screen)
keyboard.set_textarea(textarea)
keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)

print("\n" + "="*50)
print("Manual Keyboard Test")
print("="*50)
print("Click on keyboard buttons and observe the textarea.")
print("Each button should add exactly ONE character.")
print("If you see double characters, the bug exists.")
print("Press ESC or close window to exit.")
print("="*50 + "\n")
