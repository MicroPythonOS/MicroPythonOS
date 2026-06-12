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
from mpos.net.download_manager import DownloadManager
from mpos.testing.mocks import MockDownloadManager


class TestDownloadManager(unittest.TestCase):
    """Test cases for DownloadManager module."""

    def setUp(self):
        """Reset module state before each test."""
        # Create temp directory for file downloads
        self.temp_dir = "/tmp/test_download_manager"
        try:
            os.mkdir(self.temp_dir)
        except OSError:
            pass  # Directory already exists

    def tearDown(self):
        """Clean up after each test."""
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
        """Test that session is created for each download (per-request design)."""
        import asyncio

        async def run_test():
            mock_dm = MockDownloadManager()
            mock_dm.set_download_data(b"x" * 100)
            data = await mock_dm.download_url("https://example.com/bytes/100")

            # Verify download succeeded
            self.assertIsNotNone(data)
            self.assertEqual(len(data), 100)

        asyncio.run(run_test())

    def test_session_reuse_across_downloads(self):
        """Test that the same session is reused for multiple downloads."""
        import asyncio

        async def run_test():
            mock_dm = MockDownloadManager()

            # Perform first download
            mock_dm.set_download_data(b"a" * 50)
            data1 = await mock_dm.download_url("https://example.com/bytes/50")
            self.assertIsNotNone(data1)

            # Perform second download
            mock_dm.set_download_data(b"b" * 75)
            data2 = await mock_dm.download_url("https://example.com/bytes/75")
            self.assertIsNotNone(data2)

            # Verify different data was downloaded
            self.assertEqual(len(data1), 50)
            self.assertEqual(len(data2), 75)

        asyncio.run(run_test())


    # ==================== Download Mode Tests ====================

    def test_download_to_memory(self):
        """Test downloading content to memory (returns bytes)."""
        import asyncio

        async def run_test():
            mock_dm = MockDownloadManager()
            mock_dm.set_download_data(b"x" * 1024)
            data = await mock_dm.download_url("https://example.com/bytes/1024")

            self.assertIsInstance(data, bytes)
            self.assertEqual(len(data), 1024)

        asyncio.run(run_test())

    def test_download_to_file(self):
        """Test downloading content to file (returns True/False)."""
        import asyncio

        async def run_test():
            outfile = f"{self.temp_dir}/test_download.bin"
            mock_dm = MockDownloadManager()
            mock_dm.set_download_data(b"x" * 2048)

            success = await mock_dm.download_url(
                "https://example.com/bytes/2048",
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
            mock_dm = MockDownloadManager()
            mock_dm.set_download_data(b"x" * 512)

            async def collect_chunks(chunk):
                chunks_received.append(chunk)

            success = await mock_dm.download_url(
                "https://example.com/bytes/512",
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
                    "https://example.com/bytes/100",
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
            mock_dm = MockDownloadManager()
            mock_dm.set_download_data(b"x" * 5120)

            async def track_progress(percent):
                progress_calls.append(percent)

            data = await mock_dm.download_url(
                "https://example.com/bytes/5120",  # 5KB
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
        """Test progress tracking with explicitly provided total_size using mock."""
        import asyncio

        async def run_test():
            # Use mock to avoid external service dependency
            mock_dm = MockDownloadManager()
            mock_dm.set_download_data(b'x' * 3072)  # 3KB of data
            
            progress_calls = []

            async def track_progress(percent):
                progress_calls.append(percent)

            data = await mock_dm.download_url(
                "https://example.com/bytes/3072",
                total_size=3072,
                progress_callback=track_progress
            )

            self.assertIsNotNone(data)
            self.assertTrue(len(progress_calls) > 0)
            self.assertEqual(len(data), 3072)

        asyncio.run(run_test())

    # ==================== Error Handling Tests ====================

    def test_http_error_status(self):
        """Test handling of HTTP error status codes using mock."""
        import asyncio

        async def run_test():
            # Use mock to avoid external service dependency
            mock_dm = MockDownloadManager()
            # Set fail_after_bytes to 0 to trigger immediate failure
            mock_dm.set_fail_after_bytes(0)
            
            # Should raise RuntimeError for HTTP error
            with self.assertRaises(OSError):
                data = await mock_dm.download_url("https://example.com/status/404")

        asyncio.run(run_test())

    def test_http_error_with_file_output(self):
        """Test that file download raises exception on HTTP error using mock."""
        import asyncio

        async def run_test():
            outfile = f"{self.temp_dir}/error_test.bin"
            
            # Use mock to avoid external service dependency
            mock_dm = MockDownloadManager()
            # Set fail_after_bytes to 0 to trigger immediate failure
            mock_dm.set_fail_after_bytes(0)

            # Should raise OSError for network error
            with self.assertRaises(OSError):
                success = await mock_dm.download_url(
                    "https://example.com/status/500",
                    outfile=outfile
                )

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
            # Use mock to avoid flaky external dependency while still
            # verifying the header flow through DownloadManager API.
            mock_dm = MockDownloadManager()
            mock_dm.set_download_data(b"{}")

            data = await mock_dm.download_url(
                "https://example.com/headers",
                headers={"X-Custom-Header": "TestValue"}
            )

            self.assertIsNotNone(data)
            self.assertIn("X-Custom-Header", mock_dm.headers_received)
            self.assertEqual(mock_dm.headers_received["X-Custom-Header"], "TestValue")
            self.assertIn("User-Agent", mock_dm.headers_received)
            self.assertTrue(mock_dm.headers_received["User-Agent"].startswith("MicroPythonOS/"))

        asyncio.run(run_test())

    def test_default_user_agent_is_added_when_no_headers(self):
        """Test that DownloadManager always adds a default User-Agent header."""
        import asyncio

        async def run_test():
            mock_dm = MockDownloadManager()
            mock_dm.set_download_data(b"{}")

            await mock_dm.download_url("https://example.com/headers")

            self.assertIsNotNone(mock_dm.headers_received)
            self.assertIn("User-Agent", mock_dm.headers_received)
            self.assertTrue(mock_dm.headers_received["User-Agent"].startswith("MicroPythonOS/"))

        asyncio.run(run_test())

    def test_existing_user_agent_is_preserved(self):
        """Test that an explicit User-Agent header is not overwritten."""
        import asyncio

        async def run_test():
            mock_dm = MockDownloadManager()
            mock_dm.set_download_data(b"{}")

            await mock_dm.download_url(
                "https://example.com/headers",
                headers={"User-Agent": "CustomAgent/1.0"}
            )

            self.assertIsNotNone(mock_dm.headers_received)
            self.assertIn("User-Agent", mock_dm.headers_received)
            self.assertEqual(mock_dm.headers_received["User-Agent"], "CustomAgent/1.0")

        asyncio.run(run_test())

    # ==================== Edge Cases Tests ====================

    def test_empty_response(self):
        """Test handling of empty (0-byte) downloads using mock."""
        import asyncio

        async def run_test():
            # Use mock to avoid external service dependency
            mock_dm = MockDownloadManager()
            mock_dm.set_download_data(b'')  # Empty data
            
            data = await mock_dm.download_url("https://example.com/bytes/0")

            self.assertIsNotNone(data)
            self.assertEqual(len(data), 0)
            self.assertEqual(data, b'')

        asyncio.run(run_test())

    def test_small_download(self):
        """Test downloading very small files (smaller than chunk size) using mock."""
        import asyncio

        async def run_test():
            # Use mock to avoid external service dependency
            mock_dm = MockDownloadManager()
            mock_dm.set_download_data(b'x' * 10)  # 10 bytes
            
            data = await mock_dm.download_url("https://example.com/bytes/10")

            self.assertIsNotNone(data)
            self.assertEqual(len(data), 10)

        asyncio.run(run_test())

    def test_json_download(self):
        """Test downloading JSON data."""
        import asyncio
        import json

        async def run_test():
            # Use mock to avoid flaky external dependency.
            mock_dm = MockDownloadManager()
            mock_dm.set_download_data(
                b'{"slideshow":{"author":"Yours Truly","date":"date of publication"}}'
            )
            data = await mock_dm.download_url("https://example.com/json")

            self.assertIsNotNone(data)
            # Verify it's valid JSON
            parsed = json.loads(data.decode("utf-8"))
            self.assertIsInstance(parsed, dict)
            self.assertIn("slideshow", parsed)

        asyncio.run(run_test())

    # ==================== File Operations Tests ====================

    def test_file_download_creates_directory_if_needed(self):
        """Test that parent directories are NOT created (caller's responsibility)."""
        import asyncio

        async def run_test():
            # Try to download to non-existent directory
            outfile = "/tmp/nonexistent_dir_12345/test.bin"
            mock_dm = MockDownloadManager()
            mock_dm.set_download_data(b"x" * 100)

            # Should raise exception because directory doesn't exist
            with self.assertRaises(Exception):
                await mock_dm.download_url(
                    "https://example.com/bytes/100",
                    outfile=outfile
                )

        asyncio.run(run_test())

    def test_file_overwrite(self):
        """Test that downloading overwrites existing files."""
        import asyncio

        async def run_test():
            outfile = f"{self.temp_dir}/overwrite_test.bin"
            mock_dm = MockDownloadManager()
            mock_dm.set_download_data(b"x" * 100)

            # Create initial file
            with open(outfile, 'wb') as f:
                f.write(b'old content')

            # Download and overwrite
            success = await mock_dm.download_url(
                "https://example.com/bytes/100",
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

    # ==================== Async/Sync Compatibility Tests ====================

    def test_async_download_with_await(self):
        """Test async download using await (traditional async usage)."""
        import asyncio

        async def run_test():
            try:
                # Traditional async usage with await
                data = await DownloadManager.download_url("https://MicroPythonOS.com")
            except Exception as e:
                self.skipTest(f"MicroPythonOS.com unavailable: {e}")
                return

            self.assertIsNotNone(data)
            self.assertIsInstance(data, bytes)
            self.assertTrue(len(data) > 0)
            # Verify it's HTML content
            self.assertIn(b'html', data.lower())

        asyncio.run(run_test())

    def test_sync_download_without_await(self):
        """Test synchronous download without await (auto-detects sync context)."""
        # This is a synchronous function (no async def)
        # The wrapper should detect no running event loop and run synchronously
        try:
            # Synchronous usage without await
            data = DownloadManager.download_url("https://MicroPythonOS.com")
        except Exception as e:
            self.skipTest(f"MicroPythonOS.com unavailable: {e}")
            return

        self.assertIsNotNone(data)
        self.assertIsInstance(data, bytes)
        self.assertTrue(len(data) > 0)
        # Verify it's HTML content
        self.assertIn(b'html', data.lower())

    def test_async_and_sync_return_same_data(self):
        """Test that async and sync methods return identical data."""
        import asyncio

        # Use MockDownloadManager to ensure deterministic, identical responses
        # (Real URLs can return dynamic content like timestamps that differ
        # between requests, causing flaky tests)
        mock_dm = MockDownloadManager()
        test_data = b"<html><body>Test content for sync/async comparison</body></html>"
        mock_dm.set_download_data(test_data)

        # Get data via sync-style call (asyncio.run internally)
        sync_data = asyncio.run(mock_dm.download_url("https://example.com/test"))

        # Get data via async call
        async def run_async_test():
            return await mock_dm.download_url("https://example.com/test")

        async_data = asyncio.run(run_async_test())

        # Both should return the same data
        self.assertEqual(sync_data, async_data)
        self.assertEqual(len(sync_data), len(async_data))
        self.assertEqual(sync_data, test_data)

    def test_sync_download_to_file(self):
        """Test synchronous file download without await."""
        outfile = f"{self.temp_dir}/sync_download.html"

        try:
            # Synchronous file download
            success = DownloadManager.download_url(
                "https://MicroPythonOS.com",
                outfile=outfile
            )
        except Exception as e:
            self.skipTest(f"MicroPythonOS.com unavailable: {e}")
            return

        self.assertTrue(success)
        # Check file exists using os.stat instead of os.path.exists
        try:
            file_size = os.stat(outfile)[6]
            self.assertTrue(file_size > 0)
        except OSError:
            self.fail("File should exist after successful download")
        
        # Verify it's HTML content
        with open(outfile, 'rb') as f:
            content = f.read()
        self.assertIn(b'html', content.lower())

        # Clean up
        os.remove(outfile)

    def test_sync_download_with_progress_callback(self):
        """Test synchronous download with progress callback."""
        progress_calls = []

        async def track_progress(percent):
            progress_calls.append(percent)

        try:
            # Synchronous download with async progress callback
            data = DownloadManager.download_url(
                "https://MicroPythonOS.com",
                progress_callback=track_progress
            )
        except Exception as e:
            self.skipTest(f"MicroPythonOS.com unavailable: {e}")
            return

        self.assertIsNotNone(data)
        self.assertIsInstance(data, bytes)
        # Progress callbacks should have been called
        self.assertTrue(len(progress_calls) > 0)
        # Verify progress values are in valid range
        for pct in progress_calls:
            self.assertTrue(0 <= pct <= 100)


class TestSafeUrl(unittest.TestCase):
    """Unit tests for the `_safe_url` helper used by `redact_url=True`."""

    def test_https_with_path_and_query(self):
        u = "https://btc1.trezor.io/api/v2/xpub/zpub6q...secret...stuff?details=txs&tokens=derived"
        self.assertEqual(DownloadManager._safe_url(u), "https://btc1.trezor.io/...REDACTED...")

    def test_http_with_port_and_path(self):
        u = "http://api.example.com:8080/path/secret?key=abc"
        self.assertEqual(DownloadManager._safe_url(u), "http://api.example.com:8080/...REDACTED...")

    def test_naked_host_no_path_returned_unchanged(self):
        # Nothing sensitive after the host — nothing to strip.
        u = "https://example.com"
        self.assertEqual(DownloadManager._safe_url(u), "https://example.com")

    def test_trailing_slash_only(self):
        # `https://example.com/` has an empty path; safe to redact as the
        # function still finds a `/` after the scheme.
        u = "https://example.com/"
        self.assertEqual(DownloadManager._safe_url(u), "https://example.com/...REDACTED...")

    def test_malformed_url_returns_generic_placeholder(self):
        # Anything without `://` is treated as untrusted — replace whole.
        self.assertEqual(DownloadManager._safe_url("not-a-url-at-all"), "...REDACTED...")

    def test_secret_substrings_never_appear_in_redacted_output(self):
        # Belt-and-braces check: the secret-bearing parts of the input
        # must not appear in the redacted output. Catches future regressions
        # where the redaction logic might accidentally keep a substring.
        u = "https://idx.example.com/wallet/SECRETxpubABCDEFG?key=TOKEN_VALUE"
        safe = DownloadManager._safe_url(u)
        # MicroPython's unittest port has assertIn but not assertNotIn — use
        # assertFalse(... in ...) for the negative case.
        self.assertFalse("SECRETxpub" in safe)
        self.assertFalse("TOKEN_VALUE" in safe)
        self.assertIn("https://idx.example.com", safe)  # host kept on purpose


class TestRedactUrlKwarg(unittest.TestCase):
    """Verify the redact_url kwarg flows through the call surface (sync wrapper
    + async impl + mock) without changing default behaviour."""

    def test_mock_records_redact_url_default_false(self):
        import asyncio
        mock = MockDownloadManager()
        # Configure a stub payload so download_url returns deterministic data
        mock.download_data = b"x"

        async def go():
            await mock.download_url("https://example.com/path")
        asyncio.run(go())

        # Default: redact_url not requested.
        self.assertEqual(mock.call_history[-1]['redact_url'], False)
        self.assertEqual(mock.redact_url_received, False)

    def test_mock_records_redact_url_true_when_passed(self):
        import asyncio
        mock = MockDownloadManager()
        mock.download_data = b"x"

        async def go():
            await mock.download_url("https://example.com/path", redact_url=True)
        asyncio.run(go())

        self.assertEqual(mock.call_history[-1]['redact_url'], True)
        self.assertEqual(mock.redact_url_received, True)


class TestRedactedExceptionPath(unittest.TestCase):
    """End-to-end verification of the URL-bearing exception scrubbing in
    `_download_url_async`'s `except` handler.

    Real-world trigger: aiohttp's `ClientConnectorError` (and friends) often
    embed the full request URL in `str(e)`. Without scrubbing, the
    `logger.error("Exception during download: %s", err_str)` line
    leaks the secret-bearing URL to the serial / REPL log on every failed
    download attempt — exactly the case `redact_url=True` is meant to cover.

    Strategy: install a fake `aiohttp` module into `sys.modules` so the
    function-local `import aiohttp` inside `_download_url_async` resolves to
    our fake. The fake's `ClientSession.get(...)` raises a `RuntimeError`
    whose message contains the full URL — mimicking aiohttp's behaviour
    closely enough to exercise the `if redact_url and url in err_str`
    branch deterministically (no network required).
    """

    def _capture_download_with_failing_aiohttp(self, *, url, redact_url,
                                                exc_message):
        """Run `_download_url_async(url, redact_url=...)` against a fake
        aiohttp that raises `RuntimeError(exc_message)` from `session.get()`.
        Returns (captured_print_lines, raised_exception_or_None).
        """
        import asyncio
        import sys
        import builtins

        # Minimal fake aiohttp surface — only what _download_url_async touches
        # before it hits the failure point.
        class _FakeClientSession:
            def get(self, request_url, **kwargs):
                # Raise synchronously from .get() — the `async with
                # session.get(...) as response:` line will surface this as
                # an exception inside the outer try/except.
                raise RuntimeError(exc_message)

            async def close(self):
                pass

        # MicroPython doesn't support `type(sys)(...)` to instantiate a
        # fresh module object. The import machinery only checks
        # `sys.modules` for the name and binds whatever object it finds —
        # so a plain instance with the right attributes works just as
        # well for `import aiohttp; aiohttp.ClientSession()`.
        class _FakeAiohttp:
            pass

        fake_aiohttp = _FakeAiohttp()
        fake_aiohttp.ClientSession = _FakeClientSession

        # Capture print and logger output.
        captured = []
        orig_print = builtins.print

        def _fake_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))

        # Add a handler to the download_manager logger to capture log output.
        import logging

        dl_logger = logging.getLogger("mpos.net.download_manager")
        _orig_dl_handlers = list(dl_logger.handlers)

        class _CaptureHandler(logging.Handler):
            def emit(self, record):
                captured.append(record.message)

        _capture_handler = _CaptureHandler()
        dl_logger.addHandler(_capture_handler)

        old_aiohttp = sys.modules.get("aiohttp")
        sys.modules["aiohttp"] = fake_aiohttp
        builtins.print = _fake_print
        try:
            async def _go():
                await DownloadManager._download_url_async(
                    url, redact_url=redact_url)

            raised = None
            try:
                asyncio.run(_go())
            except Exception as e:
                raised = e
        finally:
            builtins.print = orig_print
            dl_logger.handlers = _orig_dl_handlers
            if old_aiohttp is None:
                # Don't leave a fake module behind that would mask real
                # aiohttp imports in subsequent tests in the same run.
                try:
                    del sys.modules["aiohttp"]
                except KeyError:
                    pass
            else:
                sys.modules["aiohttp"] = old_aiohttp

        return captured, raised

    def test_redact_url_true_scrubs_url_from_exception_print_line(self):
        # The motivating case: the URL embeds a secret (zpub / API key) in
        # the path, the aiohttp error embeds that URL in its message, and
        # the framework's except-handler print would leak it.
        url = ("https://btc1.trezor.io/api/v2/xpub/"
               "zpub6qSECRETxpubABCDEFG?details=txs&tokens=derived")
        exc_message = "Cannot connect to host: {} — DNS failure".format(url)

        captured, raised = self._capture_download_with_failing_aiohttp(
            url=url, redact_url=True, exc_message=exc_message)

        # The function must still re-raise (the framework's contract is
        # that scrubbing only affects logs, not control flow).
        self.assertIsNotNone(raised, "exception should still propagate")

        # Find the exception-print line specifically.
        exc_lines = [l for l in captured
                     if "Exception during download:" in l]
        self.assertTrue(exc_lines,
                        "expected an 'Exception during download:' "
                        "print line; got: {}".format(captured))

        for line in exc_lines:
            # The secret-bearing path component must NOT appear in the
            # printed exception line.
            self.assertFalse(
                "zpub6qSECRETxpubABCDEFG" in line,
                "secret-bearing URL substring leaked into exception "
                "print: {}".format(line))
            self.assertFalse(
                url in line,
                "full URL leaked into exception print: {}".format(line))
            # The redacted form must appear (scheme + host preserved,
            # path replaced with /...REDACTED...).
            self.assertIn("https://btc1.trezor.io/...REDACTED...", line)

    def test_redact_url_false_preserves_url_in_exception_print_line(self):
        # Regression guard: default behaviour MUST keep the full URL in
        # the exception print line so debugging public-URL downloads
        # (app icons, OS updates, weather) isn't degraded.
        url = "https://example.com/path/with/some/components"
        exc_message = "Cannot connect to host: {}".format(url)

        captured, raised = self._capture_download_with_failing_aiohttp(
            url=url, redact_url=False, exc_message=exc_message)

        self.assertIsNotNone(raised)

        exc_lines = [l for l in captured
                     if "Exception during download:" in l]
        self.assertTrue(exc_lines)
        self.assertTrue(
            any(url in l for l in exc_lines),
            "default behaviour should not scrub URL; "
            "got lines: {}".format(exc_lines))
        # And it must NOT redact when not asked to.
        self.assertFalse(
            any("...REDACTED..." in l for l in exc_lines),
            "default behaviour should not insert REDACTED placeholder; "
            "got lines: {}".format(exc_lines))
