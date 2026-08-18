import unittest

import lvgl as lv

from mpos import CameraManager, DeviceInfo
from mpos.ui.camera_activity import CameraActivity
from mpos.ui.camera_settings import CameraSettingsActivity


class TestCameraColorFormat(unittest.TestCase):
    def setUp(self):
        self.cameras = CameraManager._cameras
        self.hardware_id = DeviceInfo.get_hardware_id()

    def tearDown(self):
        CameraManager._cameras = self.cameras
        DeviceInfo.set_hardware_id(self.hardware_id)

    def make_activity(self, rgb565_byte_swap):
        CameraManager._cameras = [
            CameraManager.Camera(
                lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_FRONT,
                rgb565_byte_swap=rgb565_byte_swap,
            )
        ]
        activity = CameraActivity()
        activity.image = lv.image(lv.screen_active())
        activity.width = 240
        activity.height = 240
        activity.colormode = True
        activity.update_preview_image()
        return activity

    def test_default_camera_uses_rgb565(self):
        activity = self.make_activity(False)
        self.assertEqual(activity.image_dsc.header.cf, lv.COLOR_FORMAT.RGB565)

    def test_swapped_camera_uses_rgb565_swapped(self):
        activity = self.make_activity(True)
        self.assertEqual(
            activity.image_dsc.header.cf,
            lv.COLOR_FORMAT.RGB565_SWAPPED,
        )

    def test_camera_defaults_use_camera_vflip(self):
        CameraManager._cameras = [
            CameraManager.Camera(
                lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_FRONT,
                default_vflip=False,
            )
        ]
        activity = CameraActivity()
        defaults = activity._get_camera_defaults(CameraSettingsActivity.NORMAL_DEFAULTS)
        self.assertFalse(defaults["vflip"])

    def test_k10_camera_buttons_start_with_close_focused(self):
        group = lv.group_get_default()
        group.remove_all_objs()
        DeviceInfo.set_hardware_id("unihiker_k10")
        activity = CameraActivity()
        activity.main_screen = lv.obj()
        activity.close_button = lv.button(activity.main_screen)
        activity.settings_button = lv.button(activity.main_screen)
        activity.qr_button = lv.button(activity.main_screen)
        activity.snap_button = lv.button(activity.main_screen)
        lv.group_focus_obj(activity.settings_button)
        activity._add_focusable_buttons()
        self.assertTrue(group.get_focused() is activity.close_button)

    def test_non_k10_camera_buttons_keep_existing_focus(self):
        group = lv.group_get_default()
        group.remove_all_objs()
        DeviceInfo.set_hardware_id("desktop")
        activity = CameraActivity()
        activity.main_screen = lv.obj()
        activity.close_button = lv.button(activity.main_screen)
        activity.settings_button = lv.button(activity.main_screen)
        activity.qr_button = lv.button(activity.main_screen)
        activity.snap_button = lv.button(activity.main_screen)
        lv.group_focus_obj(activity.settings_button)
        activity._add_focusable_buttons()
        self.assertTrue(group.get_focused() is activity.settings_button)


if __name__ == "__main__":
    unittest.main()
