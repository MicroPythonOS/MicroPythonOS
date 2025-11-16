import unittest
import sys

# Mock classes for testing
class MockNetwork:
    """Mock network module for testing NetworkMonitor."""

    STA_IF = 0  # Station interface constant

    class MockWLAN:
        def __init__(self, interface):
            self.interface = interface
            self._connected = True  # Default to connected

        def isconnected(self):
            return self._connected

    def __init__(self, connected=True):
        self._connected = connected

    def WLAN(self, interface):
        wlan = self.MockWLAN(interface)
        wlan._connected = self._connected
        return wlan

    def set_connected(self, connected):
        """Helper to change connection state."""
        self._connected = connected


class MockRaw:
    """Mock raw response for streaming."""
    def __init__(self, content):
        self.content = content
        self.position = 0

    def read(self, size):
        chunk = self.content[self.position:self.position + size]
        self.position += len(chunk)
        return chunk


class MockResponse:
    """Mock HTTP response."""
    def __init__(self, status_code=200, text='', headers=None, content=b''):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.content = content
        self._closed = False

        # Mock raw attribute for streaming
        self.raw = MockRaw(content)

    def close(self):
        self._closed = True


class MockRequests:
    """Mock requests module for testing UpdateChecker and UpdateDownloader."""

    def __init__(self):
        self.last_url = None
        self.next_response = None
        self.raise_exception = None

    def get(self, url, stream=False, timeout=None, headers=None):
        self.last_url = url

        if self.raise_exception:
            raise self.raise_exception

        if self.next_response:
            return self.next_response

        # Default response
        return MockResponse()

    def set_next_response(self, status_code=200, text='', headers=None, content=b''):
        """Helper to set what the next get() should return."""
        self.next_response = MockResponse(status_code, text, headers, content)
        return self.next_response

    def set_exception(self, exception):
        """Helper to make next get() raise an exception."""
        self.raise_exception = exception


class MockJSON:
    """Mock JSON module for testing UpdateChecker."""

    def __init__(self):
        self.raise_exception = None

    def loads(self, text):
        if self.raise_exception:
            raise self.raise_exception

        # Very simple JSON parser for testing
        # In real tests, we can just use Python's json module
        import json
        return json.loads(text)

    def set_exception(self, exception):
        """Helper to make loads() raise an exception."""
        self.raise_exception = exception


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
from osupdate import NetworkMonitor, UpdateChecker, UpdateDownloader, round_up_to_multiple


class TestNetworkMonitor(unittest.TestCase):
    """Test NetworkMonitor class."""

    def test_is_connected_with_connected_network(self):
        """Test that is_connected returns True when network is connected."""
        mock_network = MockNetwork(connected=True)
        monitor = NetworkMonitor(network_module=mock_network)

        self.assertTrue(monitor.is_connected())

    def test_is_connected_with_disconnected_network(self):
        """Test that is_connected returns False when network is disconnected."""
        mock_network = MockNetwork(connected=False)
        monitor = NetworkMonitor(network_module=mock_network)

        self.assertFalse(monitor.is_connected())

    def test_is_connected_without_network_module(self):
        """Test that is_connected returns True when no network module (desktop mode)."""
        monitor = NetworkMonitor(network_module=None)

        # Should return True (assume connected) in desktop mode
        self.assertTrue(monitor.is_connected())

    def test_is_connected_with_exception(self):
        """Test that is_connected returns False when WLAN raises exception."""
        class BadNetwork:
            STA_IF = 0
            def WLAN(self, interface):
                raise Exception("WLAN error")

        monitor = NetworkMonitor(network_module=BadNetwork())

        self.assertFalse(monitor.is_connected())

    def test_network_state_change_detection(self):
        """Test detecting network state changes."""
        mock_network = MockNetwork(connected=True)
        monitor = NetworkMonitor(network_module=mock_network)

        # Initially connected
        self.assertTrue(monitor.is_connected())

        # Disconnect
        mock_network.set_connected(False)
        self.assertFalse(monitor.is_connected())

        # Reconnect
        mock_network.set_connected(True)
        self.assertTrue(monitor.is_connected())

    def test_multiple_checks_when_connected(self):
        """Test that multiple checks return consistent results."""
        mock_network = MockNetwork(connected=True)
        monitor = NetworkMonitor(network_module=mock_network)

        # Multiple checks should all return True
        for _ in range(5):
            self.assertTrue(monitor.is_connected())

    def test_wlan_with_different_interface_types(self):
        """Test that correct interface type is used."""
        class NetworkWithInterface:
            STA_IF = 0
            CALLED_WITH = None

            class MockWLAN:
                def __init__(self, interface):
                    NetworkWithInterface.CALLED_WITH = interface
                    self._connected = True

                def isconnected(self):
                    return self._connected

            def WLAN(self, interface):
                return self.MockWLAN(interface)

        network = NetworkWithInterface()
        monitor = NetworkMonitor(network_module=network)
        monitor.is_connected()

        # Should have been called with STA_IF
        self.assertEqual(NetworkWithInterface.CALLED_WITH, 0)


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
        url = self.checker.get_update_url("waveshare-esp32-s3-touch-lcd-2")

        self.assertEqual(url, "https://updates.micropythonos.com/osupdate.json")

    def test_get_update_url_other_hardware(self):
        """Test URL generation for other hardware."""
        url = self.checker.get_update_url("fri3d-2024")

        self.assertEqual(url, "https://updates.micropythonos.com/osupdate_fri3d-2024.json")

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

        result = self.checker.fetch_update_info("waveshare-esp32-s3-touch-lcd-2")

        self.assertEqual(result["version"], "0.3.3")
        self.assertEqual(result["download_url"], "https://example.com/update.bin")
        self.assertEqual(result["changelog"], "Bug fixes")

    def test_fetch_update_info_http_error(self):
        """Test fetch with HTTP error response."""
        self.mock_requests.set_next_response(status_code=404)

        # MicroPython doesn't have ConnectionError, so catch generic Exception
        try:
            self.checker.fetch_update_info("waveshare-esp32-s3-touch-lcd-2")
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
            self.checker.fetch_update_info("waveshare-esp32-s3-touch-lcd-2")

        self.assertIn("Invalid JSON", str(cm.exception))

    def test_fetch_update_info_missing_version_field(self):
        """Test fetch with missing version field."""
        import json
        self.mock_requests.set_next_response(
            status_code=200,
            text=json.dumps({"download_url": "http://example.com", "changelog": "test"})
        )

        with self.assertRaises(ValueError) as cm:
            self.checker.fetch_update_info("waveshare-esp32-s3-touch-lcd-2")

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
            self.checker.fetch_update_info("waveshare-esp32-s3-touch-lcd-2")

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
            self.checker.fetch_update_info("waveshare-esp32-s3-touch-lcd-2")
            self.fail("Should have raised an exception for timeout")
        except Exception as e:
            self.assertIn("Timeout", str(e))

    def test_fetch_update_info_connection_refused(self):
        """Test fetch with connection refused."""
        self.mock_requests.set_exception(Exception("Connection refused"))

        try:
            self.checker.fetch_update_info("waveshare-esp32-s3-touch-lcd-2")
            self.fail("Should have raised an exception")
        except Exception as e:
            self.assertIn("Connection refused", str(e))

    def test_fetch_update_info_empty_response(self):
        """Test fetch with empty response."""
        self.mock_requests.set_next_response(status_code=200, text='')

        try:
            self.checker.fetch_update_info("waveshare-esp32-s3-touch-lcd-2")
            self.fail("Should have raised an exception for empty response")
        except Exception:
            pass  # Expected to fail

    def test_fetch_update_info_server_error_500(self):
        """Test fetch with 500 server error."""
        self.mock_requests.set_next_response(status_code=500)

        try:
            self.checker.fetch_update_info("waveshare-esp32-s3-touch-lcd-2")
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
            self.checker.fetch_update_info("waveshare-esp32-s3-touch-lcd-2")
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
    """Test UpdateDownloader class."""

    def setUp(self):
        self.mock_requests = MockRequests()
        self.mock_partition = MockPartition
        self.downloader = UpdateDownloader(
            requests_module=self.mock_requests,
            partition_module=self.mock_partition
        )

    def test_download_and_install_success(self):
        """Test successful download and install."""
        # Create 8KB of test data (2 blocks of 4096 bytes)
        test_data = b'A' * 8192
        self.mock_requests.set_next_response(
            status_code=200,
            headers={'Content-Length': '8192'},
            content=test_data
        )

        progress_calls = []
        def progress_cb(percent):
            progress_calls.append(percent)

        result = self.downloader.download_and_install(
            "http://example.com/update.bin",
            progress_callback=progress_cb
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['bytes_written'], 8192)
        self.assertEqual(result['total_size'], 8192)
        self.assertIsNone(result['error'])
        # MicroPython unittest doesn't have assertGreater
        self.assertTrue(len(progress_calls) > 0, "Should have progress callbacks")

    def test_download_and_install_cancelled(self):
        """Test cancelled download."""
        test_data = b'A' * 8192
        self.mock_requests.set_next_response(
            status_code=200,
            headers={'Content-Length': '8192'},
            content=test_data
        )

        call_count = [0]
        def should_continue():
            call_count[0] += 1
            return call_count[0] < 2  # Cancel after first chunk

        result = self.downloader.download_and_install(
            "http://example.com/update.bin",
            should_continue_callback=should_continue
        )

        self.assertFalse(result['success'])
        self.assertIn("cancelled", result['error'].lower())

    def test_download_with_padding(self):
        """Test that last chunk is properly padded."""
        # 5000 bytes - not a multiple of 4096
        test_data = b'B' * 5000
        self.mock_requests.set_next_response(
            status_code=200,
            headers={'Content-Length': '5000'},
            content=test_data
        )

        result = self.downloader.download_and_install(
            "http://example.com/update.bin"
        )

        self.assertTrue(result['success'])
        # Should be rounded up to 8192 (2 * 4096)
        self.assertEqual(result['total_size'], 8192)

    def test_download_with_network_error(self):
        """Test download with network error during transfer."""
        self.mock_requests.set_exception(Exception("Network error"))

        result = self.downloader.download_and_install(
            "http://example.com/update.bin"
        )

        self.assertFalse(result['success'])
        self.assertIsNotNone(result['error'])
        self.assertIn("Network error", result['error'])

    def test_download_with_zero_content_length(self):
        """Test download with missing or zero Content-Length."""
        test_data = b'C' * 1000
        self.mock_requests.set_next_response(
            status_code=200,
            headers={},  # No Content-Length header
            content=test_data
        )

        result = self.downloader.download_and_install(
            "http://example.com/update.bin"
        )

        # Should still work, just with unknown total size initially
        self.assertTrue(result['success'])

    def test_download_progress_callback_called(self):
        """Test that progress callback is called during download."""
        test_data = b'D' * 8192
        self.mock_requests.set_next_response(
            status_code=200,
            headers={'Content-Length': '8192'},
            content=test_data
        )

        progress_values = []
        def track_progress(percent):
            progress_values.append(percent)

        result = self.downloader.download_and_install(
            "http://example.com/update.bin",
            progress_callback=track_progress
        )

        self.assertTrue(result['success'])
        # Should have at least 2 progress updates (for 2 chunks of 4096)
        self.assertTrue(len(progress_values) >= 2)
        # Last progress should be 100%
        self.assertEqual(progress_values[-1], 100.0)

    def test_download_small_file(self):
        """Test downloading a file smaller than one chunk."""
        test_data = b'E' * 100  # Only 100 bytes
        self.mock_requests.set_next_response(
            status_code=200,
            headers={'Content-Length': '100'},
            content=test_data
        )

        result = self.downloader.download_and_install(
            "http://example.com/update.bin"
        )

        self.assertTrue(result['success'])
        # Should be padded to 4096
        self.assertEqual(result['total_size'], 4096)
        self.assertEqual(result['bytes_written'], 4096)

    def test_download_exact_chunk_multiple(self):
        """Test downloading exactly 2 chunks (no padding needed)."""
        test_data = b'F' * 8192  # Exactly 2 * 4096
        self.mock_requests.set_next_response(
            status_code=200,
            headers={'Content-Length': '8192'},
            content=test_data
        )

        result = self.downloader.download_and_install(
            "http://example.com/update.bin"
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['total_size'], 8192)
        self.assertEqual(result['bytes_written'], 8192)


