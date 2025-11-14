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
"""

import lvgl as lv


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
