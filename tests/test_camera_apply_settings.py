import unittest

from mpos import CameraManager, SharedPreferences
from mpos.ui.camera_settings import CameraSettingsActivity


class RecordingCamera:

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if not name.startswith("set_"):
            raise AttributeError(name)

        def setter(value):
            self.calls.append((name[4:], value))

        return setter

    def names(self):
        return [name for name, _ in self.calls]

    def value(self, name):
        for call_name, call_value in self.calls:
            if call_name == name:
                return call_value
        raise AssertionError("set_%s was never called" % name)


def _make_prefs(**overrides):
    defaults = {}
    defaults.update(CameraSettingsActivity.COMMON_DEFAULTS)
    defaults.update(CameraSettingsActivity.NORMAL_DEFAULTS)
    defaults.update(overrides)
    return SharedPreferences("com.micropythonos.tests.camera_apply_settings", defaults=defaults)


def _apply(**overrides):
    cam = RecordingCamera()
    CameraManager.ov_apply_camera_settings(cam, _make_prefs(**overrides))
    return cam


class TestCameraApplySettingsAuto(unittest.TestCase):

    def setUp(self):
        self.cam = _apply()

    def test_ran_to_completion(self):
        self.assertIn("lenc", self.cam.names())

    def test_auto_exposure_skips_manual_value(self):
        self.assertEqual(self.cam.value("exposure_ctrl"), True)
        self.assertFalse("aec_value" in self.cam.names())

    def test_auto_gain_skips_manual_value(self):
        self.assertEqual(self.cam.value("gain_ctrl"), True)
        self.assertFalse("agc_gain" in self.cam.names())

    def test_auto_white_balance_skips_manual_mode(self):
        self.assertEqual(self.cam.value("whitebal"), True)
        self.assertFalse("wb_mode" in self.cam.names())


class TestCameraApplySettingsManual(unittest.TestCase):

    def test_manual_exposure_applies_value_after_master_switch(self):
        cam = _apply(exposure_ctrl=False, aec_value=700)
        names = cam.names()
        self.assertIn("lenc", names)
        self.assertEqual(cam.value("exposure_ctrl"), False)
        self.assertEqual(cam.value("aec_value"), 700)
        self.assertTrue(names.index("exposure_ctrl") < names.index("aec_value"))

    def test_manual_gain_applies_value_after_master_switch(self):
        cam = _apply(gain_ctrl=False, agc_gain=12)
        names = cam.names()
        self.assertIn("lenc", names)
        self.assertEqual(cam.value("gain_ctrl"), False)
        self.assertEqual(cam.value("agc_gain"), 12)
        self.assertTrue(names.index("gain_ctrl") < names.index("agc_gain"))

    def test_manual_gain_applies_zero_value(self):
        cam = _apply(gain_ctrl=False)
        self.assertEqual(cam.value("agc_gain"), 0)

    def test_manual_white_balance_applies_mode_between_master_switch_and_awb_gain(self):
        cam = _apply(whitebal=False, wb_mode=3)
        names = cam.names()
        self.assertIn("lenc", names)
        self.assertEqual(cam.value("whitebal"), False)
        self.assertEqual(cam.value("wb_mode"), 3)
        self.assertTrue(names.index("whitebal") < names.index("wb_mode"))
        self.assertTrue(names.index("wb_mode") < names.index("awb_gain"))

    def test_all_manual_applies_all_values(self):
        cam = _apply(exposure_ctrl=False, aec_value=450, gain_ctrl=False, agc_gain=5, whitebal=False, wb_mode=1)
        self.assertEqual(cam.value("aec_value"), 450)
        self.assertEqual(cam.value("agc_gain"), 5)
        self.assertEqual(cam.value("wb_mode"), 1)

    def test_manual_exposure_leaves_other_groups_auto(self):
        cam = _apply(exposure_ctrl=False)
        names = cam.names()
        self.assertIn("aec_value", names)
        self.assertFalse("agc_gain" in names)
        self.assertFalse("wb_mode" in names)
