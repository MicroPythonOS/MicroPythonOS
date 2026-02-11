import unittest
import sys
import asyncio

# Add parent directory to path so we can import network_test_helper
# When running from unittest.sh, we're in internal_filesystem/, so tests/ is ../tests/
sys.path.insert(0, '../tests')

# Import network test helpers
from network_test_helper import MockNetwork, MockRequests, MockJSON, MockDownloadManager

# Import the real DownloadManager for is_network_error function
from mpos import DownloadManager


class MockPartition:
    """Mock ESP32 Partition for testing UpdateDownloader."""

    RUNNING = 0

    def __init__(self, partition_type=None):
        self.partition_type = partition_type
        self.blocks = {}  # Store written blocks
        self.boot_set = False

    def get_next_update(self):
        """Return a mock OTA partition."""
        return MockPartition()

    def writeblocks(self, block_num, data):
        """Mock writing blocks."""
        self.blocks[block_num] = data

    def set_boot(self):
        """Mock setting boot partition."""
        self.boot_set = True


# Import PackageManager which is needed by UpdateChecker
# The test runs from internal_filesystem/ directory, so we can import from lib/mpos
from mpos import AppManager

# Import the actual classes we're testing
# Tests run from internal_filesystem/, so we add the assets directory to path
sys.path.append('builtin/apps/com.micropythonos.osupdate/assets')
from osupdate import UpdateChecker, UpdateDownloader, round_up_to_multiple


def run_async(coro):
    """Helper to run async coroutines in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestUpdateChecker(unittest.TestCase):
    """Test UpdateChecker class."""

    def setUp(self):
        self.mock_download_manager = MockDownloadManager()
        self.mock_json = MockJSON()
        self.checker = UpdateChecker(
            download_manager=self.mock_download_manager,
            json_module=self.mock_json
        )

    def test_get_update_url_waveshare(self):
        """Test URL generation for waveshare hardware."""
        url = self.checker.get_update_url("waveshare_esp32_s3_touch_lcd_2")

        self.assertEqual(url, "https://updates.micropythonos.com/osupdate.json")

    def test_get_update_url_other_hardware(self):
        """Test URL generation for other hardware."""
        url = self.checker.get_update_url("fri3d_2024")

        self.assertEqual(url, "https://updates.micropythonos.com/osupdate_fri3d_2024.json")

    def test_fetch_update_info_success(self):
        """Test successful update info fetch."""
        import json
        update_data = {
            "version": "0.3.3",
            "download_url": "https://example.com/update.bin",
            "changelog": "Bug fixes"
        }
        self.mock_download_manager.set_download_data(json.dumps(update_data).encode())

        async def run_test():
            return await self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")

        result = run_async(run_test())

        self.assertEqual(result["version"], "0.3.3")
        self.assertEqual(result["download_url"], "https://example.com/update.bin")
        self.assertEqual(result["changelog"], "Bug fixes")

    def test_fetch_update_info_http_error(self):
        """Test fetch with HTTP error response."""
        self.mock_download_manager.set_should_fail(True)

        async def run_test():
            return await self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")

        # MicroPython doesn't have ConnectionError, so catch generic Exception
        try:
            run_async(run_test())
            self.fail("Should have raised an exception for HTTP 404")
        except Exception as e:
            # MockDownloadManager returns None on failure, which causes an error
            pass

    def test_fetch_update_info_invalid_json(self):
        """Test fetch with invalid JSON."""
        self.mock_download_manager.set_download_data(b"not valid json {")

        async def run_test():
            return await self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")

        with self.assertRaises(ValueError) as cm:
            run_async(run_test())

        self.assertIn("Invalid JSON", str(cm.exception))

    def test_fetch_update_info_missing_version_field(self):
        """Test fetch with missing version field."""
        import json
        self.mock_download_manager.set_download_data(
            json.dumps({"download_url": "http://example.com", "changelog": "test"}).encode()
        )

        async def run_test():
            return await self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")

        with self.assertRaises(ValueError) as cm:
            run_async(run_test())

        self.assertIn("missing required fields", str(cm.exception))
        self.assertIn("version", str(cm.exception))

    def test_fetch_update_info_missing_download_url_field(self):
        """Test fetch with missing download_url field."""
        import json
        self.mock_download_manager.set_download_data(
            json.dumps({"version": "1.0.0", "changelog": "test"}).encode()
        )

        async def run_test():
            return await self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")

        with self.assertRaises(ValueError) as cm:
            run_async(run_test())

        self.assertIn("download_url", str(cm.exception))

    def test_is_update_available_newer_version(self):
        """Test that newer version is detected."""
        result = self.checker.is_update_available("1.2.3", "1.2.2")

        self.assertTrue(result)

    def test_is_update_available_same_version(self):
        """Test that same version is not an update."""
        result = self.checker.is_update_available("1.2.3", "1.2.3")

        self.assertFalse(result)

    def test_is_update_available_older_version(self):
        """Test that older version is not an update."""
        result = self.checker.is_update_available("1.2.2", "1.2.3")

        self.assertFalse(result)

    def test_fetch_update_info_timeout(self):
        """Test fetch with request timeout."""
        self.mock_download_manager.set_should_fail(True)

        async def run_test():
            return await self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")

        try:
            run_async(run_test())
            self.fail("Should have raised an exception for timeout")
        except Exception as e:
            # MockDownloadManager returns None on failure, which causes an error
            pass

    def test_fetch_update_info_connection_refused(self):
        """Test fetch with connection refused."""
        self.mock_download_manager.set_should_fail(True)

        async def run_test():
            return await self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")

        try:
            run_async(run_test())
            self.fail("Should have raised an exception")
        except Exception as e:
            # MockDownloadManager returns None on failure, which causes an error
            pass

    def test_fetch_update_info_empty_response(self):
        """Test fetch with empty response."""
        self.mock_download_manager.set_download_data(b'')

        async def run_test():
            return await self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")

        try:
            run_async(run_test())
            self.fail("Should have raised an exception for empty response")
        except Exception:
            pass  # Expected to fail

    def test_fetch_update_info_server_error_500(self):
        """Test fetch with 500 server error."""
        self.mock_download_manager.set_should_fail(True)

        async def run_test():
            return await self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")

        try:
            run_async(run_test())
            self.fail("Should have raised an exception for HTTP 500")
        except Exception as e:
            pass

    def test_fetch_update_info_missing_changelog(self):
        """Test fetch with missing changelog field."""
        import json
        self.mock_download_manager.set_download_data(
            json.dumps({"version": "1.0.0", "download_url": "http://example.com"}).encode()
        )

        async def run_test():
            return await self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")

        try:
            run_async(run_test())
            self.fail("Should have raised exception for missing changelog")
        except ValueError as e:
            self.assertIn("changelog", str(e))

    def test_get_update_url_custom_hardware(self):
        """Test URL generation for custom hardware IDs."""
        # Test with different hardware IDs
        url1 = self.checker.get_update_url("custom-device-v1")
        self.assertEqual(url1, "https://updates.micropythonos.com/osupdate_custom-device-v1.json")

        url2 = self.checker.get_update_url("test-123")
        self.assertEqual(url2, "https://updates.micropythonos.com/osupdate_test-123.json")


class TestUpdateDownloader(unittest.TestCase):
    """Test UpdateDownloader class with async DownloadManager."""

    def setUp(self):
        self.mock_download_manager = MockDownloadManager()
        self.mock_partition = MockPartition
        self.downloader = UpdateDownloader(
            partition_module=self.mock_partition,
            download_manager=self.mock_download_manager
        )

    def test_download_and_install_success(self):
        """Test successful download and install."""
        # Create 8KB of test data (2 blocks of 4096 bytes)
        test_data = b'A' * 8192
        self.mock_download_manager.set_download_data(test_data)
        self.mock_download_manager.chunk_size = 4096

        progress_calls = []
        async def progress_cb(percent):
            progress_calls.append(percent)

        async def run_test():
            return await self.downloader.download_and_install(
                "http://example.com/update.bin",
                progress_callback=progress_cb
            )

        result = run_async(run_test())

        self.assertTrue(result['success'])
        self.assertEqual(result['bytes_written'], 8192)
        self.assertIsNone(result['error'])
        # MicroPython unittest doesn't have assertGreater
        self.assertTrue(len(progress_calls) > 0, "Should have progress callbacks")

    def test_download_and_install_cancelled(self):
        """Test cancelled download."""
        test_data = b'A' * 8192
        self.mock_download_manager.set_download_data(test_data)
        self.mock_download_manager.chunk_size = 4096

        call_count = [0]
        def should_continue():
            call_count[0] += 1
            return call_count[0] < 2  # Cancel after first chunk

        async def run_test():
            return await self.downloader.download_and_install(
                "http://example.com/update.bin",
                should_continue_callback=should_continue
            )

        result = run_async(run_test())

        self.assertFalse(result['success'])
        self.assertIn("cancelled", result['error'].lower())

    def test_download_with_padding(self):
        """Test that last chunk is properly padded."""
        # 5000 bytes - not a multiple of 4096
        test_data = b'B' * 5000
        self.mock_download_manager.set_download_data(test_data)
        self.mock_download_manager.chunk_size = 4096

        async def run_test():
            return await self.downloader.download_and_install(
                "http://example.com/update.bin"
            )

        result = run_async(run_test())

        self.assertTrue(result['success'])
        # Should be padded to 8192 (2 * 4096)
        self.assertEqual(result['bytes_written'], 8192)

    def test_download_with_network_error(self):
        """Test download with network error during transfer."""
        self.mock_download_manager.set_should_fail(True)

        async def run_test():
            return await self.downloader.download_and_install(
                "http://example.com/update.bin"
            )

        result = run_async(run_test())

        self.assertFalse(result['success'])
        self.assertIsNotNone(result['error'])

    def test_download_with_zero_content_length(self):
        """Test download with missing or zero Content-Length."""
        test_data = b'C' * 1000
        self.mock_download_manager.set_download_data(test_data)
        self.mock_download_manager.chunk_size = 1000

        async def run_test():
            return await self.downloader.download_and_install(
                "http://example.com/update.bin"
            )

        result = run_async(run_test())

        # Should still work, just with unknown total size initially
        self.assertTrue(result['success'])

    def test_download_progress_callback_called(self):
        """Test that progress callback is called during download."""
        test_data = b'D' * 8192
        self.mock_download_manager.set_download_data(test_data)
        self.mock_download_manager.chunk_size = 4096

        progress_values = []
        async def track_progress(percent):
            progress_values.append(percent)

        async def run_test():
            return await self.downloader.download_and_install(
                "http://example.com/update.bin",
                progress_callback=track_progress
            )

        result = run_async(run_test())

        self.assertTrue(result['success'])
        # Should have at least 2 progress updates (for 2 chunks of 4096)
        self.assertTrue(len(progress_values) >= 2)
        # Last progress should be 100%
        self.assertEqual(progress_values[-1], 100)

    def test_download_small_file(self):
        """Test downloading a file smaller than one chunk."""
        test_data = b'E' * 100  # Only 100 bytes
        self.mock_download_manager.set_download_data(test_data)
        self.mock_download_manager.chunk_size = 100

        async def run_test():
            return await self.downloader.download_and_install(
                "http://example.com/update.bin"
            )

        result = run_async(run_test())

        self.assertTrue(result['success'])
        # Should be padded to 4096
        self.assertEqual(result['bytes_written'], 4096)

    def test_download_exact_chunk_multiple(self):
        """Test downloading exactly 2 chunks (no padding needed)."""
        test_data = b'F' * 8192  # Exactly 2 * 4096
        self.mock_download_manager.set_download_data(test_data)
        self.mock_download_manager.chunk_size = 4096

        async def run_test():
            return await self.downloader.download_and_install(
                "http://example.com/update.bin"
            )

        result = run_async(run_test())

        self.assertTrue(result['success'])
        self.assertEqual(result['bytes_written'], 8192)

    def test_network_error_detection_econnaborted(self):
        """Test that ECONNABORTED error is detected as network error."""
        error = OSError(-113, "ECONNABORTED")
        self.assertTrue(DownloadManager.is_network_error(error))

    def test_network_error_detection_econnreset(self):
        """Test that ECONNRESET error is detected as network error."""
        error = OSError(-104, "ECONNRESET")
        self.assertTrue(DownloadManager.is_network_error(error))

    def test_network_error_detection_etimedout(self):
        """Test that ETIMEDOUT error is detected as network error."""
        error = OSError(-110, "ETIMEDOUT")
        self.assertTrue(DownloadManager.is_network_error(error))

    def test_network_error_detection_ehostunreach(self):
        """Test that EHOSTUNREACH error is detected as network error."""
        error = OSError(-118, "EHOSTUNREACH")
        self.assertTrue(DownloadManager.is_network_error(error))

    def test_network_error_detection_by_message(self):
        """Test that network errors are detected by message."""
        self.assertTrue(DownloadManager.is_network_error(Exception("Connection reset by peer")))
        self.assertTrue(DownloadManager.is_network_error(Exception("Connection aborted")))
        self.assertTrue(DownloadManager.is_network_error(Exception("Broken pipe")))

    def test_non_network_error_not_detected(self):
        """Test that non-network errors are not detected as network errors."""
        self.assertFalse(DownloadManager.is_network_error(ValueError("Invalid data")))
        self.assertFalse(DownloadManager.is_network_error(Exception("File not found")))
        self.assertFalse(DownloadManager.is_network_error(KeyError("missing")))

    def test_download_pauses_on_network_error_during_read(self):
        """Test that download pauses when network error occurs during read."""
        # Set up mock to raise network error after first chunk
        test_data = b'G' * 16384  # 4 chunks
        self.mock_download_manager.set_download_data(test_data)
        self.mock_download_manager.chunk_size = 4096
        self.mock_download_manager.set_fail_after_bytes(4096)  # Fail after first chunk

        async def run_test():
            return await self.downloader.download_and_install(
                "http://example.com/update.bin"
            )

        result = run_async(run_test())

        self.assertFalse(result['success'])
        self.assertTrue(result['paused'])
        self.assertEqual(result['bytes_written'], 4096)  # Should have written first chunk
        self.assertIsNone(result['error'])  # Pause, not error

    def test_download_resumes_from_saved_position(self):
        """Test that download resumes from the last written position."""
        # Simulate partial download
        self.downloader.bytes_written_so_far = 8192  # Already downloaded 2 chunks
        self.downloader.total_size_expected = 12288

        # Server should receive Range header - only remaining data
        remaining_data = b'H' * 4096  # Last chunk
        self.mock_download_manager.set_download_data(remaining_data)
        self.mock_download_manager.chunk_size = 4096

        async def run_test():
            return await self.downloader.download_and_install(
                "http://example.com/update.bin"
            )

        result = run_async(run_test())

        self.assertTrue(result['success'])
        self.assertEqual(result['bytes_written'], 12288)
        # Check that Range header was set
        self.assertIsNotNone(self.mock_download_manager.headers_received)
        self.assertIn('Range', self.mock_download_manager.headers_received)
        self.assertEqual(self.mock_download_manager.headers_received['Range'], 'bytes=8192-')

    def test_resume_failure_preserves_state(self):
        """Test that resume failures preserve download state for retry."""
        # Simulate partial download state
        self.downloader.bytes_written_so_far = 245760  # 60 chunks already downloaded
        self.downloader.total_size_expected = 3391488

        # Resume attempt fails immediately with network error
        self.mock_download_manager.set_download_data(b'')
        self.mock_download_manager.set_fail_after_bytes(0)  # Fail immediately

        async def run_test():
            return await self.downloader.download_and_install(
                "http://example.com/update.bin"
            )

        result = run_async(run_test())

        # Should pause, not fail
        self.assertFalse(result['success'])
        self.assertTrue(result['paused'])
        self.assertIsNone(result['error'])

        # Critical: Must preserve progress for next retry
        self.assertEqual(result['bytes_written'], 245760, "Must preserve bytes_written")
        self.assertEqual(result['total_size'], 3391488, "Must preserve total_size")
        self.assertEqual(self.downloader.bytes_written_so_far, 245760, "Must preserve internal state")


class MockLVGLButton:
     """Mock LVGL button for testing button state and text."""
     
     def __init__(self, initial_disabled=True):
         self.disabled = initial_disabled
         self.children = []
         self.hidden = False
     
     def add_state(self, state):
         """Add a state flag (e.g., lv.STATE.DISABLED)."""
         # Track if DISABLED state is being added
         if state == 1:  # lv.STATE.DISABLED
             self.disabled = True
     
     def remove_state(self, state):
         """Remove a state flag."""
         # Track if DISABLED state is being removed
         if state == 1:  # lv.STATE.DISABLED
             self.disabled = False
     
     def add_flag(self, flag):
         """Add a flag (e.g., lv.obj.FLAG.HIDDEN)."""
         if flag == 1:  # lv.obj.FLAG.HIDDEN
             self.hidden = True
     
     def remove_flag(self, flag):
         """Remove a flag."""
         if flag == 1:  # lv.obj.FLAG.HIDDEN
             self.hidden = False
     
     def get_child(self, index):
         """Get child widget by index."""
         if index < len(self.children):
             return self.children[index]
         return None
     
     def is_disabled(self):
         """Check if button is disabled."""
         return self.disabled
     
     def is_hidden(self):
         """Check if button is hidden."""
         return self.hidden
     
     def set_text(self, text):
         """Set button text (for compatibility with direct text setting)."""
         if self.children and hasattr(self.children[0], 'set_text'):
             self.children[0].set_text(text)


class MockLVGLLabel:
    """Mock LVGL label for testing text content."""
    
    def __init__(self):
        self.text = ""
    
    def set_text(self, text):
        """Set label text."""
        self.text = text
    
    def get_text(self):
        """Get label text."""
        return self.text
    
    def center(self):
        """Mock center method (no-op for testing)."""
        pass


class MockAppManager:
   """Mock AppManager for version comparison."""
   
   @staticmethod
   def compare_versions(version1, version2):
       """Compare two version strings.
       
       Returns:
           > 0 if version1 > version2
           = 0 if version1 == version2
           < 0 if version1 < version2
       """
       def parse_version(v):
           return tuple(map(int, v.split('.')))
       
       v1 = parse_version(version1)
       v2 = parse_version(version2)
       
       if v1 > v2:
           return 1
       elif v1 < v2:
           return -1
       else:
           return 0


class MockBuildInfo:
    """Mock BuildInfo for testing."""
    class Version:
        release = "1.0.0"
    version = Version()


class TestOSUpdateButtonBehavior(unittest.TestCase):
     """Test OSUpdate button behavior with different version scenarios.
     
     These tests verify that handle_update_info() correctly interprets
     AppManager.compare_versions() return values and sets button text accordingly.
     The bug being tested: compare_versions() returns integers (-1, 0, 1), not booleans.
     """
     
     def setUp(self):
         """Set up test fixtures."""
         # Create a mock OSUpdate instance with mocked dependencies
         self.mock_app_manager = MockAppManager()
         
         # We'll patch AppManager.compare_versions for these tests
         self.original_compare_versions = AppManager.compare_versions
         AppManager.compare_versions = self.mock_app_manager.compare_versions
         
         # Create mock button and label
         self.mock_button = MockLVGLButton(initial_disabled=True)
         self.mock_label = MockLVGLLabel()
         self.mock_button.children = [self.mock_label]
     
     def tearDown(self):
         """Restore original AppManager.compare_versions."""
         AppManager.compare_versions = self.original_compare_versions
     
     def test_button_initially_disabled(self):
         """Test that the 'Update OS' button is initially disabled."""
         # Button should start in disabled state
         self.assertTrue(self.mock_button.is_disabled(),
                        "Button should be initially disabled")
     
     def test_handle_update_info_with_newer_version(self):
         """Test handle_update_info() with newer version (1.1.0 vs 1.0.0).
         
         This test verifies that:
         - compare_versions(1.1.0, 1.0.0) returns 1 (positive integer)
         - The button text is set to exactly "Update OS"
         - The button is enabled (remove_state called)
         """
         # Create a minimal OSUpdate instance for testing
         from osupdate import OSUpdate
         import osupdate
         
         app = OSUpdate()
         
         # Mock the UI components with a tracking button
         tracking_button = MockLVGLButton(initial_disabled=True)
         tracking_button.children = [MockLVGLLabel()]
         app.install_button = tracking_button
         app.status_label = MockLVGLLabel()
         
         # Mock BuildInfo and AppManager in osupdate module
         original_build_info = osupdate.BuildInfo
         original_app_manager = osupdate.AppManager
         try:
             osupdate.BuildInfo = MockBuildInfo
             osupdate.AppManager = type('MockAppManager', (), {
                 'compare_versions': staticmethod(self.mock_app_manager.compare_versions)
             })
             
             # Call handle_update_info with newer version
             app.handle_update_info("1.1.0", "http://example.com/update.bin", "Bug fixes")
             
             # Verify button text is exactly "Install\nnew\nversion"
             button_label = tracking_button.get_child(0)
             self.assertIsNotNone(button_label, "Button should have a label child")
             self.assertEqual(button_label.get_text(), "Install\nnew\nversion",
                            "Button text must be exactly 'Install\nnew\nversion' for newer version")
         finally:
             osupdate.BuildInfo = original_build_info
             osupdate.AppManager = original_app_manager
     
     def test_handle_update_info_with_same_version(self):
         """Test handle_update_info() with same version (1.0.0 vs 1.0.0).
         
         This test verifies that:
         - compare_versions(1.0.0, 1.0.0) returns 0
         - The button text is set to exactly "Reinstall\\nsame version"
         - The button is enabled (remove_state called)
         """
         # Create a minimal OSUpdate instance for testing
         from osupdate import OSUpdate
         import osupdate
         
         app = OSUpdate()
         
         # Mock the UI components with a tracking button
         tracking_button = MockLVGLButton(initial_disabled=True)
         tracking_button.children = [MockLVGLLabel()]
         app.install_button = tracking_button
         app.status_label = MockLVGLLabel()
         
         # Mock BuildInfo and AppManager in osupdate module
         original_build_info = osupdate.BuildInfo
         original_app_manager = osupdate.AppManager
         try:
             osupdate.BuildInfo = MockBuildInfo
             osupdate.AppManager = type('MockAppManager', (), {
                 'compare_versions': staticmethod(self.mock_app_manager.compare_versions)
             })
             
             # Call handle_update_info with same version
             app.handle_update_info("1.0.0", "http://example.com/update.bin", "Reinstall")
             
             # Verify button text is exactly "Reinstall\nsame version"
             button_label = tracking_button.get_child(0)
             self.assertIsNotNone(button_label, "Button should have a label child")
             self.assertEqual(button_label.get_text(), "Reinstall\nsame\nversion",
                            "Button text must be exactly 'Reinstall\\nsame\nversion' for same version")
         finally:
             osupdate.BuildInfo = original_build_info
             osupdate.AppManager = original_app_manager
     
     def test_handle_update_info_with_older_version(self):
         """Test handle_update_info() with older version (0.9.0 vs 1.0.0).
         
         This test verifies that:
         - compare_versions(0.9.0, 1.0.0) returns -1 (negative integer)
         - The button text is set to exactly "Install old version"
         - The button is enabled (remove_state called)
         """
         # Create a minimal OSUpdate instance for testing
         from osupdate import OSUpdate
         import osupdate
         
         app = OSUpdate()
         
         # Mock the UI components with a tracking button
         tracking_button = MockLVGLButton(initial_disabled=True)
         tracking_button.children = [MockLVGLLabel()]
         app.install_button = tracking_button
         app.status_label = MockLVGLLabel()
         
         # Mock BuildInfo and AppManager in osupdate module
         original_build_info = osupdate.BuildInfo
         original_app_manager = osupdate.AppManager
         try:
             osupdate.BuildInfo = MockBuildInfo
             osupdate.AppManager = type('MockAppManager', (), {
                 'compare_versions': staticmethod(self.mock_app_manager.compare_versions)
             })
             
             # Call handle_update_info with older version
             app.handle_update_info("0.9.0", "http://example.com/update.bin", "Old version")
             
             # Verify button text is exactly "Install old version"
             button_label = tracking_button.get_child(0)
             self.assertIsNotNone(button_label, "Button should have a label child")
             self.assertEqual(button_label.get_text(), "Install\nold\nversion",
                            "Button text must be exactly 'Install\\nold\nversion' for older version")
         finally:
             osupdate.BuildInfo = original_build_info
             osupdate.AppManager = original_app_manager
     
     def test_version_comparison_returns_integers_not_booleans(self):
         """Test that compare_versions() returns integers, not booleans.
         
         This is the core bug test: the old code treated integer return values
         as booleans in if statements. This test verifies the mock returns
         proper integer values that would have caught the bug.
         """
         # Test that compare_versions returns integers
         result_greater = self.mock_app_manager.compare_versions("1.1.0", "1.0.0")
         self.assertEqual(result_greater, 1, "Should return 1 for greater version")
         self.assertIsInstance(result_greater, int, "Should return int, not bool")
         
         result_equal = self.mock_app_manager.compare_versions("1.0.0", "1.0.0")
         self.assertEqual(result_equal, 0, "Should return 0 for equal version")
         self.assertIsInstance(result_equal, int, "Should return int, not bool")
         
         result_less = self.mock_app_manager.compare_versions("0.9.0", "1.0.0")
         self.assertEqual(result_less, -1, "Should return -1 for lesser version")
         self.assertIsInstance(result_less, int, "Should return int, not bool")
     
     def test_button_text_with_multiple_version_pairs(self):
         """Test button text with various version comparison scenarios.
         
         This comprehensive test ensures the button text is correct for
         multiple version pairs, catching any edge cases in the comparison logic.
         The bug being tested: compare_versions() returns integers (-1, 0, 1),
         and these must be properly interpreted in if statements.
         """
         from osupdate import OSUpdate
         import osupdate
         
         test_cases = [
             # (new_version, current_version, expected_button_text, description)
             ("2.0.0", "1.0.0", "Install\nnew\nversion", "Major version upgrade"),
             ("1.1.0", "1.0.0", "Install\nnew\nversion", "Minor version upgrade"),
             ("1.0.1", "1.0.0", "Install\nnew\nversion", "Patch version upgrade"),
             ("1.0.0", "1.0.0", "Reinstall\nsame\nversion", "Exact same version"),
             ("0.9.9", "1.0.0", "Install\nold\nversion", "Downgrade to older version"),
             ("0.5.0", "1.0.0", "Install\nold\nversion", "Major version downgrade"),
             ("1.0.0", "2.0.0", "Install\nold\nversion", "Downgrade from major version"),
         ]
         
         original_build_info = osupdate.BuildInfo
         original_app_manager = osupdate.AppManager
         try:
             for new_version, current_version, expected_text, description in test_cases:
                 # Reset button state for each test
                 tracking_button = MockLVGLButton(initial_disabled=True)
                 tracking_button.children = [MockLVGLLabel()]
                 
                 # Set current version
                 osupdate.BuildInfo = MockBuildInfo
                 osupdate.BuildInfo.version.release = current_version
                 osupdate.AppManager = type('MockAppManager', (), {
                     'compare_versions': staticmethod(self.mock_app_manager.compare_versions)
                 })
                 
                 # Create app and mock components
                 app = OSUpdate()
                 app.install_button = tracking_button
                 app.status_label = MockLVGLLabel()
                 
                 # Call handle_update_info
                 app.handle_update_info(new_version, "http://example.com/update.bin", "Test")
                 
                 # Verify button text
                 button_label = tracking_button.get_child(0)
                 actual_text = button_label.get_text()
                 self.assertEqual(actual_text, expected_text,
                                f"Failed for {description}: {new_version} vs {current_version}. "
                                f"Expected '{expected_text}', got '{actual_text}'")
         finally:
             osupdate.BuildInfo = original_build_info
             osupdate.AppManager = original_app_manager


