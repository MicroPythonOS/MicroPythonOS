import unittest
import sys
import os

class TestSysPathRestore(unittest.TestCase):
    """Test that sys.path is properly restored after execute_script"""

    def test_syspath_restored_after_execute_script(self):
        """Test that sys.path is restored to original state after script execution"""
        # Import here to ensure we're in the right context
        import mpos.apps

        # Capture original sys.path
        original_path = sys.path[:]
        original_length = len(sys.path)

        # Create a test directory path that would be added
        test_cwd = "apps/com.test.app/assets/"

        # Verify the test path is not already in sys.path
        self.assertFalse(test_cwd in original_path,
                        f"Test path {test_cwd} should not be in sys.path initially")

        # Create a simple test script
        test_script = '''
import sys
# Just a simple script that does nothing
x = 42
'''

        # Call execute_script with cwd parameter
        # Note: This will fail because there's no Activity to start,
        # but that's fine - we're testing the sys.path restoration
        result = mpos.apps.execute_script(
            test_script,
            is_file=False,
            cwd=test_cwd,
            classname="NonExistentClass"
        )

        # After execution, sys.path should be restored
        current_path = sys.path
        current_length = len(sys.path)

        # Verify sys.path has been restored to original
        self.assertEqual(current_length, original_length,
                        f"sys.path length should be restored. Original: {original_length}, Current: {current_length}")

        # Verify the test directory is not in sys.path anymore
        self.assertFalse(test_cwd in current_path,
                        f"Test path {test_cwd} should not be in sys.path after execution. sys.path={current_path}")

        # Verify sys.path matches original
        self.assertEqual(current_path, original_path,
                        f"sys.path should match original.\nOriginal: {original_path}\nCurrent:  {current_path}")

    def test_syspath_not_affected_when_no_cwd(self):
        """Test that sys.path is unchanged when cwd is None"""
        import mpos.apps

        # Capture original sys.path
        original_path = sys.path[:]

        test_script = '''
x = 42
'''

        # Call without cwd parameter
        result = mpos.apps.execute_script(
            test_script,
            is_file=False,
            cwd=None,
            classname="NonExistentClass"
        )

        # sys.path should be unchanged
        self.assertEqual(sys.path, original_path,
                        "sys.path should be unchanged when cwd is None")
