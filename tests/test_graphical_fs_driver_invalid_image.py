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
3. After an invalid image load fails, the SAME widget can load a valid image
4. Multiple invalid loads don't corrupt the driver for new widgets

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
    VALID_IMAGE_PATH = "M:builtin/MicroPythonOS-logo-white-long-w296.png"
    # Fixed invalid path
    INVALID_IMAGE_PATH = "M:/path/to/nonexistent_image.png"

    def _wait_ui(self, seconds=0.5):
        """Wait for UI to fully update - combines render cycles with real time."""
        self.wait_for_render(20)
        time.sleep(seconds)
        self.wait_for_render(20)

    def test_01_valid_image_loads(self):
        """Verify that a valid image loads successfully."""
        img = lv.image(self.screen)
        img.set_src(self.VALID_IMAGE_PATH)
        img.center()
        self._wait_ui()

        w = img.get_width()
        h = img.get_height()
        print(f"Valid image dimensions: {w}x{h}")
        self.assertTrue(w > 0, "Valid image should have width > 0")
        self.assertTrue(h > 0, "Valid image should have height > 0")

    def test_02_invalid_image_fails_gracefully(self):
        """Confirm that loading an invalid image path fails gracefully."""
        img = lv.image(self.screen)

        print(f"Attempting to load invalid image: {self.INVALID_IMAGE_PATH}")
        img.set_src(self.INVALID_IMAGE_PATH)
        img.center()
        self._wait_ui()

        w = img.get_width()
        h = img.get_height()
        print(f"Invalid image dimensions: {w}x{h}")
        self.assertEqual(w, 0, "Invalid image should have width == 0")
        self.assertEqual(h, 0, "Invalid image should have height == 0")

    def test_03_same_widget_invalid_then_valid(self):
        """
        Test that the SAME widget can load a valid image after failing to load
        an invalid image.

        This is the key test for the fs_driver fix. When _fs_open_cb raised
        RuntimeError, it could corrupt internal state and prevent the same
        widget from loading valid images afterwards. With the fix (returning
        None instead of raising), recovery should work.
        """
        img = lv.image(self.screen)
        img.center()

        # First, try to load an INVALID image
        print(f"Step 1: Loading INVALID image: {self.INVALID_IMAGE_PATH}")
        img.set_src(self.INVALID_IMAGE_PATH)
        self._wait_ui()

        w1 = img.get_width()
        h1 = img.get_height()
        print(f"After invalid: {w1}x{h1}")
        self.assertEqual(w1, 0, "Invalid image should have width == 0")

        # Now try to load a VALID image on the SAME widget
        print(f"Step 2: Loading VALID image on same widget: {self.VALID_IMAGE_PATH}")
        img.set_src(self.VALID_IMAGE_PATH)
        self._wait_ui()

        w2 = img.get_width()
        h2 = img.get_height()
        print(f"After valid: {w2}x{h2}")

        self.assertTrue(
            w2 > 0,
            f"Same widget should load valid image after invalid failed, but got width={w2}",
        )

    def test_04_multiple_invalid_then_new_widget_valid(self):
        """
        Test that after multiple invalid image loads, a NEW widget can still
        load valid images.

        This tests whether the fs_driver global state gets corrupted by
        repeated errors.
        """
        # Load several invalid images on different widgets
        print("Loading multiple invalid images...")
        for i in range(5):
            img = lv.image(self.screen)
            invalid_path = f"M:/nonexistent/image_{i}.png"
            print(f"  Loading invalid: {invalid_path}")
            img.set_src(invalid_path)
            img.align(lv.ALIGN.TOP_LEFT, i * 50, 10)
            self._wait_ui(0.2)

        # Give extra time for any async processing
        self._wait_ui(1.0)

        # Now create a NEW widget and try to load a valid image
        img_valid = lv.image(self.screen)
        print(f"Loading valid image on new widget: {self.VALID_IMAGE_PATH}")
        img_valid.set_src(self.VALID_IMAGE_PATH)
        img_valid.align(lv.ALIGN.BOTTOM_MID, 0, -10)
        self._wait_ui()

        w = img_valid.get_width()
        h = img_valid.get_height()
        print(f"Valid image dimensions on new widget: {w}x{h}")

        self.assertTrue(
            w > 0,
            f"New widget should load valid image after multiple invalid loads, but got width={w}",
        )

    def test_05_interleaved_invalid_valid_loads(self):
        """
        Test interleaving invalid and valid image loads.

        This simulates a more realistic scenario where valid and invalid
        loads might happen in unpredictable order.
        """
        results = []

        # Interleave invalid and valid loads
        for i in range(3):
            # Load invalid
            img_bad = lv.image(self.screen)
            invalid_path = f"M:/bad/path_{i}.png"
            print(f"Round {i+1}: Loading invalid: {invalid_path}")
            img_bad.set_src(invalid_path)
            img_bad.align(lv.ALIGN.TOP_LEFT, i * 100, 10)
            self._wait_ui(0.3)

            # Load valid on a new widget
            img_good = lv.image(self.screen)
            print(f"Round {i+1}: Loading valid: {self.VALID_IMAGE_PATH}")
            img_good.set_src(self.VALID_IMAGE_PATH)
            img_good.align(lv.ALIGN.TOP_LEFT, i * 100, 80)
            self._wait_ui(0.3)

            w = img_good.get_width()
            h = img_good.get_height()
            print(f"Round {i+1}: Valid image dimensions: {w}x{h}")
            results.append((w, h))

        # All valid images should have loaded successfully
        for i, (w, h) in enumerate(results):
            self.assertTrue(
                w > 0,
                f"Round {i+1}: Valid image should have loaded, but got width={w}",
            )
