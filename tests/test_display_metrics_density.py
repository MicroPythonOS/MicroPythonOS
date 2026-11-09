"""
test_display_metrics_density.py - Density buckets for authored bitmaps.

Issue #289: apps that ship a 1.5x variant of a hero/mascot bitmap need a way to
ask which density class the current screen belongs to, so they can pick the
right asset and fall back to scaling the mdpi one otherwise.

The bucket is chosen by the smaller screen dimension, so portrait and landscape
variants of the same panel resolve identically:
    mdpi: min(width, height) < 300  -> factor 1.0
    hdpi: min(width, height) >= 300 -> factor 1.5

Usage:
    python3 scripts/test_runner.py tests/test_display_metrics_density.py
"""

import unittest

from mpos import DisplayMetrics


class TestDisplayMetricsDensity(unittest.TestCase):
    def setUp(self):
        self._saved_width = DisplayMetrics._width
        self._saved_height = DisplayMetrics._height

    def tearDown(self):
        DisplayMetrics._width = self._saved_width
        DisplayMetrics._height = self._saved_height

    def _assert_bucket(self, width, height, bucket, factor):
        DisplayMetrics.set_resolution(width, height)
        self.assertEqual(DisplayMetrics.density_bucket(), bucket,
                         "wrong bucket for %dx%d" % (width, height))
        self.assertEqual(DisplayMetrics.density_factor(), factor,
                         "wrong factor for %dx%d" % (width, height))

    def test_classic_panel_is_mdpi(self):
        self._assert_bucket(320, 240, "mdpi", 1.0)

    def test_classic_panel_landscape_is_mdpi(self):
        self._assert_bucket(240, 320, "mdpi", 1.0)

    def test_large_panel_is_hdpi(self):
        self._assert_bucket(480, 320, "hdpi", 1.5)

    def test_large_panel_portrait_is_hdpi(self):
        self._assert_bucket(320, 480, "hdpi", 1.5)

    def test_smaller_dimension_decides_the_bucket(self):
        # A wide panel whose small dimension is still classic-class.
        self._assert_bucket(800, 240, "mdpi", 1.0)

    def test_boundary(self):
        self._assert_bucket(300, 300, "hdpi", 1.5)
        self._assert_bucket(299, 400, "mdpi", 1.0)


if __name__ == "__main__":
    unittest.main()
