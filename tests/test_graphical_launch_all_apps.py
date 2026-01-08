"""
Test that launches all installed apps to check for startup errors.

This test discovers all apps in apps/ and builtin/apps/ directories,
launches each one, and checks for exceptions during startup.
"""

import unittest
import os
import sys
import time

# This is a graphical test - needs boot and main to run first
# Add tests directory to path for helpers

from mpos.ui.testing import wait_for_render
import mpos.apps
import mpos.ui
from mpos.content.package_manager import PackageManager


class TestLaunchAllApps(unittest.TestCase):
    """Test launching all installed apps."""

    def setUp(self):
        """Set up test fixtures."""
        self.apps_to_test = []
        self.app_errors = {}

        # Discover all apps
        self._discover_apps()

    def _discover_apps(self):
        """Discover all installed apps."""
        # Use PackageManager to get all apps
        all_packages = PackageManager.get_app_list()

        for package in all_packages:
            # Get the main activity for each app
            if package.activities:
                # Use first activity as the main one (activities are dicts)
                main_activity = package.activities[0]
                self.apps_to_test.append({
                    'package_name': package.fullname,
                    'activity_name': main_activity.get('classname', 'MainActivity'),
                    'label': package.name
                })

    def test_launch_all_apps(self):
        """Launch each app and check for errors."""
        print(f"\n{'='*60}")
        print(f"Testing {len(self.apps_to_test)} apps for startup errors")
        print(f"{'='*60}\n")

        failed_apps = []
        passed_apps = []

        for i, app_info in enumerate(self.apps_to_test, 1):
            package_name = app_info['package_name']
            activity_name = app_info['activity_name']
            label = app_info['label']

            print(f"\n[{i}/{len(self.apps_to_test)}] Testing: {label} ({package_name})")

            error_found = False
            error_message = ""

            try:
                # Launch the app by package name
                result = mpos.apps.start_app(package_name)

                # Wait for UI to render
                wait_for_render(iterations=5)

                # Check if start_app returned False (indicates error during execution)
                if result is False:
                    error_found = True
                    error_message = "App failed to start (execute_script returned False)"
                    print(f"  ❌ FAILED - App failed to start")
                    print(f"     {error_message}")
                    failed_apps.append({
                        'info': app_info,
                        'error': error_message
                    })
                else:
                    # If we got here without error, the app loaded successfully
                    print(f"  ✓ PASSED - App loaded successfully")
                    passed_apps.append(app_info)

                # Navigate back to exit the app
                mpos.ui.back_screen()
                wait_for_render(iterations=3)

            except Exception as e:
                error_found = True
                error_message = f"{type(e).__name__}: {str(e)}"
                print(f"  ❌ FAILED - Exception during launch")
                print(f"     {error_message}")
                failed_apps.append({
                    'info': app_info,
                    'error': error_message
                })

        # Print summary
        print(f"\n{'='*60}")
        print(f"Test Summary")
        print(f"{'='*60}")
        print(f"Total apps tested: {len(self.apps_to_test)}")
        print(f"Passed: {len(passed_apps)}")
        print(f"Failed: {len(failed_apps)}")
        print(f"{'='*60}\n")

        if failed_apps:
            print("Failed apps:")
            for fail in failed_apps:
                print(f"  - {fail['info']['label']} ({fail['info']['package_name']})")
                print(f"    Error: {fail['error']}")
            print()

        # Separate errortest failures from other failures
        errortest_failures = [
            fail for fail in failed_apps
            if 'errortest' in fail['info']['package_name'].lower()
        ]

        # On macOS, musicplayer is known to fail due to @micropython.viper issue
        # and camera app fails due to no camera hardware
        is_macos = sys.platform == 'darwin'
        musicplayer_failures = [
            fail for fail in failed_apps
            if fail['info']['package_name'] == 'com.micropythonos.musicplayer' and is_macos
        ]
        
        camera_failures = [
            fail for fail in failed_apps
            if fail['info']['package_name'] == 'com.micropythonos.camera' and is_macos
        ]

        other_failures = [
            fail for fail in failed_apps
            if 'errortest' not in fail['info']['package_name'].lower() and
               not (fail['info']['package_name'] == 'com.micropythonos.musicplayer' and is_macos) and
               not (fail['info']['package_name'] == 'com.micropythonos.camera' and is_macos)
        ]

        # Check if errortest app exists
        all_app_names = [app['package_name'] for app in self.apps_to_test]
        has_errortest = any('errortest' in name.lower() for name in all_app_names)

        # Verify errortest app fails if it exists
        if has_errortest:
            self.assertTrue(len(errortest_failures) > 0,
                "Failed to detect error in com.micropythonos.errortest app")
            print("✓ Successfully detected the intentional error in errortest app")

        # Report on musicplayer failures on macOS (known issue)
        if musicplayer_failures:
            print("⚠ Skipped musicplayer failure on macOS (known @micropython.viper issue)")
        
        # Report on camera failures on macOS (no camera hardware)
        if camera_failures:
            print("⚠ Skipped camera app failure on macOS (no camera hardware available)")

        # Fail the test if any non-errortest apps have errors
        if other_failures:
            print(f"\n❌ FAIL: {len(other_failures)} non-errortest app(s) have errors:")
            for fail in other_failures:
                print(f"  - {fail['info']['label']} ({fail['info']['package_name']})")
                print(f"    Error: {fail['error']}")
            self.fail(f"{len(other_failures)} app(s) failed to launch (excluding errortest)")
        else:
            print("✓ All non-errortest apps launched successfully")


class TestLaunchSpecificApps(unittest.TestCase):
    """Test specific apps individually for more detailed error reporting."""

    def _launch_and_check_app(self, package_name, expected_error=False):
        """
        Launch an app and check for errors.

        Args:
            package_name: Full package name (e.g., 'com.micropythonos.camera')
            expected_error: Whether this app is expected to have errors

        Returns:
            tuple: (success, error_message)
        """
        error_found = False
        error_message = ""

        try:
            # Launch the app by package name
            result = mpos.apps.start_app(package_name)
            wait_for_render(iterations=5)

            # Check if start_app returned False (indicates error)
            if result is False:
                error_found = True
                error_message = "App failed to start (execute_script returned False)"

            # Navigate back
            mpos.ui.back_screen()
            wait_for_render(iterations=3)

        except Exception as e:
            error_found = True
            error_message = f"{type(e).__name__}: {str(e)}"

        if expected_error:
            # For apps expected to have errors
            return (error_found, error_message)
        else:
            # For apps that should work
            return (not error_found, error_message)

    def test_errortest_app_has_error(self):
        """Test that the errortest app properly reports an error."""
        success, error_msg = self._launch_and_check_app(
            'com.micropythonos.errortest',
            expected_error=True
        )

        if success:
            print(f"\n✓ Successfully detected error in errortest app:")
            print(f"  {error_msg}")
        else:
            print(f"\n❌ Failed to detect error in errortest app")

        self.assertTrue(success,
            "The errortest app should have an error but none was detected")

    def test_launcher_app_loads(self):
        """Test that the launcher app loads without errors."""
        success, error_msg = self._launch_and_check_app(
            'com.micropythonos.launcher',
            expected_error=False
        )

        if not success:
            print(f"\n❌ Launcher app has errors: {error_msg}")

        self.assertTrue(success,
            f"Launcher app should load without errors: {error_msg}")

    def test_about_app_loads(self):
        """Test that the About app loads without errors."""
        success, error_msg = self._launch_and_check_app(
            'com.micropythonos.about',
            expected_error=False
        )

        if not success:
            print(f"\n❌ About app has errors: {error_msg}")

        self.assertTrue(success,
            f"About app should load without errors: {error_msg}")


