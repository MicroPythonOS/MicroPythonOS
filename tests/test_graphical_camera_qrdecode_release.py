"""
Graphical test: the Camera activity frees the QR decoder when it stops scanning.

qrdecode keeps its decoder (about 400 KB at 640x640) between calls, so live
scanning doesn't allocate and free it for every frame. The Camera activity
must call qrdecode.release() when QR scanning stops and when it is paused.

CameraActivity.onCreate builds the UI and, through setContentView and
onResume, starts the camera when the board has one. A fake qrdecode module in
sys.modules counts the release() calls.
"""

import logging
import sys
import unittest

from mpos import Intent
from mpos.ui.camera_activity import CameraActivity
from mpos.ui.testing import wait_for_render


class _FakeQRDecode:
    def __init__(self):
        self.releases = 0

    def release(self):
        self.releases += 1


class _FakeTimer:
    def __init__(self):
        self.deletes = 0

    def delete(self):
        self.deletes += 1


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        # MicroPython reuses the LogRecord object, so snapshot the message now.
        self.records.append(record.message)


class TestGraphicalCameraQRDecodeRelease(unittest.TestCase):

    def setUp(self):
        self.saved_qrdecode = sys.modules.get("qrdecode")
        self.fake = _FakeQRDecode()
        sys.modules["qrdecode"] = self.fake
        self.activity = CameraActivity()
        self.activity.intent = Intent(activity_class=CameraActivity)
        self.activity.appFullName = "com.micropythonos.camera"
        self.activity.onCreate()
        wait_for_render(iterations=10)

    def tearDown(self):
        if self.saved_qrdecode is None:
            sys.modules.pop("qrdecode", None)
        else:
            sys.modules["qrdecode"] = self.saved_qrdecode
        try:
            from mpos.ui import back_screen
            back_screen()
            wait_for_render(iterations=5)
        except Exception:
            pass

    def test_stop_qr_decoding_releases_decoder(self):
        self.activity.scanqr_mode = True
        self.activity.stop_qr_decoding(activate_non_qr_mode=False)
        self.assertFalse(self.activity.scanqr_mode)
        self.assertEqual(self.fake.releases, 1)

    def test_pause_releases_decoder(self):
        self.activity.onPause(self.activity.main_screen)
        self.assertEqual(self.fake.releases, 1)
        # tearDown's back_screen() pauses the activity again: the timer must not be deleted twice
        self.assertIsNone(self.activity.capture_timer)

    def test_stop_cam_twice_deletes_capture_timer_once(self):
        self.activity.stop_cam()  # stops the real camera, if onCreate started one
        timer = _FakeTimer()
        self.activity.capture_timer = timer
        self.activity.stop_cam()
        self.activity.stop_cam()
        self.assertEqual(timer.deletes, 1)
        self.assertIsNone(self.activity.capture_timer)

    def test_pause_survives_release_failure(self):
        stopped = []
        self.activity.stop_cam = lambda: stopped.append(True)
        sys.modules["qrdecode"] = object()
        handler = _ListHandler()
        logger = logging.getLogger("mpos.ui.camera_activity")
        logger.handlers.append(handler)
        try:
            self.activity.onPause(self.activity.main_screen)
        finally:
            logger.handlers.remove(handler)
            del self.activity.stop_cam
        self.assertEqual(stopped, [True])
        warnings = [m for m in handler.records if m.startswith("Could not release the QR decoder")]
        self.assertEqual(len(warnings), 1)

    def test_pause_releases_decoder_when_stop_cam_raises(self):
        def failing_stop_cam():
            raise RuntimeError("camera deinit failed")

        self.activity.stop_cam = failing_stop_cam
        try:
            with self.assertRaises(RuntimeError):
                self.activity.onPause(self.activity.main_screen)
        finally:
            del self.activity.stop_cam
        self.assertEqual(self.fake.releases, 1)


if __name__ == "__main__":
    unittest.main()
