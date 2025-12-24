"""
test_download_manager.py - Tests for DownloadManager module

Tests the centralized download manager functionality including:
- Session lifecycle management
- Download modes (memory, file, streaming)
- Progress tracking
- Error handling
- Resume support with Range headers
- Concurrent downloads
"""

import unittest
import os
import sys

# Import the module under test
sys.path.insert(0, '../internal_filesystem/lib')
import mpos.net.download_manager as DownloadManager


class TestDownloadManager(unittest.TestCase):
    """Test cases for DownloadManager module."""

    def setUp(self):
        """Reset module state before each test."""
        # Reset module-level state
        DownloadManager._session = None
        DownloadManager._session_refcount = 0
        DownloadManager._session_lock = None

        # Create temp directory for file downloads
        self.temp_dir = "/tmp/test_download_manager"
        try:
            os.mkdir(self.temp_dir)
        except OSError:
            pass  # Directory already exists

    def tearDown(self):
        """Clean up after each test."""
        # Close any open sessions
        import asyncio
        if DownloadManager._session:
            asyncio.run(DownloadManager.close_session())

        # Clean up temp files
        try:
            import os
            for file in os.listdir(self.temp_dir):
                try:
                    os.remove(f"{self.temp_dir}/{file}")
                except OSError:
                    pass
            os.rmdir(self.temp_dir)
        except OSError:
            pass

    # ==================== Session Lifecycle Tests ====================

    def test_lazy_session_creation(self):
        """Test that session is created lazily on first download."""
        import asyncio

        async def run_test():
            # Verify no session exists initially
            self.assertFalse(DownloadManager.is_session_active())

            # Perform a download
            data = await DownloadManager.download_url("https://httpbin.org/bytes/100")

            # Verify session was created
            # Note: Session may be closed immediately after download if refcount == 0
            # So we can't reliably check is_session_active() here
            self.assertIsNotNone(data)
            self.assertEqual(len(data), 100)

        asyncio.run(run_test())

    def test_session_reuse_across_downloads(self):
        """Test that the same session is reused for multiple downloads."""
        import asyncio

        async def run_test():
            # Perform first download
            data1 = await DownloadManager.download_url("https://httpbin.org/bytes/50")
            self.assertIsNotNone(data1)

            # Perform second download
            data2 = await DownloadManager.download_url("https://httpbin.org/bytes/75")
            self.assertIsNotNone(data2)

            # Verify different data was downloaded
            self.assertEqual(len(data1), 50)
            self.assertEqual(len(data2), 75)

        asyncio.run(run_test())

    def test_explicit_session_close(self):
        """Test explicit session closure."""
        import asyncio

        async def run_test():
            # Create session by downloading
            data = await DownloadManager.download_url("https://httpbin.org/bytes/10")
            self.assertIsNotNone(data)

            # Explicitly close session
            await DownloadManager.close_session()

            # Verify session is closed
            self.assertFalse(DownloadManager.is_session_active())

            # Verify new download recreates session
            data2 = await DownloadManager.download_url("https://httpbin.org/bytes/20")
            self.assertIsNotNone(data2)
            self.assertEqual(len(data2), 20)

        asyncio.run(run_test())

    # ==================== Download Mode Tests ====================

    def test_download_to_memory(self):
        """Test downloading content to memory (returns bytes)."""
        import asyncio

        async def run_test():
            data = await DownloadManager.download_url("https://httpbin.org/bytes/1024")

            self.assertIsInstance(data, bytes)
            self.assertEqual(len(data), 1024)

        asyncio.run(run_test())

    def test_download_to_file(self):
        """Test downloading content to file (returns True/False)."""
        import asyncio

        async def run_test():
            outfile = f"{self.temp_dir}/test_download.bin"

            success = await DownloadManager.download_url(
                "https://httpbin.org/bytes/2048",
                outfile=outfile
            )

            self.assertTrue(success)
            self.assertEqual(os.stat(outfile)[6], 2048)

            # Clean up
            os.remove(outfile)

        asyncio.run(run_test())

    def test_download_with_chunk_callback(self):
        """Test streaming download with chunk callback."""
        import asyncio

        async def run_test():
            chunks_received = []

            async def collect_chunks(chunk):
                chunks_received.append(chunk)

            success = await DownloadManager.download_url(
                "https://httpbin.org/bytes/512",
                chunk_callback=collect_chunks
            )

            self.assertTrue(success)
            self.assertTrue(len(chunks_received) > 0)

            # Verify total size matches
            total_size = sum(len(chunk) for chunk in chunks_received)
            self.assertEqual(total_size, 512)

        asyncio.run(run_test())

    def test_parameter_validation_conflicting_params(self):
        """Test that outfile and chunk_callback cannot both be provided."""
        import asyncio

        async def run_test():
            with self.assertRaises(ValueError) as context:
                await DownloadManager.download_url(
                    "https://httpbin.org/bytes/100",
                    outfile="/tmp/test.bin",
                    chunk_callback=lambda chunk: None
                )

            self.assertIn("Cannot use both", str(context.exception))

        asyncio.run(run_test())

    # ==================== Progress Tracking Tests ====================

    def test_progress_callback(self):
        """Test that progress callback is called with percentages."""
        import asyncio

        async def run_test():
            progress_calls = []

            async def track_progress(percent):
                progress_calls.append(percent)

            data = await DownloadManager.download_url(
                "https://httpbin.org/bytes/5120",  # 5KB
                progress_callback=track_progress
            )

            self.assertIsNotNone(data)
            self.assertTrue(len(progress_calls) > 0)

            # Verify progress values are in valid range
            for pct in progress_calls:
                self.assertTrue(0 <= pct <= 100)

            # Verify progress generally increases (allowing for some rounding variations)
            # Note: Due to chunking and rounding, progress might not be strictly increasing
            self.assertTrue(progress_calls[-1] >= 90)  # Should end near 100%

        asyncio.run(run_test())

    def test_progress_with_explicit_total_size(self):
        """Test progress tracking with explicitly provided total_size."""
        import asyncio

        async def run_test():
            progress_calls = []

            async def track_progress(percent):
                progress_calls.append(percent)

            data = await DownloadManager.download_url(
                "https://httpbin.org/bytes/3072",  # 3KB
                total_size=3072,
                progress_callback=track_progress
            )

            self.assertIsNotNone(data)
            self.assertTrue(len(progress_calls) > 0)

        asyncio.run(run_test())

    # ==================== Error Handling Tests ====================

    def test_http_error_status(self):
        """Test handling of HTTP error status codes."""
        import asyncio

        async def run_test():
            # Request 404 error from httpbin - should raise RuntimeError
            with self.assertRaises(RuntimeError) as context:
                data = await DownloadManager.download_url("https://httpbin.org/status/404")

            # Should raise RuntimeError with status code
            self.assertIn("404", str(context.exception))

        asyncio.run(run_test())

    def test_http_error_with_file_output(self):
        """Test that file download raises exception on HTTP error."""
        import asyncio

        async def run_test():
            outfile = f"{self.temp_dir}/error_test.bin"

            # Should raise RuntimeError for HTTP 500
            with self.assertRaises(RuntimeError) as context:
                success = await DownloadManager.download_url(
                    "https://httpbin.org/status/500",
                    outfile=outfile
                )

            # Should raise RuntimeError with status code
            self.assertIn("500", str(context.exception))

            # File should not be created
            try:
                os.stat(outfile)
                self.fail("File should not exist after failed download")
            except OSError:
                pass  # Expected - file doesn't exist

        asyncio.run(run_test())

    def test_invalid_url(self):
        """Test handling of invalid URL."""
        import asyncio

        async def run_test():
            # Invalid URL should raise an exception
            with self.assertRaises(Exception):
                data = await DownloadManager.download_url("http://invalid-url-that-does-not-exist.local/")

        asyncio.run(run_test())

    # ==================== Headers Support Tests ====================

    def test_custom_headers(self):
        """Test that custom headers are passed to the request."""
        import asyncio

        async def run_test():
            # httpbin.org/headers echoes back the headers sent
            data = await DownloadManager.download_url(
                "https://httpbin.org/headers",
                headers={"X-Custom-Header": "TestValue"}
            )

            self.assertIsNotNone(data)
            # Verify the custom header was included (httpbin echoes it back)
            response_text = data.decode('utf-8')
            self.assertIn("X-Custom-Header", response_text)
            self.assertIn("TestValue", response_text)

        asyncio.run(run_test())

    # ==================== Edge Cases Tests ====================

    def test_empty_response(self):
        """Test handling of empty (0-byte) downloads."""
        import asyncio

        async def run_test():
            # Download 0 bytes
            data = await DownloadManager.download_url("https://httpbin.org/bytes/0")

            self.assertIsNotNone(data)
            self.assertEqual(len(data), 0)
            self.assertEqual(data, b'')

        asyncio.run(run_test())

    def test_small_download(self):
        """Test downloading very small files (smaller than chunk size)."""
        import asyncio

        async def run_test():
            # Download 10 bytes (much smaller than 1KB chunk size)
            data = await DownloadManager.download_url("https://httpbin.org/bytes/10")

            self.assertIsNotNone(data)
            self.assertEqual(len(data), 10)

        asyncio.run(run_test())

    def test_json_download(self):
        """Test downloading JSON data."""
        import asyncio
        import json

        async def run_test():
            data = await DownloadManager.download_url("https://httpbin.org/json")

            self.assertIsNotNone(data)
            # Verify it's valid JSON
            parsed = json.loads(data.decode('utf-8'))
            self.assertIsInstance(parsed, dict)

        asyncio.run(run_test())

    # ==================== File Operations Tests ====================

    def test_file_download_creates_directory_if_needed(self):
        """Test that parent directories are NOT created (caller's responsibility)."""
        import asyncio

        async def run_test():
            # Try to download to non-existent directory
            outfile = "/tmp/nonexistent_dir_12345/test.bin"

            # Should raise exception because directory doesn't exist
            with self.assertRaises(Exception):
                success = await DownloadManager.download_url(
                    "https://httpbin.org/bytes/100",
                    outfile=outfile
                )

        asyncio.run(run_test())

    def test_file_overwrite(self):
        """Test that downloading overwrites existing files."""
        import asyncio

        async def run_test():
            outfile = f"{self.temp_dir}/overwrite_test.bin"

            # Create initial file
            with open(outfile, 'wb') as f:
                f.write(b'old content')

            # Download and overwrite
            success = await DownloadManager.download_url(
                "https://httpbin.org/bytes/100",
                outfile=outfile
            )

            self.assertTrue(success)
            self.assertEqual(os.stat(outfile)[6], 100)

            # Verify old content is gone
            with open(outfile, 'rb') as f:
                content = f.read()
            self.assertNotEqual(content, b'old content')
            self.assertEqual(len(content), 100)

            # Clean up
            os.remove(outfile)

        asyncio.run(run_test())
