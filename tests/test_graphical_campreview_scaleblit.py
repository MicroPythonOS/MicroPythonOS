"""
Graphical regression test for camera preview color fidelity through the
LVGL image blit, both 1:1 and scaled.

Motivation: on the Waveshare ESP32-S3-Touch-LCD-3.5, the camera preview
renders with badly wrong colors ("x-ray") even though the raw RGB565
frames from the sensor are correct. The one structural difference from
boards where preview colors are fine (e.g. Touch-LCD-2) is that the
preview image is scaled (set_scale != 256), which sends the blit through
LVGL's software transform path instead of a plain copy.

This test feeds a synthetic RGB565 color-bar frame through the real
CameraActivity preview widget and samples the rendered screen:
- test_scaled_preview_colors: 192x192 source scaled to 240x240 (scale=320)
- test_unscaled_preview_colors: forced scale=256 control
"""

import struct
import unittest

import lvgl as lv

import mpos.ui
from mpos import CameraManager
from mpos.ui.camera_activity import CameraActivity
from mpos.ui.testing import capture_screenshot, wait_for_render

SRC_W = 192
SRC_H = 192

# 6 vertical bars in RGB565: red, green, blue, white, black, yellow
BAR_COLORS = [0xF800, 0x07E0, 0x001F, 0xFFFF, 0x0000, 0xFFE0]


def make_colorbar_frame():
    bar_w = SRC_W // len(BAR_COLORS)
    row = b''.join(
        struct.pack('<H', BAR_COLORS[min(x // bar_w, len(BAR_COLORS) - 1)])
        for x in range(SRC_W)
    )
    return row * SRC_H


def rgb565_to_rgb888(v):
    r = (v >> 11) & 0x1F
    g = (v >> 5) & 0x3F
    b = v & 0x1F
    return (r * 255 // 31, g * 255 // 63, b * 255 // 31)


class TestCameraPreviewScaledBlit(unittest.TestCase):

    def setUp(self):
        # Own a bare screen: the active screen left behind by earlier
        # graphical tests (or the live launcher) may carry a layout that
        # repositions children, which would move the image away from the
        # coordinates sampled below.
        self.prev_screen = lv.screen_active()
        self.screen = lv.obj()
        self.screen.set_style_pad_all(0, 0)
        self.screen.set_style_border_width(0, 0)
        lv.screen_load(self.screen)
        self.saved_cameras = CameraManager._cameras
        CameraManager._cameras = [
            CameraManager.Camera(
                lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_FRONT,
                rgb565_byte_swap=False,
                rotation_degrees=0,
            )
        ]
        self.frame = make_colorbar_frame()

    def tearDown(self):
        CameraManager._cameras = self.saved_cameras
        if getattr(self, 'activity', None) and self.activity.image:
            self.activity.image_dsc.data = None
            self.activity.image.delete()
        lv.screen_load(self.prev_screen)
        self.screen.delete()

    def _show_preview(self):
        self.activity = CameraActivity()
        self.activity.image = lv.image(self.screen)
        self.activity.image.set_pos(0, 0)
        self.activity.width = SRC_W
        self.activity.height = SRC_H
        self.activity.colormode = True
        self.activity.update_preview_image()
        self.activity.image_dsc.data = self.frame
        self.activity.image.set_src(self.activity.image_dsc)

    def _screenshot(self):
        self.shot_w = mpos.ui.DisplayMetrics.width()
        self.shot_h = mpos.ui.DisplayMetrics.height()
        return capture_screenshot(width=self.shot_w, height=self.shot_h)

    def _sample(self, shot, x, y):
        v = struct.unpack_from('<H', shot, (y * self.shot_w + x) * 2)[0]
        return rgb565_to_rgb888(v)

    def _assert_bars(self, shot, rendered_w, msg):
        bar_w = rendered_w // len(BAR_COLORS)
        img = self.activity.image
        x0, y0 = img.get_x(), img.get_y()
        errors = []
        for i, expected565 in enumerate(BAR_COLORS):
            x = x0 + i * bar_w + bar_w // 2
            got = self._sample(shot, x, y0 + 100)
            want = rgb565_to_rgb888(expected565)
            if any(abs(g - w) > 40 for g, w in zip(got, want)):
                errors.append("bar %d at x=%d: want RGB%s got RGB%s" % (i, x, want, got))
        self.assertFalse(errors, "%s: %s" % (msg, "; ".join(errors)))

    def test_scaled_preview_colors(self):
        self._show_preview()
        # e.g. 320x240 display -> target 240, scale 240*256/192 = 320
        scale = self.activity.image.get_scale_x()
        self.assertNotEqual(scale, 256, "test setup expects a scaled preview")
        wait_for_render()
        shot = self._screenshot()
        rendered_w = SRC_W * scale // 256
        self._assert_bars(shot, rendered_w, "scaled blit (scale=%d)" % scale)

    def test_unscaled_preview_colors(self):
        self._show_preview()
        self.activity.image.set_scale(256)  # force 1:1 control
        # Shrink the widget to its content: update_preview_image sized it for
        # the scaled preview, and a scaled image is placed about its pivot, so
        # unscaled content would sit centered (offset) inside the larger box.
        self.activity.image.set_size(SRC_W, SRC_H)
        wait_for_render()
        shot = self._screenshot()
        self._assert_bars(shot, SRC_W, "1:1 blit (scale=256)")


if __name__ == "__main__":
    unittest.main()
