"""
Base class for graphical tests in MicroPythonOS.

This class provides common setup/teardown patterns for tests that require
LVGL/UI initialization. It handles:
- Screen creation and cleanup
- Screenshot directory configuration
- Common UI testing utilities

Usage:
    from base import GraphicalTestBase
    
    class TestMyApp(GraphicalTestBase):
        def test_something(self):
            # self.screen is already set up (320x240)
            # self.screenshot_dir is configured
            label = lv.label(self.screen)
            label.set_text("Hello")
            self.wait_for_render()
            self.capture_screenshot("my_test")
"""

import unittest
import lvgl as lv
import sys
import os


class GraphicalTestBase(unittest.TestCase):
    """
    Base class for all graphical tests.
    
    Provides:
    - Automatic screen creation and cleanup
    - Screenshot directory configuration
    - Common UI testing utilities
    
    Class Attributes:
        SCREEN_WIDTH: Default screen width (320)
        SCREEN_HEIGHT: Default screen height (240)
        DEFAULT_RENDER_ITERATIONS: Default iterations for wait_for_render (5)
    
    Instance Attributes:
        screen: The LVGL screen object for the test
        screenshot_dir: Path to the screenshots directory
    """
    
    SCREEN_WIDTH = 320
    SCREEN_HEIGHT = 240
    DEFAULT_RENDER_ITERATIONS = 5
    
    @classmethod
    def setUpClass(cls):
        """
        Set up class-level fixtures.
        
        Configures the screenshot directory based on platform.
        """
        # Determine screenshot directory based on platform
        if sys.platform == "esp32":
            cls.screenshot_dir = "tests/screenshots"
        else:
            # On desktop, tests directory is in parent
            cls.screenshot_dir = "../tests/screenshots"
        
        # Ensure screenshots directory exists
        try:
            os.mkdir(cls.screenshot_dir)
        except OSError:
            pass  # Directory already exists
    
    def setUp(self):
        """
        Set up test fixtures before each test method.
        
        Creates a new screen and loads it.
        """
        # Create and load a new screen
        self.screen = lv.obj()
        self.screen.set_size(self.SCREEN_WIDTH, self.SCREEN_HEIGHT)
        lv.screen_load(self.screen)
        self.wait_for_render()
    
    def tearDown(self):
        """
        Clean up after each test method.
        
        Loads an empty screen to clean up.
        """
        # Load an empty screen to clean up
        lv.screen_load(lv.obj())
        self.wait_for_render()
    
    def wait_for_render(self, iterations=None):
        """
        Wait for LVGL to render.
        
        Args:
            iterations: Number of render iterations (default: DEFAULT_RENDER_ITERATIONS)
        """
        from mpos.ui.testing import wait_for_render
        if iterations is None:
            iterations = self.DEFAULT_RENDER_ITERATIONS
        wait_for_render(iterations)
    
    def capture_screenshot(self, name, width=None, height=None):
        """
        Capture a screenshot with standardized naming.
        
        Args:
            name: Name for the screenshot (without extension)
            width: Screenshot width (default: SCREEN_WIDTH)
            height: Screenshot height (default: SCREEN_HEIGHT)
            
        Returns:
            bytes: The screenshot buffer
        """
        from mpos.ui.testing import capture_screenshot
        
        if width is None:
            width = self.SCREEN_WIDTH
        if height is None:
            height = self.SCREEN_HEIGHT
            
        path = f"{self.screenshot_dir}/{name}.raw"
        return capture_screenshot(path, width=width, height=height)
    
    def find_label_with_text(self, text, parent=None):
        """
        Find a label containing the specified text.
        
        Args:
            text: Text to search for
            parent: Parent widget to search in (default: current screen)
            
        Returns:
            The label widget if found, None otherwise
        """
        from mpos.ui.testing import find_label_with_text
        if parent is None:
            parent = lv.screen_active()
        return find_label_with_text(parent, text)
    
    def verify_text_present(self, text, parent=None):
        """
        Verify that text is present on screen.
        
        Args:
            text: Text to search for
            parent: Parent widget to search in (default: current screen)
            
        Returns:
            bool: True if text is found
        """
        from mpos.ui.testing import verify_text_present
        if parent is None:
            parent = lv.screen_active()
        return verify_text_present(parent, text)
    
    def print_screen_labels(self, parent=None):
        """
        Print all labels on screen (for debugging).
        
        Args:
            parent: Parent widget to search in (default: current screen)
        """
        from mpos.ui.testing import print_screen_labels
        if parent is None:
            parent = lv.screen_active()
        print_screen_labels(parent)
    
    def click_button(self, text, use_send_event=True):
        """
        Click a button by its text.
        
        Args:
            text: Button text to find and click
            use_send_event: If True, use send_event (more reliable)
            
        Returns:
            bool: True if button was found and clicked
        """
        from mpos.ui.testing import click_button
        return click_button(text, use_send_event=use_send_event)
    
    def click_label(self, text, use_send_event=True):
        """
        Click a label by its text.
        
        Args:
            text: Label text to find and click
            use_send_event: If True, use send_event (more reliable)
            
        Returns:
            bool: True if label was found and clicked
        """
        from mpos.ui.testing import click_label
        return click_label(text, use_send_event=use_send_event)
    
    def simulate_click(self, x, y):
        """
        Simulate a click at specific coordinates.
        
        Note: For most UI testing, prefer click_button() or click_label()
        which are more reliable. Use this only when testing touch behavior.
        
        Args:
            x: X coordinate
            y: Y coordinate
        """
        from mpos.ui.testing import simulate_click
        simulate_click(x, y)
        self.wait_for_render()
    
    def assertTextPresent(self, text, msg=None):
        """
        Assert that text is present on screen.
        
        Args:
            text: Text to search for
            msg: Optional failure message
        """
        if msg is None:
            msg = f"Text '{text}' not found on screen"
        self.assertTrue(self.verify_text_present(text), msg)
    
    def assertTextNotPresent(self, text, msg=None):
        """
        Assert that text is NOT present on screen.
        
        Args:
            text: Text to search for
            msg: Optional failure message
        """
        if msg is None:
            msg = f"Text '{text}' should not be on screen"
        self.assertFalse(self.verify_text_present(text), msg)
