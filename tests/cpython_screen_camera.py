#!/usr/bin/env python3
"""CPython tests for scripts/mpos_screen_camera.py — no camera or device needed.

Builds a synthetic framebuffer, simulates a webcam view with a known
scale/rotation/blur/JPEG compression, and checks that the alignment and the
quality metrics behave as expected. Skipped when numpy/opencv are missing.

Usage:
    python3 tests/cpython_screen_camera.py
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover - depends on the host
    cv2 = None
    np = None

from scripts import mpos_screen_camera as cam  # noqa: E402


HAVE_IMAGE_LIBS = cv2 is not None and np is not None


def make_reference(width=320, height=240, seed=1234):
    """A framebuffer-like launcher: coloured icon tiles with small labels."""
    rng = np.random.default_rng(seed)
    image = np.full((height, width, 3), 238, np.uint8)
    for row in range(4):
        for col in range(5):
            x = 14 + col * 60
            y = 12 + row * 55
            color = [int(value) for value in rng.integers(20, 210, 3)]
            cv2.rectangle(image, (x, y), (x + 42, y + 34), color, -1)
            cv2.rectangle(image, (x, y), (x + 42, y + 34), (30, 30, 30), 1)
            cv2.putText(image, "I%d%d" % (row, col), (x + 2, y + 47),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.33, (20, 20, 20), 1, cv2.LINE_AA)
    return image


def simulate_camera(reference, scale=1.6, angle_deg=4.0, sigma=1.0, jpeg_quality=85,
                    canvas=(1920, 1080)):
    height, width = reference.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle_deg, scale)
    matrix[0, 2] += (canvas[0] - width * scale) / 2.0
    matrix[1, 2] += (canvas[1] - height * scale) / 2.0
    frame = cv2.warpAffine(reference, matrix, canvas, flags=cv2.INTER_LINEAR,
                           borderValue=(24, 24, 24))
    if sigma > 0:
        frame = cv2.GaussianBlur(frame, (0, 0), sigma)
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    if ok:
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    return frame


@unittest.skipUnless(HAVE_IMAGE_LIBS, "numpy/opencv-python-headless not installed")
class TestScreenCamera(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.reference = make_reference()

    def test_align_recovers_simulated_view(self):
        frame = simulate_camera(self.reference, scale=1.6, angle_deg=4.0, sigma=1.0)
        result = cam.align(self.reference, frame)
        self.assertIsNotNone(result, "SIFT alignment failed on a synthetic view")
        self.assertGreaterEqual(result.inliers, 20)
        self.assertAlmostEqual(result.scale, 1.6, delta=0.25)
        self.assertLess(min(abs(result.rotation_deg - 4.0), abs(result.rotation_deg + 4.0)), 3.0)
        measured = cam.metrics(self.reference, result.aligned, result.quad)
        self.assertGreater(measured["ncc_gray"], 0.85)
        self.assertGreater(measured["ncc_gradient"], 0.60)
        self.assertGreater(measured["cell_ncc_min"], 0.50)
        self.assertAlmostEqual(measured["eff_px_per_screen_px"], 1.6, delta=0.25)

    def test_metrics_identical_image(self):
        measured = cam.metrics(self.reference, self.reference, None)
        self.assertEqual(measured["ncc_gray"], 1.0)
        self.assertEqual(measured["ncc_gradient"], 1.0)
        self.assertEqual(measured["cell_ncc_min"], 1.0)

    def test_sharpness_drops_with_blur(self):
        values = []
        for sigma in (0.0, 1.0, 2.5, 4.0):
            blurred = cv2.GaussianBlur(self.reference, (0, 0), sigma) if sigma else self.reference
            measured = cam.metrics(self.reference, blurred, None)
            values.append(measured["laplacian_var"])
        self.assertGreater(values[0], values[1])
        self.assertGreater(values[1], values[2])
        self.assertGreater(values[2], values[3])

    def test_align_rejects_featureless_frame(self):
        blank = np.full((1080, 1920, 3), 128, np.uint8)
        self.assertIsNone(cam.align(self.reference, blank))

    def test_focus_sweep_picks_sharpest(self):
        focus_frames = {
            0: cv2.GaussianBlur(self.reference, (0, 0), 4.0),
            10: cv2.GaussianBlur(self.reference, (0, 0), 2.0),
            20: cv2.GaussianBlur(self.reference, (0, 0), 0.5),
        }
        state = {"focus": None}

        def apply_fn(config):
            state["focus"] = config.focus

        def capture_fn():
            return focus_frames[state["focus"]]

        best, rows = cam.focus_sweep(
            config=cam.CameraConfig(), reference_bgr=self.reference,
            values=[0, 10, 20], repeats=1, settle=0.0,
            capture_fn=capture_fn, apply_fn=apply_fn,
        )
        self.assertEqual(best, 20, "focus sweep should pick the sharpest frame")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["focus"], 0)

    def test_thresholds(self):
        measured = {"inliers": 100, "ncc_gray": 0.9, "ncc_gradient": 0.8,
                    "cell_ncc_min": 0.85, "eff_px_per_screen_px": 1.2}
        ok, failures = cam.check_thresholds(measured)
        self.assertTrue(ok)
        self.assertEqual(failures, {})
        bad = dict(measured, inliers=5)
        ok, failures = cam.check_thresholds(bad)
        self.assertFalse(ok)
        self.assertIn("inliers", failures)

    def test_config_roundtrip(self):
        config = cam.CameraConfig(device="/dev/video9", focus=45, auto_focus=False,
                                  exposure=389, auto_exposure=False, wb_temperature=4300,
                                  gain=49, out_dir="tmp/camtests")
        restored = cam.CameraConfig.from_dict(config.to_dict())
        self.assertEqual(restored, config)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "camera.json")
            cam.save_config(path, config)
            self.assertEqual(cam.load_config(path), config)
            with open(path) as handle:
                self.assertEqual(json.load(handle)["focus"], 45)

    def test_save_artifacts(self):
        frame = simulate_camera(self.reference)
        result = cam.align(self.reference, frame)
        self.assertIsNotNone(result)
        measured = cam.metrics(self.reference, result.aligned, result.quad)
        measured["ok"] = True
        with tempfile.TemporaryDirectory() as tmp:
            paths = cam.save_artifacts(tmp, "unit", self.reference, frame, result.aligned, measured)
            for path in paths.values():
                self.assertTrue(os.path.isfile(path), path)
            jsonl = os.path.join(tmp, "metrics.jsonl")
            self.assertTrue(os.path.isfile(jsonl))
            with open(jsonl) as handle:
                self.assertEqual(json.loads(handle.readline())["label"], "unit")

    def test_list_devices_shape(self):
        devices = cam.list_devices()
        self.assertIsInstance(devices, list)
        for entry in devices:
            self.assertIn("device", entry)
            self.assertIn("name", entry)


if __name__ == "__main__":
    unittest.main()
