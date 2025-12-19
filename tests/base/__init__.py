"""
Base test classes for MicroPythonOS testing.

This module provides base classes that encapsulate common test patterns:
- GraphicalTestBase: For tests that require LVGL/UI
- KeyboardTestBase: For tests that involve keyboard interaction

Usage:
    from base import GraphicalTestBase, KeyboardTestBase
    
    class TestMyApp(GraphicalTestBase):
        def test_something(self):
            # self.screen is already set up
            # self.screenshot_dir is configured
            pass
"""

from .graphical_test_base import GraphicalTestBase
from .keyboard_test_base import KeyboardTestBase

__all__ = [
    'GraphicalTestBase',
    'KeyboardTestBase',
]
