"""
Manual test for WiFi password page keyboard.

This test allows you to manually type and check for double characters.

Run with: ./scripts/run_desktop.sh tests/manual_test_wifi_password.py

Instructions:
1. Click on the password field
2. Type some characters
3. Check if each keypress adds ONE character or TWO
4. If you see doubles, the bug exists
"""

import lvgl as lv
from mpos.ui.keyboard import MposKeyboard

# Get active screen
screen = lv.screen_active()
screen.clean()

# Create title label
title = lv.label(screen)
title.set_text("WiFi Password Test")
title.align(lv.ALIGN.TOP_MID, 0, 10)

# Create textarea (simulating WiFi password field)
password_ta = lv.textarea(screen)
password_ta.set_width(lv.pct(90))
password_ta.set_one_line(True)
password_ta.align_to(title, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
password_ta.set_placeholder_text("Type here...")
password_ta.set_text("")  # Start empty

# Create instruction label
instructions = lv.label(screen)
instructions.set_text("Click above and type.\nWatch for DOUBLE characters.\nEach key should add ONE char only.")
instructions.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
instructions.align(lv.ALIGN.CENTER, 0, 0)

# Create keyboard (like WiFi app does)
keyboard = MposKeyboard(screen)
keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
keyboard.set_textarea(password_ta)  # This might cause double-typing!
keyboard.set_style_min_height(165, 0)

# Add event handler like WiFi app does (to detect READY/CANCEL)
def handle_keyboard_events(event):
    target_obj = event.get_target_obj()
    button = target_obj.get_selected_button()
    text = target_obj.get_button_text(button)
    print(f"Event: button={button}, text={text}, textarea='{password_ta.get_text()}'")
    if text == lv.SYMBOL.NEW_LINE:
        print("Enter pressed")

keyboard.add_event_cb(handle_keyboard_events, lv.EVENT.VALUE_CHANGED, None)

print("\n" + "="*60)
print("WiFi Password Keyboard Test")
print("="*60)
print("Type on the keyboard and watch the textarea.")
print("BUG: If each keypress adds TWO characters instead of ONE,")
print("     then we have the double-character bug!")
print("")
print("Expected: typing 'hello' should show 'hello'")
print("Bug:      typing 'hello' shows 'hheelllloo'")
print("="*60)
print("\nPress ESC or close window to exit.")
