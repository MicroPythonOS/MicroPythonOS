"""
Graphical test demonstrating how an invalid image path can break fs_driver.py.

This test shows that when an lv.image widget tries to load a non-existent file
via the "M:" fs_driver, it causes RuntimeError in _fs_open_cb. The error from
this callback can leave the fs driver in a broken state, preventing subsequent
valid images from loading correctly.

The bug manifests because _fs_open_cb raises RuntimeError on ENOENT, and this
exception may corrupt internal LVGL/fs_driver state.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_fs_driver_invalid_image.py
    Device:  ./tests/unittest.sh tests/test_graphical_fs_driver_invalid_image.py --ondevice
"""

import unittest
from mpos.ui.testing import GraphicalTestCase, wait_for_render
import lvgl as lv


class TestFsDriverInvalidImage(GraphicalTestCase):
    """Test that demonstrates fs_driver breakage from invalid image paths."""

    # Known working image path in the filesystem
    VALID_IMAGE_PATH = "M:builtin/res/mipmap-mdpi/MicroPythonOS-logo-white-long-w296.png"
    # Invalid image path that does not exist
    INVALID_IMAGE_PATH = "M:/path/to/nonexistent_image.png"

    def test_valid_image_loads_before_invalid(self):
        """Verify that a valid image loads successfully before any invalid attempts."""
        img = lv.image(self.screen)
        img.set_src(self.VALID_IMAGE_PATH)
        img.center()
        self.wait_for_render(20)

        # Check that the image widget has non-zero dimensions (image loaded)
        w = img.get_width()
        h = img.get_height()
        print(f"Valid image dimensions before invalid attempt: {w}x{h}")
        self.assertTrue(w > 0, "Valid image should have width > 0")
        self.assertTrue(h > 0, "Valid image should have height > 0")

    def test_invalid_image_causes_error(self):
        """Confirm that loading an invalid image path triggers an error."""
        img = lv.image(self.screen)

        # This should trigger RuntimeError in fs_driver._fs_open_cb
        # The error shows: RuntimeError: fs_open_callback(bad_image.png) exception: [Errno 2] ENOENT
        print(f"Attempting to load invalid image: {self.INVALID_IMAGE_PATH}")
        img.set_src(self.INVALID_IMAGE_PATH)
        img.center()
        self.wait_for_render(20)

        # The image should have zero or minimal dimensions since it failed to load
        w = img.get_width()
        h = img.get_height()
        print(f"Invalid image dimensions: {w}x{h}")
        # Note: LVGL may show a placeholder or error indicator

    def test_invalid_then_valid_image_demonstrates_breakage(self):
        """
        Demonstrate that loading an invalid image can break subsequent valid image loading.

        This is the main test that shows the bug: after attempting to load an
        invalid image path through the M: fs_driver, subsequent attempts to load
        valid images may fail because the fs_driver is left in a broken state.

        The expected behavior (after a fix) would be that valid images still load
        correctly even after an invalid image attempt.
        """
        # First, create an image widget and try to load the INVALID path
        img_bad = lv.image(self.screen)
        print(f"Step 1: Attempting to load INVALID image: {self.INVALID_IMAGE_PATH}")
        img_bad.set_src(self.INVALID_IMAGE_PATH)
        img_bad.align(lv.ALIGN.TOP_MID, 0, 10)
        self.wait_for_render(20)

        bad_w = img_bad.get_width()
        bad_h = img_bad.get_height()
        print(f"Invalid image dimensions: {bad_w}x{bad_h}")

        # Now, create a SECOND image widget and try to load a VALID path
        # If the fs_driver is broken, this may fail even though the path is valid
        img_good = lv.image(self.screen)
        print(f"Step 2: Attempting to load VALID image: {self.VALID_IMAGE_PATH}")
        img_good.set_src(self.VALID_IMAGE_PATH)
        img_good.align(lv.ALIGN.BOTTOM_MID, 0, -10)
        self.wait_for_render(20)

        good_w = img_good.get_width()
        good_h = img_good.get_height()
        print(f"Valid image dimensions after invalid attempt: {good_w}x{good_h}")

        # The valid image SHOULD load correctly with non-zero dimensions
        # If this assertion fails, it demonstrates the fs_driver breakage bug
        self.assertTrue(
            good_w > 0,
            f"Valid image should have width > 0 even after invalid image attempt, but got {good_w}",
        )
        self.assertTrue(
            good_h > 0,
            f"Valid image should have height > 0 even after invalid image attempt, but got {good_h}",
        )

        # Additional check: the valid image should have reasonable dimensions
        # The MicroPythonOS logo is 296 pixels wide
        self.assertTrue(
            good_w >= 100,
            f"Valid image width {good_w} seems too small for the logo",
        )

    def test_multiple_invalid_images_compound_breakage(self):
        """
        Test that multiple invalid image loads compound the problem.

        This demonstrates that repeated errors from fs_driver may make
        the situation worse.
        """
        # Load multiple invalid images
        invalid_paths = [
            "M:/does/not/exist1.png",
            "M:/does/not/exist2.png",
            "M:/fake/path/image.png",
        ]

        for i, invalid_path in enumerate(invalid_paths):
            img = lv.image(self.screen)
            print(f"Loading invalid image {i+1}: {invalid_path}")
            img.set_src(invalid_path)
            img.align(lv.ALIGN.TOP_LEFT, 10, 10 + i * 30)
            self.wait_for_render(10)
            img.delete()
            self.wait_for_render(5)

        # Now try to load a valid image
        img_valid = lv.image(self.screen)
        print(f"Loading valid image after {len(invalid_paths)} invalid attempts: {self.VALID_IMAGE_PATH}")
        img_valid.set_src(self.VALID_IMAGE_PATH)
        img_valid.center()
        self.wait_for_render(20)

        w = img_valid.get_width()
        h = img_valid.get_height()
        print(f"Valid image dimensions after multiple invalid attempts: {w}x{h}")

        self.assertTrue(
            w > 0,
            f"Valid image should still load after {len(invalid_paths)} invalid attempts",
        )

    def test_same_widget_invalid_then_valid(self):
        """
        Test setting invalid then valid source on the SAME image widget.

        This tests whether the widget itself or the driver gets corrupted
        when the same widget experiences a load failure then success.
        """
        img = lv.image(self.screen)
        img.center()

        # First set invalid source
        print(f"Setting INVALID source on image widget: {self.INVALID_IMAGE_PATH}")
        img.set_src(self.INVALID_IMAGE_PATH)
        self.wait_for_render(20)

        w_bad = img.get_width()
        h_bad = img.get_height()
        print(f"After invalid src: {w_bad}x{h_bad}")

        # Now set valid source on the SAME widget
        print(f"Setting VALID source on same widget: {self.VALID_IMAGE_PATH}")
        img.set_src(self.VALID_IMAGE_PATH)
        self.wait_for_render(20)

        w_good = img.get_width()
        h_good = img.get_height()
        print(f"After valid src: {w_good}x{h_good}")

        self.assertTrue(
            w_good > 0,
            f"Same widget should accept valid source after invalid, but width is {w_good}",
        )
        self.assertTrue(
            h_good > 0,
            f"Same widget should accept valid source after invalid, but height is {h_good}",
        )
