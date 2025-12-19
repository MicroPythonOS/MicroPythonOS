"""
Base class for keyboard tests in MicroPythonOS.

This class extends GraphicalTestBase with keyboard-specific functionality:
- Keyboard and textarea creation
- Keyboard button clicking
- Textarea text assertions

Usage:
    from base import KeyboardTestBase
    
    class TestMyKeyboard(KeyboardTestBase):
        def test_typing(self):
            keyboard, textarea = self.create_keyboard_scene()
            self.click_keyboard_button("h")
            self.click_keyboard_button("i")
            self.assertTextareaText("hi")
"""

import lvgl as lv
from .graphical_test_base import GraphicalTestBase


class KeyboardTestBase(GraphicalTestBase):
    """
    Base class for keyboard tests.
    
    Extends GraphicalTestBase with keyboard-specific functionality.
    
    Instance Attributes:
        keyboard: The MposKeyboard instance (after create_keyboard_scene)
        textarea: The textarea widget (after create_keyboard_scene)
    """
    
    # Increase render iterations for keyboard tests
    DEFAULT_RENDER_ITERATIONS = 10
    
    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        self.keyboard = None
        self.textarea = None
    
    def create_keyboard_scene(self, initial_text="", textarea_width=200, textarea_height=30):
        """
        Create a standard keyboard test scene with textarea and keyboard.
        
        Args:
            initial_text: Initial text in the textarea
            textarea_width: Width of the textarea
            textarea_height: Height of the textarea
            
        Returns:
            tuple: (keyboard, textarea)
        """
        from mpos.ui.keyboard import MposKeyboard
        
        # Create textarea
        self.textarea = lv.textarea(self.screen)
        self.textarea.set_size(textarea_width, textarea_height)
        self.textarea.set_one_line(True)
        self.textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        self.textarea.set_text(initial_text)
        self.wait_for_render()
        
        # Create keyboard and connect to textarea
        self.keyboard = MposKeyboard(self.screen)
        self.keyboard.set_textarea(self.textarea)
        self.keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.wait_for_render()
        
        return self.keyboard, self.textarea
    
    def click_keyboard_button(self, button_text):
        """
        Click a keyboard button by its text.
        
        This uses the reliable click_keyboard_button helper which
        directly manipulates the textarea for MposKeyboard instances.
        
        Args:
            button_text: The text of the button to click (e.g., "q", "a", "Enter")
            
        Returns:
            bool: True if button was clicked successfully
        """
        from mpos.ui.testing import click_keyboard_button
        
        if self.keyboard is None:
            raise RuntimeError("No keyboard created. Call create_keyboard_scene() first.")
        
        return click_keyboard_button(self.keyboard, button_text)
    
    def get_textarea_text(self):
        """
        Get the current text in the textarea.
        
        Returns:
            str: The textarea text
        """
        if self.textarea is None:
            raise RuntimeError("No textarea created. Call create_keyboard_scene() first.")
        return self.textarea.get_text()
    
    def set_textarea_text(self, text):
        """
        Set the textarea text.
        
        Args:
            text: The text to set
        """
        if self.textarea is None:
            raise RuntimeError("No textarea created. Call create_keyboard_scene() first.")
        self.textarea.set_text(text)
        self.wait_for_render()
    
    def clear_textarea(self):
        """Clear the textarea."""
        self.set_textarea_text("")
    
    def type_text(self, text):
        """
        Type a string by clicking each character on the keyboard.
        
        Args:
            text: The text to type
            
        Returns:
            bool: True if all characters were typed successfully
        """
        for char in text:
            if not self.click_keyboard_button(char):
                return False
        return True
    
    def assertTextareaText(self, expected, msg=None):
        """
        Assert that the textarea contains the expected text.
        
        Args:
            expected: Expected text
            msg: Optional failure message
        """
        actual = self.get_textarea_text()
        if msg is None:
            msg = f"Textarea text mismatch. Expected '{expected}', got '{actual}'"
        self.assertEqual(actual, expected, msg)
    
    def assertTextareaEmpty(self, msg=None):
        """
        Assert that the textarea is empty.
        
        Args:
            msg: Optional failure message
        """
        if msg is None:
            msg = f"Textarea should be empty, but contains '{self.get_textarea_text()}'"
        self.assertEqual(self.get_textarea_text(), "", msg)
    
    def assertTextareaContains(self, substring, msg=None):
        """
        Assert that the textarea contains a substring.
        
        Args:
            substring: Substring to search for
            msg: Optional failure message
        """
        actual = self.get_textarea_text()
        if msg is None:
            msg = f"Textarea should contain '{substring}', but has '{actual}'"
        self.assertIn(substring, actual, msg)
    
    def get_keyboard_button_text(self, index):
        """
        Get the text of a keyboard button by index.
        
        Args:
            index: Button index
            
        Returns:
            str: Button text, or None if not found
        """
        if self.keyboard is None:
            raise RuntimeError("No keyboard created. Call create_keyboard_scene() first.")
        
        try:
            return self.keyboard.get_button_text(index)
        except:
            return None
    
    def find_keyboard_button_index(self, button_text):
        """
        Find the index of a keyboard button by its text.
        
        Args:
            button_text: Text to search for
            
        Returns:
            int: Button index, or None if not found
        """
        for i in range(100):  # Check first 100 indices
            text = self.get_keyboard_button_text(i)
            if text is None:
                break
            if text == button_text:
                return i
        return None
    
    def get_all_keyboard_buttons(self):
        """
        Get all keyboard buttons as a list of (index, text) tuples.
        
        Returns:
            list: List of (index, text) tuples
        """
        buttons = []
        for i in range(100):
            text = self.get_keyboard_button_text(i)
            if text is None:
                break
            if text:  # Skip empty strings
                buttons.append((i, text))
        return buttons
