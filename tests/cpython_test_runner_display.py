#!/usr/bin/env python3
"""
CPython unit tests for the desktop display settings of scripts/test_runner.py.

Desktop test runs are headless by default (SDL's dummy video driver), so the
test binaries open no window that takes the keyboard focus. --show-window or
MPOS_TEST_SHOW_WINDOW=1 brings the window back. Nothing is started here: the
tests only check the environment the test binaries would inherit.

Usage:
    python3 tests/cpython_test_runner_display.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts import test_runner


class TestDesktopDisplay(unittest.TestCase):
    def test_headless_by_default(self):
        env = {}
        self.assertTrue(test_runner._configure_desktop_display(False, env))
        self.assertEqual(env, {
            "SDL_VIDEO_DRIVER": "dummy",
            "SDL_VIDEODRIVER": "dummy",
            "SDL_MAC_BACKGROUND_APP": "1",
        })

    def test_show_window_flag_leaves_the_environment_alone(self):
        env = {}
        self.assertFalse(test_runner._configure_desktop_display(True, env))
        self.assertEqual(env, {})

    def test_show_window_environment_variable(self):
        env = {"MPOS_TEST_SHOW_WINDOW": "1"}
        self.assertFalse(test_runner._configure_desktop_display(False, env))
        self.assertEqual(env, {"MPOS_TEST_SHOW_WINDOW": "1"})

    def test_other_show_window_values_stay_headless(self):
        env = {"MPOS_TEST_SHOW_WINDOW": "0"}
        self.assertTrue(test_runner._configure_desktop_display(False, env))
        self.assertEqual(env["SDL_VIDEO_DRIVER"], "dummy")

    def test_existing_sdl_settings_are_kept(self):
        env = {"SDL_VIDEODRIVER": "x11"}
        test_runner._configure_desktop_display(False, env)
        self.assertEqual(env["SDL_VIDEODRIVER"], "x11")
        self.assertEqual(env["SDL_VIDEO_DRIVER"], "dummy")

    def test_defaults_to_the_process_environment(self):
        saved = dict(os.environ)
        try:
            for key in test_runner.HEADLESS_SDL_ENV:
                os.environ.pop(key, None)
            os.environ.pop("MPOS_TEST_SHOW_WINDOW", None)
            test_runner._configure_desktop_display(False)
            self.assertEqual(os.environ["SDL_MAC_BACKGROUND_APP"], "1")
        finally:
            os.environ.clear()
            os.environ.update(saved)


if __name__ == "__main__":
    unittest.main()
