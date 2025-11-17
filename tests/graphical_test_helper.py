"""
Graphical testing helper module for MicroPythonOS.

This module provides utilities for graphical/visual testing that work on both
desktop (unix/macOS) and device (ESP32).

Important: Tests using this module should be run with boot and main files
already executed (so display, theme, and UI infrastructure are initialized).

Usage:
    from graphical_test_helper import wait_for_render, capture_screenshot

    # Start your app
    mpos.apps.start_app("com.example.myapp")

    # Wait for UI to render
    wait_for_render()

    # Verify content
    assert verify_text_present(lv.screen_active(), "Expected Text")

    # Capture screenshot
    capture_screenshot("tests/screenshots/mytest.raw")

    # Simulate click at coordinates
    simulate_click(160, 120)  # Click at center of 320x240 screen
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

    Args:
        iterations: Number of task handler iterations to run (default: 10)
    """
    import time
    for _ in range(iterations):
        lv.task_handler()
        time.sleep(0.01)  # Small delay between iterations


def capture_screenshot(filepath, width=320, height=240, color_format=lv.COLOR_FORMAT.RGB565):
    print(f"capture_screenshot writing to {filepath}")
    """
    Capture screenshot of current screen using LVGL snapshot.

    The screenshot is saved as raw binary data in the specified color format.
    To convert RGB565 to PNG, use:
        ffmpeg -vcodec rawvideo -f rawvideo -pix_fmt rgb565 -s 320x240 -i file.raw file.png

    Args:
        filepath: Path where to save the raw screenshot data
        width: Screen width in pixels (default: 320)
        height: Screen height in pixels (default: 240)
        color_format: LVGL color format (default: RGB565 for memory efficiency)

    Returns:
        bytearray: The screenshot buffer

    Raises:
        Exception: If screenshot capture fails
    """
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


def get_all_labels(obj, labels=None):
    """
    Recursively find all label widgets in the object hierarchy.

    This traverses the entire widget tree starting from obj and
    collects all LVGL label objects.

    Args:
        obj: LVGL object to search (typically lv.screen_active())
        labels: Internal accumulator list (leave as None)

    Returns:
        list: List of all label objects found in the hierarchy
    """
    if labels is None:
        labels = []

    # Check if this object is a label
    try:
        if obj.get_class() == lv.label_class:
            labels.append(obj)
    except:
        pass  # Not a label or no get_class method

    # Recursively check children
    try:
        child_count = obj.get_child_count()
        for i in range(child_count):
            child = obj.get_child(i)
            get_all_labels(child, labels)
    except:
        pass  # No children or error accessing them

    return labels


def find_label_with_text(obj, search_text):
    """
    Find a label widget containing specific text.

    Searches the entire widget hierarchy for a label whose text
    contains the search string (substring match).

    Args:
        obj: LVGL object to search (typically lv.screen_active())
        search_text: Text to search for (can be substring)

    Returns:
        LVGL label object if found, None otherwise
    """
    labels = get_all_labels(obj)
    for label in labels:
        try:
            text = label.get_text()
            if search_text in text:
                return label
        except:
            pass  # Error getting text from this label
    return None


def get_screen_text_content(obj):
    """
    Extract all text content from all labels on screen.

    Useful for debugging or comprehensive text verification.

    Args:
        obj: LVGL object to search (typically lv.screen_active())

    Returns:
        list: List of all text strings found in labels
    """
    labels = get_all_labels(obj)
    texts = []
    for label in labels:
        try:
            text = label.get_text()
            if text:
                texts.append(text)
        except:
            pass  # Error getting text
    return texts


def verify_text_present(obj, expected_text):
    """
    Verify that expected text is present somewhere on screen.

    This is the primary verification method for graphical tests.
    It searches all labels for the expected text.

    Args:
        obj: LVGL object to search (typically lv.screen_active())
        expected_text: Text that should be present (can be substring)

    Returns:
        bool: True if text found, False otherwise
    """
    return find_label_with_text(obj, expected_text) is not None


def print_screen_labels(obj):
    """
    Debug helper: Print all label text found on screen.

    Useful for debugging tests to see what text is actually present.

    Args:
        obj: LVGL object to search (typically lv.screen_active())
    """
    texts = get_screen_text_content(obj)
    print(f"Found {len(texts)} labels on screen:")
    for i, text in enumerate(texts):
        print(f"  {i}: {text}")


def _touch_read_cb(indev_drv, data):
    """
    Internal callback for simulated touch input device.

    This callback is registered with LVGL and provides touch state
    when simulate_click() is used.

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

    To find object coordinates for clicking, use:
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
        # Click at screen center (320x240)
        simulate_click(160, 120)

        # Click on a specific button
        button_area = lv.area_t()
        button.get_coords(button_area)
        simulate_click(button_area.x1 + 10, button_area.y1 + 10)
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
