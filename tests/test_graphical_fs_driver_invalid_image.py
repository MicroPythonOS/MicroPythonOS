"""
Graphical test for fs_driver.py error handling with invalid image paths.

This test verifies that the fs_driver correctly handles attempts to load
non-existent image files without corrupting global state. Previously,
_fs_open_cb raised RuntimeError on ENOENT which could leave LVGL's fs
driver in a broken state. The fix changes it to return None and log an
error instead.

Key behaviors tested:
1. Valid images load successfully
2. Invalid images fail gracefully (0x0 dimensions)
3. After an invalid image load fails, NEW widgets can still load valid images
4. The fs_driver logs errors but doesn't raise exceptions

Known LVGL limitation: A single image widget that fails to load an invalid
image may not recover when given a valid image path later. The workaround
is to delete and recreate the widget.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_fs_driver_invalid_image.py
    Device:  ./tests/unittest.sh tests/test_graphical_fs_driver_invalid_image.py --ondevice
"""

import unittest
from mpos.ui.testing import GraphicalTestCase
import lvgl as lv
import time


class TestFsDriverInvalidImage(GraphicalTestCase):
    """Test fs_driver error handling for invalid image paths."""

    # Known working image path in the filesystem
    VALID_IMAGE_PATH = "M:builtin/res/mipmap-mdpi/MicroPythonOS-logo-white-long-w296.png"

    @staticmethod
    def _unique_invalid_path():
        """Generate a unique invalid path to avoid any caching issues."""
        return f"M:/nonexistent/{time.ticks_ms()}.png"

    def test_01_valid_image_loads(self):
        """Verify that a valid image loads successfully."""
        img = lv.image(self.screen)
        img.set_src(self.VALID_IMAGE_PATH)
        img.center()
        self.wait_for_render(20)

        w = img.get_width()
        h = img.get_height()
        print(f"Valid image dimensions: {w}x{h}")
        self.assertTrue(w > 0, "Valid image should have width > 0")
        self.assertTrue(h > 0, "Valid image should have height > 0")

    def test_02_invalid_image_fails_gracefully(self):
        """Confirm that loading an invalid image path fails gracefully."""
        img = lv.image(self.screen)

        invalid_path = self._unique_invalid_path()
        print(f"Attempting to load invalid image: {invalid_path}")
        img.set_src(invalid_path)
        img.center()
        self.wait_for_render(20)

        w = img.get_width()
        h = img.get_height()
        print(f"Invalid image dimensions: {w}x{h}")
        # Image should have zero dimensions since it failed to load
        self.assertEqual(w, 0, "Invalid image should have width == 0")
        self.assertEqual(h, 0, "Invalid image should have height == 0")

    def test_03_new_widget_loads_valid_after_invalid(self):
        """
        Verify that a NEW widget can load a valid image after another widget
        failed to load an invalid image.

        This is the key test for the fs_driver fix - it ensures that a failed
        load doesn't corrupt global state and prevent subsequent valid loads.
        """
        # First, create a widget and try to load an INVALID path
        img_bad = lv.image(self.screen)
        invalid_path = self._unique_invalid_path()
        print(f"Step 1: Loading INVALID image: {invalid_path}")
        img_bad.set_src(invalid_path)
        img_bad.align(lv.ALIGN.TOP_MID, 0, 10)
        self.wait_for_render(20)

        bad_w = img_bad.get_width()
        bad_h = img_bad.get_height()
        print(f"Invalid image dimensions: {bad_w}x{bad_h}")
        self.assertEqual(bad_w, 0, "Invalid image should fail with width == 0")

        # Now, create a SECOND widget and load a VALID path
        # This should succeed - the fix ensures invalid loads don't break the driver
        img_good = lv.image(self.screen)
        print(f"Step 2: Loading VALID image on new widget: {self.VALID_IMAGE_PATH}")
        img_good.set_src(self.VALID_IMAGE_PATH)
        img_good.align(lv.ALIGN.BOTTOM_MID, 0, -10)
        self.wait_for_render(20)

        good_w = img_good.get_width()
        good_h = img_good.get_height()
        print(f"Valid image dimensions on new widget: {good_w}x{good_h}")

        self.assertTrue(
            good_w > 0,
            f"New widget should load valid image after another widget failed, but got width={good_w}",
        )
        self.assertTrue(
            good_h > 0,
            f"New widget should load valid image after another widget failed, but got height={good_h}",
        )
