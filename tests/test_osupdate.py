import unittest
import sys
import asyncio

# Add parent directory to path so we can import network_test_helper
# When running from unittest.sh, we're in internal_filesystem/, so tests/ is ../tests/
sys.path.insert(0, '../tests')

# Import network test helpers
from network_test_helper import MockNetwork, MockRequests, MockJSON, MockDownloadManager


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
from mpos import PackageManager

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
        self.mock_requests = MockRequests()
        self.mock_json = MockJSON()
        self.checker = UpdateChecker(
            requests_module=self.mock_requests,
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
        self.mock_requests.set_next_response(
            status_code=200,
            text=json.dumps(update_data)
        )

        result = self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")

        self.assertEqual(result["version"], "0.3.3")
        self.assertEqual(result["download_url"], "https://example.com/update.bin")
        self.assertEqual(result["changelog"], "Bug fixes")

    def test_fetch_update_info_http_error(self):
        """Test fetch with HTTP error response."""
        self.mock_requests.set_next_response(status_code=404)

        # MicroPython doesn't have ConnectionError, so catch generic Exception
        try:
            self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")
            self.fail("Should have raised an exception for HTTP 404")
        except Exception as e:
            # Should be a ConnectionError, but we accept any exception with HTTP status
            self.assertIn("404", str(e))

    def test_fetch_update_info_invalid_json(self):
        """Test fetch with invalid JSON."""
        self.mock_requests.set_next_response(
            status_code=200,
            text="not valid json {"
        )

        with self.assertRaises(ValueError) as cm:
            self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")

        self.assertIn("Invalid JSON", str(cm.exception))

    def test_fetch_update_info_missing_version_field(self):
        """Test fetch with missing version field."""
        import json
        self.mock_requests.set_next_response(
            status_code=200,
            text=json.dumps({"download_url": "http://example.com", "changelog": "test"})
        )

        with self.assertRaises(ValueError) as cm:
            self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")

        self.assertIn("missing required fields", str(cm.exception))
        self.assertIn("version", str(cm.exception))

    def test_fetch_update_info_missing_download_url_field(self):
        """Test fetch with missing download_url field."""
        import json
        self.mock_requests.set_next_response(
            status_code=200,
            text=json.dumps({"version": "1.0.0", "changelog": "test"})
        )

        with self.assertRaises(ValueError) as cm:
            self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")

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
        self.mock_requests.set_exception(Exception("Timeout"))

        try:
            self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")
            self.fail("Should have raised an exception for timeout")
        except Exception as e:
            self.assertIn("Timeout", str(e))

    def test_fetch_update_info_connection_refused(self):
        """Test fetch with connection refused."""
        self.mock_requests.set_exception(Exception("Connection refused"))

        try:
            self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")
            self.fail("Should have raised an exception")
        except Exception as e:
            self.assertIn("Connection refused", str(e))

    def test_fetch_update_info_empty_response(self):
        """Test fetch with empty response."""
        self.mock_requests.set_next_response(status_code=200, text='')

        try:
            self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")
            self.fail("Should have raised an exception for empty response")
        except Exception:
            pass  # Expected to fail

    def test_fetch_update_info_server_error_500(self):
        """Test fetch with 500 server error."""
        self.mock_requests.set_next_response(status_code=500)

        try:
            self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")
            self.fail("Should have raised an exception for HTTP 500")
        except Exception as e:
            self.assertIn("500", str(e))

    def test_fetch_update_info_missing_changelog(self):
        """Test fetch with missing changelog field."""
        import json
        self.mock_requests.set_next_response(
            status_code=200,
            text=json.dumps({"version": "1.0.0", "download_url": "http://example.com"})
        )

        try:
            self.checker.fetch_update_info("waveshare_esp32_s3_touch_lcd_2")
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
        self.assertTrue(self.downloader._is_network_error(error))

    def test_network_error_detection_econnreset(self):
        """Test that ECONNRESET error is detected as network error."""
        error = OSError(-104, "ECONNRESET")
        self.assertTrue(self.downloader._is_network_error(error))

    def test_network_error_detection_etimedout(self):
        """Test that ETIMEDOUT error is detected as network error."""
        error = OSError(-110, "ETIMEDOUT")
        self.assertTrue(self.downloader._is_network_error(error))

    def test_network_error_detection_ehostunreach(self):
        """Test that EHOSTUNREACH error is detected as network error."""
        error = OSError(-118, "EHOSTUNREACH")
        self.assertTrue(self.downloader._is_network_error(error))

    def test_network_error_detection_by_message(self):
        """Test that network errors are detected by message."""
        self.assertTrue(self.downloader._is_network_error(Exception("Connection reset by peer")))
        self.assertTrue(self.downloader._is_network_error(Exception("Connection aborted")))
        self.assertTrue(self.downloader._is_network_error(Exception("Broken pipe")))

    def test_non_network_error_not_detected(self):
        """Test that non-network errors are not detected as network errors."""
        self.assertFalse(self.downloader._is_network_error(ValueError("Invalid data")))
        self.assertFalse(self.downloader._is_network_error(Exception("File not found")))
        self.assertFalse(self.downloader._is_network_error(KeyError("missing")))

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


