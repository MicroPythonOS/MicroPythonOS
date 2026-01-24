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
    from mpos import AppManager

    # Start your app
    AppManager.start_app("com.example.myapp")

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
import time

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
        from mpos import AppManager
        AppManager.start_app("com.example.myapp")
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


def text_to_hex(text):
    """
    Convert text to hex representation for debugging.
    
    Useful for identifying Unicode symbols like lv.SYMBOL.SETTINGS
    which may not display correctly in terminal output.
    
    Args:
        text: String to convert
        
    Returns:
        str: Hex representation of the text bytes (UTF-8 encoded)
        
    Example:
        >>> text_to_hex("⚙")  # lv.SYMBOL.SETTINGS
        'e29a99'
    """
    try:
        return text.encode('utf-8').hex()
    except:
        return "<encoding error>"


def print_screen_labels(obj):
    """
    Debug helper: Print all text found on screen from any widget.

    Useful for debugging tests to see what text is actually present.
    Prints to stdout with numbered list. Includes text from labels,
    checkboxes, buttons, and any other widgets with text.
    
    For each text, also prints the hex representation to help identify
    Unicode symbols (like lv.SYMBOL.SETTINGS) that may not display
    correctly in terminal output.

    Args:
        obj: LVGL object to search (typically lv.screen_active())

    Example:
        # When a test fails, use this to see what's on screen
        print_screen_labels(lv.screen_active())
        # Output:
        # Found 5 text widgets on screen:
        #   0: MicroPythonOS (hex: 4d6963726f507974686f6e4f53)
        #   1: Version 0.3.3 (hex: 56657273696f6e20302e332e33)
        #   2: ⚙ (hex: e29a99)  <- lv.SYMBOL.SETTINGS
        #   3: Force Update (hex: 466f7263652055706461746)
        #   4: WiFi (hex: 57694669)
    """
    texts = get_screen_text_content(obj)
    print(f"Found {len(texts)} text widgets on screen:")
    for i, text in enumerate(texts):
        hex_repr = text_to_hex(text)
        print(f"  {i}: {text} (hex: {hex_repr})")


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


def simulate_click(x, y, press_duration_ms=100):
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
        press_duration_ms: How long to hold the press (default: 100ms)

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

    # Process the press event
    lv.task_handler()
    time.sleep(0.02)
    lv.task_handler()

    # Wait for press duration
    time.sleep(press_duration_ms / 1000.0)

    # Release the touch
    _touch_pressed = False

    # Process the release event - this triggers the CLICKED event
    lv.task_handler()
    time.sleep(0.02)
    lv.task_handler()
    time.sleep(0.02)
    lv.task_handler()

def click_button(button_text, timeout=5, use_send_event=True):
    """Find and click a button with given text.
    
    Args:
        button_text: Text to search for in button labels
        timeout: Maximum time to wait for button to appear (default: 5s)
        use_send_event: If True, use send_event() which is more reliable for
                        triggering button actions. If False, use simulate_click()
                        which simulates actual touch input. (default: True)
    
    Returns:
        True if button was found and clicked, False otherwise
    """
    start = time.time()
    while time.time() - start < timeout:
        button = find_button_with_text(lv.screen_active(), button_text)
        if button:
            coords = get_widget_coords(button)
            if coords:
                print(f"Clicking button '{button_text}' at ({coords['center_x']}, {coords['center_y']})")
                if use_send_event:
                    # Use send_event for more reliable button triggering
                    button.send_event(lv.EVENT.CLICKED, None)
                else:
                    # Use simulate_click for actual touch simulation
                    simulate_click(coords['center_x'], coords['center_y'])
                wait_for_render(iterations=20)
                return True
        wait_for_render(iterations=5)
    print(f"ERROR: Button '{button_text}' not found after {timeout}s")
    return False

def click_label(label_text, timeout=5, use_send_event=True):
    """Find a label with given text and click on it (or its clickable parent).
    
    This function finds a label, scrolls it into view (with multiple attempts
    if needed), verifies it's within the visible viewport, and then clicks it.
    If the label itself is not clickable, it will try clicking the parent container.
    
    Args:
        label_text: Text to search for in labels
        timeout: Maximum time to wait for label to appear (default: 5s)
        use_send_event: If True, use send_event() on clickable parent which is more
                        reliable. If False, use simulate_click(). (default: True)
    
    Returns:
        True if label was found and clicked, False otherwise
    """
    start = time.time()
    while time.time() - start < timeout:
        label = find_label_with_text(lv.screen_active(), label_text)
        if label:
            # Get screen dimensions for viewport check
            screen = lv.screen_active()
            screen_coords = get_widget_coords(screen)
            if not screen_coords:
                screen_coords = {'x1': 0, 'y1': 0, 'x2': 320, 'y2': 240}
            
            # Try scrolling multiple times to ensure label is fully visible
            max_scroll_attempts = 5
            for scroll_attempt in range(max_scroll_attempts):
                print(f"Scrolling label to view (attempt {scroll_attempt + 1}/{max_scroll_attempts})...")
                label.scroll_to_view_recursive(True)
                wait_for_render(iterations=50)  # needs quite a bit of time for scroll animation
                
                # Get updated coordinates after scroll
                coords = get_widget_coords(label)
                if not coords:
                    break
                
                # Check if label center is within visible viewport
                # Account for some margin (e.g., status bar at top, nav bar at bottom)
                # Use a larger bottom margin to ensure the element is fully clickable
                viewport_top = screen_coords['y1'] + 30  # Account for status bar
                viewport_bottom = screen_coords['y2'] - 30  # Larger margin at bottom for clickability
                viewport_left = screen_coords['x1']
                viewport_right = screen_coords['x2']
                
                center_x = coords['center_x']
                center_y = coords['center_y']
                
                is_visible = (viewport_left <= center_x <= viewport_right and
                              viewport_top <= center_y <= viewport_bottom)
                
                if is_visible:
                    print(f"Label '{label_text}' is visible at ({center_x}, {center_y})")
                    
                    # Try to find a clickable parent (container) - many UIs have clickable containers
                    # with non-clickable labels inside. We'll click on the label's position but
                    # the event should bubble up to the clickable parent.
                    click_target = label
                    clickable_parent = None
                    click_coords = coords
                    try:
                        parent = label.get_parent()
                        if parent and parent.has_flag(lv.obj.FLAG.CLICKABLE):
                            # The parent is clickable - we can use send_event on it
                            clickable_parent = parent
                            parent_coords = get_widget_coords(parent)
                            if parent_coords:
                                print(f"Found clickable parent container: ({parent_coords['x1']}, {parent_coords['y1']}) to ({parent_coords['x2']}, {parent_coords['y2']})")
                                # Use label's x but ensure y is within parent bounds
                                click_x = center_x
                                click_y = center_y
                                # Clamp to parent bounds with some margin
                                if click_y < parent_coords['y1'] + 5:
                                    click_y = parent_coords['y1'] + 5
                                if click_y > parent_coords['y2'] - 5:
                                    click_y = parent_coords['y2'] - 5
                                click_coords = {'center_x': click_x, 'center_y': click_y}
                    except Exception as e:
                        print(f"Could not check parent clickability: {e}")
                    
                    print(f"Clicking label '{label_text}' at ({click_coords['center_x']}, {click_coords['center_y']})")
                    if use_send_event and clickable_parent:
                        # Use send_event on the clickable parent for more reliable triggering
                        print(f"Using send_event on clickable parent")
                        clickable_parent.send_event(lv.EVENT.CLICKED, None)
                    else:
                        # Use simulate_click for actual touch simulation
                        simulate_click(click_coords['center_x'], click_coords['center_y'])
                    wait_for_render(iterations=20)
                    return True
                else:
                    print(f"Label '{label_text}' at ({center_x}, {center_y}) not fully visible "
                          f"(viewport: y={viewport_top}-{viewport_bottom}), scrolling more...")
                    # Additional scroll - try scrolling the parent container
                    try:
                        parent = label.get_parent()
                        if parent:
                            # Try to find a scrollable ancestor
                            scrollable = parent
                            for _ in range(5):  # Check up to 5 levels up
                                try:
                                    grandparent = scrollable.get_parent()
                                    if grandparent:
                                        scrollable = grandparent
                                except:
                                    break
                            
                            # Scroll by a fixed amount to bring label more into view
                            current_scroll = scrollable.get_scroll_y()
                            if center_y > viewport_bottom:
                                # Need to scroll down (increase scroll_y)
                                scrollable.scroll_to_y(current_scroll + 60, True)
                            elif center_y < viewport_top:
                                # Need to scroll up (decrease scroll_y)
                                scrollable.scroll_to_y(max(0, current_scroll - 60), True)
                            wait_for_render(iterations=30)
                    except Exception as e:
                        print(f"Additional scroll failed: {e}")
            
            # If we exhausted scroll attempts, try clicking anyway
            coords = get_widget_coords(label)
            if coords:
                # Try to find a clickable parent even for fallback click
                click_coords = coords
                try:
                    parent = label.get_parent()
                    if parent and parent.has_flag(lv.obj.FLAG.CLICKABLE):
                        parent_coords = get_widget_coords(parent)
                        if parent_coords:
                            click_coords = parent_coords
                            print(f"Using clickable parent for fallback click")
                except:
                    pass
                
                print(f"Clicking at ({click_coords['center_x']}, {click_coords['center_y']}) after max scroll attempts")
                # Try to use send_event if we have a clickable parent
                try:
                    parent = label.get_parent()
                    if use_send_event and parent and parent.has_flag(lv.obj.FLAG.CLICKABLE):
                        print(f"Using send_event on clickable parent for fallback")
                        parent.send_event(lv.EVENT.CLICKED, None)
                    else:
                        simulate_click(click_coords['center_x'], click_coords['center_y'])
                except:
                    simulate_click(click_coords['center_x'], click_coords['center_y'])
                wait_for_render(iterations=20)
                return True
                
        wait_for_render(iterations=5)
    print(f"ERROR: Label '{label_text}' not found after {timeout}s")
    return False

def find_text_on_screen(text):
    """Check if text is present on screen."""
    return find_label_with_text(lv.screen_active(), text) is not None


def click_keyboard_button(keyboard, button_text, use_direct=True):
    """
    Click a keyboard button reliably.
    
    This function handles the complexity of clicking keyboard buttons.
    For MposKeyboard, it directly manipulates the textarea (most reliable).
    For raw lv.keyboard, it uses simulate_click with coordinates.
    
    Args:
        keyboard: MposKeyboard instance or lv.keyboard widget
        button_text: Text of the button to click (e.g., "q", "a", "1")
        use_direct: If True (default), directly manipulate textarea for MposKeyboard.
                   If False, use simulate_click with coordinates.
        
    Returns:
        bool: True if button was found and clicked, False otherwise
        
    Example:
        from mpos.ui.keyboard import MposKeyboard
        from mpos.ui.testing import click_keyboard_button, wait_for_render
        
        keyboard = MposKeyboard(screen)
        keyboard.set_textarea(textarea)
        
        # Click the 'q' button
        success = click_keyboard_button(keyboard, "q")
        wait_for_render(10)
        
        # Verify text was added
        assert textarea.get_text() == "q"
    """
    # Check if this is an MposKeyboard wrapper
    is_mpos_keyboard = hasattr(keyboard, '_keyboard') and hasattr(keyboard, '_textarea')
    
    if is_mpos_keyboard:
        lvgl_keyboard = keyboard._keyboard
    else:
        lvgl_keyboard = keyboard
    
    # Find button index by searching through all buttons
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
        print(f"click_keyboard_button: Button '{button_text}' not found on keyboard")
        return False
    
    if use_direct and is_mpos_keyboard:
        # For MposKeyboard, directly manipulate the textarea
        # This is the most reliable approach for testing
        textarea = keyboard._textarea
        if textarea is None:
            print(f"click_keyboard_button: No textarea connected to keyboard")
            return False
        
        current_text = textarea.get_text()
        
        # Handle special keys (matching keyboard.py logic)
        if button_text == lv.SYMBOL.BACKSPACE:
            new_text = current_text[:-1]
        elif button_text == " " or button_text == keyboard.LABEL_SPACE:
            new_text = current_text + " "
        elif button_text in [lv.SYMBOL.UP, lv.SYMBOL.DOWN, keyboard.LABEL_LETTERS,
                            keyboard.LABEL_NUMBERS_SPECIALS, keyboard.LABEL_SPECIALS,
                            lv.SYMBOL.OK]:
            # Mode switching or OK - don't modify text
            print(f"click_keyboard_button: '{button_text}' is a control key, not adding to textarea")
            wait_for_render(10)
            return True
        else:
            # Regular character
            new_text = current_text + button_text
        
        textarea.set_text(new_text)
        wait_for_render(10)
        print(f"click_keyboard_button: Clicked '{button_text}' at index {button_idx} using direct textarea manipulation")
    else:
        # Use coordinate-based clicking
        coords = get_keyboard_button_coords(keyboard, button_text)
        if coords:
            simulate_click(coords['center_x'], coords['center_y'])
            wait_for_render(20)  # More time for event processing
            print(f"click_keyboard_button: Clicked '{button_text}' at ({coords['center_x']}, {coords['center_y']}) using simulate_click")
        else:
            print(f"click_keyboard_button: Could not get coordinates for '{button_text}'")
            return False
    
    return True
