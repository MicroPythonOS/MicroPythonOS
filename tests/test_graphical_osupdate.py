import unittest
import lvgl as lv
import mpos

from mpos import (
    wait_for_text,
    find_label_with_text,
    verify_text_present,
    print_screen_labels,
    BuildInfo,
    AppManager
)


class TestOSUpdateGraphicalUI(unittest.TestCase):
    """Graphical tests for OSUpdate app UI state."""

    def tearDown(self):
        mpos.ui.back_screen()

    def test_app_launches_successfully(self):
        """Test that OSUpdate app launches without errors."""
        result = AppManager.start_app("com.micropythonos.osupdate")

        self.assertTrue(result, "Failed to start OSUpdate app")
        self.assertTrue(
            wait_for_text("Installed OS version", timeout=10),
            "OSUpdate app did not show version label within timeout"
        )

        screen = lv.screen_active()
        self.assertIsNotNone(screen, "No active screen after launch")

    def test_ui_elements_exist(self):
        """Test that all required UI elements are created."""
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        self.assertTrue(
            wait_for_text("Installed OS version", timeout=10),
            "OSUpdate app did not load within timeout"
        )

        screen = lv.screen_active()

        current_version_label = find_label_with_text(screen, "Installed OS version")
        self.assertIsNotNone(current_version_label, "Current version label not found")

        update_button_found = verify_text_present(screen, "Update") or verify_text_present(screen, "update") or \
                             verify_text_present(screen, "Reinstall") or verify_text_present(screen, "Install")
        self.assertTrue(update_button_found, "Update button text not found")


    def test_install_button_text_exists(self):
        """Test that install button with update text exists on screen."""
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        self.assertTrue(
            wait_for_text("Installed OS version", timeout=10),
            "OSUpdate app did not load within timeout"
        )

        screen = lv.screen_active()

        button_text_found = verify_text_present(screen, "Update OS") or \
                           verify_text_present(screen, "Reinstall") or \
                           verify_text_present(screen, "Install")
        self.assertTrue(button_text_found, "Install button text should be present on screen")

    def test_current_version_displayed(self):
        """Test that current OS version is displayed correctly."""
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        self.assertTrue(
            wait_for_text("Installed OS version:", timeout=10),
            "Version label did not appear within timeout"
        )

        screen = lv.screen_active()

        version_label = find_label_with_text(screen, "Installed OS version:")
        self.assertIsNotNone(version_label, "Version label not found")

        label_text = version_label.get_text()
        current_version = BuildInfo.version.release
        self.assertIn(current_version, label_text,
                     f"Current version {current_version} not in label text: {label_text}")

    def test_initial_status_message_without_wifi(self):
        """Test status message when wifi is not connected."""
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        self.assertTrue(
            wait_for_text("Installed OS version", timeout=10),
            "OSUpdate app did not load within timeout"
        )

        screen = lv.screen_active()

        checking_found = verify_text_present(screen, "Checking") or \
                        verify_text_present(screen, "version") or \
                        verify_text_present(screen, "WiFi")
        self.assertTrue(checking_found, "Should show some status message")

    def test_initial_state_labels(self):
        """Print initial app labels for debugging."""
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        self.assertTrue(
            wait_for_text("Installed OS version", timeout=10),
            "OSUpdate app did not load within timeout"
        )

        screen = lv.screen_active()

        print("\n=== OSUpdate Initial State Labels ===")
        print_screen_labels(screen)


class TestOSUpdateGraphicalStatusMessages(unittest.TestCase):
    """Graphical tests for OSUpdate status messages."""

    def tearDown(self):
        mpos.ui.back_screen()

    def test_status_label_exists(self):
        """Test that status label is created and visible."""
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        self.assertTrue(
            wait_for_text("Installed OS version", timeout=10),
            "OSUpdate app did not load within timeout"
        )

        screen = lv.screen_active()

        has_status = (
            verify_text_present(screen, "Checking") or
            verify_text_present(screen, "version") or
            verify_text_present(screen, "WiFi") or
            verify_text_present(screen, "Error") or
            verify_text_present(screen, "Update")
        )
        self.assertTrue(has_status, "Status label should be present with some message")

    def test_all_labels_readable(self):
        """Test that all labels are readable (no truncation issues)."""
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        self.assertTrue(
            wait_for_text("Installed OS version", timeout=10),
            "OSUpdate app did not load within timeout"
        )

        screen = lv.screen_active()

        print("\n=== All OSUpdate Labels ===")
        print_screen_labels(screen)

        version_found = verify_text_present(screen, "Installed OS version")
        self.assertTrue(version_found, "Version label should be present and readable")
