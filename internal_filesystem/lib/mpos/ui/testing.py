"""
Graphical testing utilities for MicroPythonOS.

This module provides utilities for graphical/visual testing and UI automation
that work on both desktop (unix/macOS) and device (ESP32). These functions can
be used by:
- Unit tests for verifying UI behavior
- Apps that want to implement automation or testing features
- Integration tests and end-to-end testing

Important: Functions in this module assume the display, theme, and UI
infrastructure are already initialized (boot.py and main.py executed).

Usage in tests:
    from mpos.ui.testing import wait_for_render, capture_screenshot

    # Start your app
    mpos.apps.start_app("com.example.myapp")

    # Wait for UI to render
    wait_for_render()

    # Verify content
    assert verify_text_present(lv.screen_active(), "Expected Text")

    # Capture screenshot
    capture_screenshot("tests/screenshots/mytest.raw")

    # Simulate user interaction
    simulate_click(160, 120)  # Click at center of 320x240 screen

Usage in apps:
    from mpos.ui.testing import simulate_click, find_label_with_text

    # Automated demo mode
    label = find_label_with_text(self.screen, "Start")
    if label:
        area = lv.area_t()
        label.get_coords(area)
        simulate_click(area.x1 + 10, area.y1 + 10)
"""

import lvgl as lv

# Simulation globals for touch input
_touch_x = 0
_touch_y = 0
_touch_pressed = False
_touch_indev = None


def wait_for_render(iterations=10):
    """
    Wait for LVGL to process UI events and render.

    This processes the LVGL task handler multiple times to ensure
    all UI updates, animations, and layout changes are complete.
    Essential for tests to avoid race conditions.

    Args:
        iterations: Number of task handler iterations to run (default: 10)

    Example:
        mpos.apps.start_app("com.example.myapp")
        wait_for_render()  # Ensure UI is ready
        assert verify_text_present(lv.screen_active(), "Welcome")
    """
    import time
    for _ in range(iterations):
        lv.task_handler()
        time.sleep(0.01)  # Small delay between iterations


def capture_screenshot(filepath, width=320, height=240, color_format=lv.COLOR_FORMAT.RGB565):
    """
    Capture screenshot of current screen using LVGL snapshot.

    The screenshot is saved as raw binary data in the specified color format.
    Useful for visual regression testing or documentation.

    To convert RGB565 to PNG:
        ffmpeg -vcodec rawvideo -f rawvideo -pix_fmt rgb565 -s 320x240 -i file.raw file.png

    Or use the conversion script:
        cd tests/screenshots
        ./convert_to_png.sh

    Args:
        filepath: Path where to save the raw screenshot data
        width: Screen width in pixels (default: 320)
        height: Screen height in pixels (default: 240)
        color_format: LVGL color format (default: RGB565 for memory efficiency)

    Returns:
        bytearray: The screenshot buffer

    Raises:
        Exception: If screenshot capture fails

    Example:
        from mpos.ui.testing import capture_screenshot
        capture_screenshot("tests/screenshots/home.raw")
    """
    print(f"capture_screenshot writing to {filepath}")

    # Calculate buffer size based on color format
    if color_format == lv.COLOR_FORMAT.RGB565:
        bytes_per_pixel = 2
    elif color_format == lv.COLOR_FORMAT.RGB888:
        bytes_per_pixel = 3
    else:
        bytes_per_pixel = 4  # ARGB8888

    size = width * height * bytes_per_pixel
    buffer = bytearray(size)
    image_dsc = lv.image_dsc_t()

    # Take snapshot of active screen
    lv.snapshot_take_to_buf(lv.screen_active(), color_format, image_dsc, buffer, size)

    # Save to file
    with open(filepath, "wb") as f:
        f.write(buffer)

    return buffer


def get_all_widgets_with_text(obj, widgets=None):
    """
    Recursively find all widgets that have text in the object hierarchy.

    This traverses the entire widget tree starting from obj and
    collects all widgets that have a get_text() method and return
    non-empty text. This includes labels, checkboxes, buttons with
    text, etc.

    Args:
        obj: LVGL object to search (typically lv.screen_active())
        widgets: Internal accumulator list (leave as None)

    Returns:
        list: List of all widgets with text found in the hierarchy

    Example:
        widgets = get_all_widgets_with_text(lv.screen_active())
        print(f"Found {len(widgets)} widgets with text")
    """
    if widgets is None:
        widgets = []

    # Check if this object has text
    try:
        if hasattr(obj, 'get_text'):
            text = obj.get_text()
            if text:  # Only add if text is non-empty
                widgets.append(obj)
    except:
        pass  # Error getting text or no get_text method

    # Recursively check children
    try:
        child_count = obj.get_child_count()
        for i in range(child_count):
            child = obj.get_child(i)
            get_all_widgets_with_text(child, widgets)
    except:
        pass  # No children or error accessing them

    return widgets


def get_all_labels(obj, labels=None):
    """
    Recursively find all label widgets in the object hierarchy.

    DEPRECATED: Use get_all_widgets_with_text() instead for better
    compatibility with all text-containing widgets (labels, checkboxes, etc.)

    This traverses the entire widget tree starting from obj and
    collects all LVGL label objects. Useful for comprehensive
    text verification or debugging.

    Args:
        obj: LVGL object to search (typically lv.screen_active())
        labels: Internal accumulator list (leave as None)

    Returns:
        list: List of all label objects found in the hierarchy

    Example:
        labels = get_all_labels(lv.screen_active())
        print(f"Found {len(labels)} labels")
    """
    # For backwards compatibility, use the new function
    return get_all_widgets_with_text(obj, labels)


def find_label_with_text(obj, search_text):
    """
    Find a widget containing specific text.

    Searches the entire widget hierarchy for any widget (label, checkbox,
    button, etc.) whose text contains the search string (substring match).
    Returns the first match found.

    Args:
        obj: LVGL object to search (typically lv.screen_active())
        search_text: Text to search for (can be substring)

    Returns:
        LVGL widget object if found, None otherwise

    Example:
        widget = find_label_with_text(lv.screen_active(), "Settings")
        if widget:
            print(f"Found Settings widget at {widget.get_coords()}")
    """
    widgets = get_all_widgets_with_text(obj)
    for widget in widgets:
        try:
            text = widget.get_text()
            if search_text in text:
                return widget
        except:
            pass  # Error getting text from this widget
    return None


def get_screen_text_content(obj):
    """
    Extract all text content from all widgets on screen.

    Useful for debugging or comprehensive text verification.
    Returns a list of all text strings found in any widgets with text
    (labels, checkboxes, buttons, etc.).

    Args:
        obj: LVGL object to search (typically lv.screen_active())

    Returns:
        list: List of all text strings found in widgets

    Example:
        texts = get_screen_text_content(lv.screen_active())
        assert "Welcome" in texts
        assert "Version 1.0" in texts
    """
    widgets = get_all_widgets_with_text(obj)
    texts = []
    for widget in widgets:
        try:
            text = widget.get_text()
            if text:
                texts.append(text)
        except:
            pass  # Error getting text
    return texts


def verify_text_present(obj, expected_text):
    """
    Verify that expected text is present somewhere on screen.

    This is the primary verification method for graphical tests.
    It searches all labels for the expected text (substring match).

    Args:
        obj: LVGL object to search (typically lv.screen_active())
        expected_text: Text that should be present (can be substring)

    Returns:
        bool: True if text found, False otherwise

    Example:
        assert verify_text_present(lv.screen_active(), "Settings")
        assert verify_text_present(lv.screen_active(), "Version")
    """
    return find_label_with_text(obj, expected_text) is not None


def print_screen_labels(obj):
    """
    Debug helper: Print all text found on screen from any widget.

    Useful for debugging tests to see what text is actually present.
    Prints to stdout with numbered list. Includes text from labels,
    checkboxes, buttons, and any other widgets with text.

    Args:
        obj: LVGL object to search (typically lv.screen_active())

    Example:
        # When a test fails, use this to see what's on screen
        print_screen_labels(lv.screen_active())
        # Output:
        # Found 5 text widgets on screen:
        #   0: MicroPythonOS
        #   1: Version 0.3.3
        #   2: Settings
        #   3: Force Update (checkbox)
        #   4: WiFi
    """
    texts = get_screen_text_content(obj)
    print(f"Found {len(texts)} text widgets on screen:")
    for i, text in enumerate(texts):
        print(f"  {i}: {text}")


def get_widget_coords(widget):
    """
    Get the coordinates of a widget.

    Returns the bounding box coordinates of the widget, useful for
    clicking on it or verifying its position.

    Args:
        widget: LVGL widget object

    Returns:
        dict: Dictionary with keys 'x1', 'y1', 'x2', 'y2', 'center_x', 'center_y'
              Returns None if widget is invalid or has no coordinates

    Example:
        # Find and click on a button
        button = find_label_with_text(lv.screen_active(), "Submit")
        if button:
            coords = get_widget_coords(button.get_parent())  # Get parent button
            if coords:
                simulate_click(coords['center_x'], coords['center_y'])
    """
    try:
        area = lv.area_t()
        widget.get_coords(area)
        return {
            'x1': area.x1,
            'y1': area.y1,
            'x2': area.x2,
            'y2': area.y2,
            'center_x': (area.x1 + area.x2) // 2,
            'center_y': (area.y1 + area.y2) // 2,
            'width': area.x2 - area.x1,
            'height': area.y2 - area.y1,
        }
    except:
        return None


def find_button_with_text(obj, search_text):
    """
    Find a button widget containing specific text in its label.

    This is specifically for finding buttons (which contain labels as children)
    rather than just labels. Very useful for testing UI interactions.

    Args:
        obj: LVGL object to search (typically lv.screen_active())
        search_text: Text to search for in button labels (can be substring)

    Returns:
        LVGL button object if found, None otherwise

    Example:
        submit_btn = find_button_with_text(lv.screen_active(), "Submit")
        if submit_btn:
            coords = get_widget_coords(submit_btn)
            simulate_click(coords['center_x'], coords['center_y'])
    """
    # Find the label first
    label = find_label_with_text(obj, search_text)
    if label:
        # Try to get the parent button
        try:
            parent = label.get_parent()
            # Check if parent is a button
            if parent.get_class() == lv.button_class:
                return parent
            # Sometimes there's an extra container layer
            grandparent = parent.get_parent()
            if grandparent and grandparent.get_class() == lv.button_class:
                return grandparent
        except:
            pass
    return None


def get_keyboard_button_coords(keyboard, button_text):
    """
    Get the coordinates of a specific button on an LVGL keyboard/buttonmatrix.

    This function calculates the exact center position of a keyboard button
    by finding its index and computing its position based on the keyboard's
    layout, control widths, and actual screen coordinates.

    Args:
        keyboard: LVGL keyboard widget (or MposKeyboard wrapper)
        button_text: Text of the button to find (e.g., "q", "a", "1")

    Returns:
        dict with 'center_x' and 'center_y', or None if button not found

    Example:
        from mpos.ui.keyboard import MposKeyboard
        keyboard = MposKeyboard(screen)
        coords = get_keyboard_button_coords(keyboard, "q")
        if coords:
            simulate_click(coords['center_x'], coords['center_y'])
    """
    # Get the underlying LVGL keyboard if this is a wrapper
    if hasattr(keyboard, '_keyboard'):
        lvgl_keyboard = keyboard._keyboard
    else:
        lvgl_keyboard = keyboard

    # Find the button index
    button_idx = None
    for i in range(100):  # Check up to 100 buttons
        try:
            text = lvgl_keyboard.get_button_text(i)
            if text == button_text:
                button_idx = i
                break
        except:
            break  # No more buttons

    if button_idx is None:
        return None

    # Get keyboard widget coordinates
    area = lv.area_t()
    lvgl_keyboard.get_coords(area)
    kb_x = area.x1
    kb_y = area.y1
    kb_width = area.x2 - area.x1
    kb_height = area.y2 - area.y1

    # Parse the keyboard layout to find button position
    # Note: LVGL get_button_text() skips '\n' markers, so they're not in the indices
    # Standard keyboard layout (from MposKeyboard):
    # Row 0: 10 buttons (q w e r t y u i o p)
    # Row 1: 9 buttons (a s d f g h j k l)
    # Row 2: 9 buttons (shift z x c v b n m backspace)
    # Row 3: 5 buttons (?123, comma, space, dot, enter)

    # Define row lengths for standard keyboard
    row_lengths = [10, 9, 9, 5]

    # Find which row our button is in
    row = 0
    buttons_before = 0
    for row_len in row_lengths:
        if button_idx < buttons_before + row_len:
            # Button is in this row
            col = button_idx - buttons_before
            buttons_this_row = row_len
            break
        buttons_before += row_len
        row += 1
    else:
        # Button not found in standard layout, use row 0
        row = 0
        col = button_idx
        buttons_this_row = 10

    # Calculate position
    # Approximate: divide keyboard into equal rows and columns
    # (This is simplified - actual LVGL uses control widths, but this is good enough)
    num_rows = 4  # Typical keyboard has 4 rows
    button_height = kb_height / num_rows
    button_width = kb_width / max(buttons_this_row, 1)

    # Calculate center position
    center_x = int(kb_x + (col * button_width) + (button_width / 2))
    center_y = int(kb_y + (row * button_height) + (button_height / 2))

    return {
        'center_x': center_x,
        'center_y': center_y,
        'button_idx': button_idx,
        'row': row,
        'col': col
    }


def _touch_read_cb(indev_drv, data):
    """
    Internal callback for simulated touch input device.

    This callback is registered with LVGL and provides touch state
    when simulate_click() is used. Not intended for direct use.

    Args:
        indev_drv: Input device driver (LVGL internal)
        data: Input device data structure to fill
    """
    global _touch_x, _touch_y, _touch_pressed
    data.point.x = _touch_x
    data.point.y = _touch_y
    if _touch_pressed:
        data.state = lv.INDEV_STATE.PRESSED
    else:
        data.state = lv.INDEV_STATE.RELEASED


def _ensure_touch_indev():
    """
    Ensure that the simulated touch input device is created.

    This is called automatically by simulate_click() on first use.
    Creates a pointer-type input device that uses _touch_read_cb.
    Not intended for direct use.
    """
    global _touch_indev
    if _touch_indev is None:
        _touch_indev = lv.indev_create()
        _touch_indev.set_type(lv.INDEV_TYPE.POINTER)
        _touch_indev.set_read_cb(_touch_read_cb)
        print("Created simulated touch input device")


def simulate_click(x, y, press_duration_ms=50):
    """
    Simulate a touch/click at the specified coordinates.

    This creates a simulated touch press at (x, y) and automatically
    releases it after press_duration_ms milliseconds. The touch is
    processed through LVGL's normal input handling, so it triggers
    click events, focus changes, scrolling, etc. just like real input.

    Useful for:
    - Automated testing of UI interactions
    - Demo modes in apps
    - Accessibility automation
    - Integration testing

    To find object coordinates for clicking:
        obj_area = lv.area_t()
        obj.get_coords(obj_area)
        center_x = (obj_area.x1 + obj_area.x2) // 2
        center_y = (obj_area.y1 + obj_area.y2) // 2
        simulate_click(center_x, center_y)

    Args:
        x: X coordinate to click (in pixels)
        y: Y coordinate to click (in pixels)
        press_duration_ms: How long to hold the press (default: 50ms)

    Example:
        from mpos.ui.testing import simulate_click, wait_for_render

        # Click at screen center (320x240)
        simulate_click(160, 120)
        wait_for_render()

        # Click on a specific button
        button_area = lv.area_t()
        my_button.get_coords(button_area)
        simulate_click(button_area.x1 + 10, button_area.y1 + 10)
        wait_for_render()
    """
    global _touch_x, _touch_y, _touch_pressed

    # Ensure the touch input device exists
    _ensure_touch_indev()

    # Set touch position and press state
    _touch_x = x
    _touch_y = y
    _touch_pressed = True

    # Process the press immediately
    lv.task_handler()

    def release_timer_cb(timer):
        """Timer callback to release the touch press."""
        global _touch_pressed
        _touch_pressed = False
        lv.task_handler()  # Process the release immediately

    # Schedule the release
    timer = lv.timer_create(release_timer_cb, press_duration_ms, None)
    timer.set_repeat_count(1)
