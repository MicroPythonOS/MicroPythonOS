"""
Unit tests for DownloadManager utility functions.

Tests the network error detection and resume position helpers.
"""

import unittest
import os
import sys

# Handle both CPython and MicroPython path handling
try:
    # CPython has os.path
    from os.path import join, dirname
except ImportError:
    # MicroPython doesn't have os.path, use string concatenation
    def join(*parts):
        return '/'.join(parts)
    def dirname(path):
        parts = path.split('/')
        return '/'.join(parts[:-1]) if len(parts) > 1 else '.'

# Add parent directory to path for imports
sys.path.insert(0, join(dirname(__file__), '..', 'internal_filesystem', 'lib'))

# Import functions directly from the module file to avoid mpos.__init__ dependencies
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "download_manager",
        join(dirname(__file__), '..', 'internal_filesystem', 'lib', 'mpos', 'net', 'download_manager.py')
    )
    download_manager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(download_manager)
except (ImportError, AttributeError):
    # MicroPython doesn't have importlib.util, import directly
    sys.path.insert(0, join(dirname(__file__), '..', 'internal_filesystem', 'lib', 'mpos', 'net'))
    import download_manager

is_network_error = download_manager.is_network_error
get_resume_position = download_manager.get_resume_position


class TestIsNetworkError(unittest.TestCase):
    """Test network error detection utility."""

    def test_detects_timeout_error_code(self):
        """Should detect OSError with -110 (ETIMEDOUT) as network error."""
        error = OSError(-110, "Connection timed out")
        self.assertTrue(is_network_error(error))

    def test_detects_connection_aborted_error_code(self):
        """Should detect OSError with -113 (ECONNABORTED) as network error."""
        error = OSError(-113, "Connection aborted")
        self.assertTrue(is_network_error(error))

    def test_detects_connection_reset_error_code(self):
        """Should detect OSError with -104 (ECONNRESET) as network error."""
        error = OSError(-104, "Connection reset by peer")
        self.assertTrue(is_network_error(error))

    def test_detects_host_unreachable_error_code(self):
        """Should detect OSError with -118 (EHOSTUNREACH) as network error."""
        error = OSError(-118, "No route to host")
        self.assertTrue(is_network_error(error))

    def test_detects_dns_error_code(self):
        """Should detect OSError with -202 (DNS/connection error) as network error."""
        error = OSError(-202, "DNS lookup failed")
        self.assertTrue(is_network_error(error))

    def test_detects_connection_reset_message(self):
        """Should detect 'connection reset' in error message."""
        error = Exception("Connection reset by peer")
        self.assertTrue(is_network_error(error))

    def test_detects_connection_aborted_message(self):
        """Should detect 'connection aborted' in error message."""
        error = Exception("Connection aborted")
        self.assertTrue(is_network_error(error))

    def test_detects_broken_pipe_message(self):
        """Should detect 'broken pipe' in error message."""
        error = Exception("Broken pipe")
        self.assertTrue(is_network_error(error))

    def test_detects_network_unreachable_message(self):
        """Should detect 'network unreachable' in error message."""
        error = Exception("Network unreachable")
        self.assertTrue(is_network_error(error))

    def test_detects_failed_to_download_chunk_message(self):
        """Should detect 'failed to download chunk' message from download_manager."""
        error = OSError(-110, "Failed to download chunk after retries")
        self.assertTrue(is_network_error(error))

    def test_rejects_value_error(self):
        """Should not detect ValueError as network error."""
        error = ValueError("Invalid value")
        self.assertFalse(is_network_error(error))

    def test_rejects_http_404_error(self):
        """Should not detect HTTP 404 as network error."""
        error = RuntimeError("HTTP 404")
        self.assertFalse(is_network_error(error))

    def test_rejects_file_not_found_error(self):
        """Should not detect ENOENT (-2) as network error."""
        error = OSError(-2, "No such file or directory")
        self.assertFalse(is_network_error(error))

    def test_rejects_permission_error(self):
        """Should not detect permission errors as network error."""
        error = OSError(-13, "Permission denied")
        self.assertFalse(is_network_error(error))

    def test_case_insensitive_detection(self):
        """Should detect network errors regardless of case."""
        error1 = Exception("CONNECTION RESET")
        error2 = Exception("connection reset")
        error3 = Exception("Connection Reset")
        self.assertTrue(is_network_error(error1))
        self.assertTrue(is_network_error(error2))
        self.assertTrue(is_network_error(error3))


class TestGetResumePosition(unittest.TestCase):
    """Test resume position utility."""

    def setUp(self):
        """Create test directory."""
        self.test_dir = "tmp/test_download_manager"
        # Handle both CPython and MicroPython
        try:
            os.makedirs(self.test_dir, exist_ok=True)
        except (AttributeError, TypeError):
            # MicroPython doesn't have makedirs or exist_ok parameter
            try:
                os.mkdir(self.test_dir)
            except OSError:
                pass  # Directory already exists

    def tearDown(self):
        """Clean up test files."""
        # Handle both CPython and MicroPython
        try:
            import shutil
            if os.path.exists(self.test_dir):
                shutil.rmtree(self.test_dir)
        except (ImportError, AttributeError):
            # MicroPython doesn't have shutil, manually remove files
            try:
                import os as os_module
                for f in os_module.listdir(self.test_dir):
                    os_module.remove(join(self.test_dir, f))
                os_module.rmdir(self.test_dir)
            except (OSError, AttributeError):
                pass  # Ignore errors during cleanup

    def test_returns_zero_for_nonexistent_file(self):
        """Should return 0 for files that don't exist."""
        nonexistent = join(self.test_dir, "nonexistent.bin")
        self.assertEqual(get_resume_position(nonexistent), 0)

    def test_returns_file_size_for_existing_file(self):
        """Should return file size for existing files."""
        test_file = join(self.test_dir, "test.bin")
        test_data = b"x" * 1024
        with open(test_file, "wb") as f:
            f.write(test_data)
        
        self.assertEqual(get_resume_position(test_file), 1024)

    def test_returns_zero_for_empty_file(self):
        """Should return 0 for empty files."""
        test_file = join(self.test_dir, "empty.bin")
        with open(test_file, "wb") as f:
            pass  # Create empty file
        
        self.assertEqual(get_resume_position(test_file), 0)

    def test_returns_correct_size_for_large_file(self):
        """Should return correct size for larger files."""
        test_file = join(self.test_dir, "large.bin")
        test_data = b"x" * (1024 * 1024)  # 1 MB (reduced from 10 MB to avoid memory issues)
        with open(test_file, "wb") as f:
            f.write(test_data)
        
        self.assertEqual(get_resume_position(test_file), 1024 * 1024)

    def test_returns_size_after_partial_write(self):
        """Should return current size after partial write."""
        test_file = join(self.test_dir, "partial.bin")
        
        # Write 1KB
        with open(test_file, "wb") as f:
            f.write(b"x" * 1024)
        self.assertEqual(get_resume_position(test_file), 1024)
        
        # Append another 1KB
        with open(test_file, "ab") as f:
            f.write(b"y" * 1024)
        self.assertEqual(get_resume_position(test_file), 2048)
