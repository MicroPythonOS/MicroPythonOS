"""
download_manager.py - HTTP download service for MicroPythonOS

Provides synchronous and asynchronous HTTP downloads with flexible output modes:
- Download to memory (returns bytes)
- Download to file (returns bool)
- Streaming with chunk callback (returns bool)

Features:
- Retry logic (3 attempts per chunk, 10s timeout)
- Progress tracking with 2-decimal precision
- Download speed reporting
- Resume support via Range headers
- Network error detection utilities
"""

import logging
logger = logging.getLogger(__name__)

# Constants
_DEFAULT_CHUNK_SIZE = 4 * 1024
_DEFAULT_TOTAL_SIZE = 100 * 1024  # 100KB default if Content-Length missing
_MAX_RETRIES = 3  # Retry attempts per chunk
_CHUNK_TIMEOUT_SECONDS = 10  # Timeout per chunk read
_SPEED_UPDATE_INTERVAL_MS = 1000  # Update speed every 1 second


class DownloadManager:
    """Centralized HTTP download service with flexible output modes."""

    @staticmethod
    def _build_user_agent():
        """Build the default User-Agent value for DownloadManager requests."""
        version = "unknown"
        device = "unknown"

        try:
            from mpos import BuildInfo

            version = BuildInfo.version.release
        except Exception:
            pass

        try:
            from mpos import DeviceInfo

            device = DeviceInfo.get_hardware_id()
        except Exception:
            pass

        return "MicroPythonOS/{} (device={})".format(version, device)

    @classmethod
    def _merge_headers(cls, headers=None):
        """Return request headers with a guaranteed User-Agent value."""
        merged_headers = {}
        if headers:
            merged_headers.update(headers)

        has_user_agent = False
        for key in merged_headers.keys():
            if str(key).lower() == "user-agent":
                has_user_agent = True
                break

        if not has_user_agent:
            merged_headers["User-Agent"] = cls._build_user_agent()

        return merged_headers
    
    @classmethod
    def download_url(cls, url, outfile=None, total_size=None,
                    progress_callback=None, chunk_callback=None, headers=None,
                    speed_callback=None, redact_url=False):
        """Download a URL with flexible output modes (sync or async wrapper).

        This method automatically detects whether it's being called from an async context
        and either returns a coroutine (for await) or runs synchronously.

        Args:
            url (str): URL to download (required)
            outfile (str, optional): Path to write file. If None, returns bytes.
            total_size (int, optional): Expected size in bytes for progress tracking.
            progress_callback (coroutine, optional): async def callback(percent: float)
            chunk_callback (coroutine, optional): async def callback(chunk: bytes)
            headers (dict, optional): HTTP headers (e.g., {'Range': 'bytes=1000-'})
            speed_callback (coroutine, optional): async def callback(bytes_per_second: float)
            redact_url (bool, optional): Opt in to redacting the URL in log
                output and the response-headers dump. Set True whenever the
                URL embeds an auth secret in its path or query string —
                e.g. an API key, an OAuth token, an LNBits readkey, or an
                xpub/ypub/zpub (which exposes the wallet's whole derivation
                tree). Only the `scheme://host[:port]` prefix is kept in
                logs; path + query are replaced with "/...REDACTED...".
                Defaults to False to preserve current debug output for
                callers fetching public URLs (app icons, OS updates, etc.).

        Returns:
            bytes: Downloaded content (if outfile and chunk_callback are None)
            bool: True if successful (when using outfile or chunk_callback)
            coroutine: If called from async context, returns awaitable

        Raises:
            ValueError: If both outfile and chunk_callback are provided
        """
        # Check if we're in an async context
        try:
            import asyncio
            try:
                asyncio.current_task()
                # We're in an async context, return the coroutine
                return cls._download_url_async(url, outfile, total_size,
                                              progress_callback, chunk_callback, headers,
                                              speed_callback, redact_url)
            except RuntimeError:
                # No running event loop, run synchronously
                return asyncio.run(cls._download_url_async(url, outfile, total_size,
                                                          progress_callback, chunk_callback, headers,
                                                          speed_callback, redact_url))
        except ImportError:
            # asyncio not available, shouldn't happen but handle gracefully
            raise ImportError("asyncio module not available")

    @staticmethod
    def _safe_url(url):
        """Return a log-safe rendering of `url` for use when the original URL
        carries a secret in its path or query string. Strips everything
        after `scheme://host[:port]` and replaces it with "/...REDACTED...".

        Examples:
            https://example.com/api/v2/xpub/zpub6q...  -> https://example.com/...REDACTED...
            https://api.example.com:8080/p?key=abc     -> https://api.example.com:8080/...REDACTED...
            https://example.com                        -> https://example.com  (no path to redact)
            not-a-url                                  -> ...REDACTED...
        """
        try:
            scheme_end = url.find("://")
            if scheme_end < 0:
                return "...REDACTED..."
            path_start = url.find("/", scheme_end + 3)
            if path_start < 0:
                # No path component — nothing sensitive to strip.
                return url
            return url[:path_start] + "/...REDACTED..."
        except Exception:
            return "...REDACTED..."

    @classmethod
    async def _download_url_async(cls, url, outfile=None, total_size=None,
                                 progress_callback=None, chunk_callback=None, headers=None,
                                 speed_callback=None, redact_url=False):
        """Download a URL with flexible output modes.
        
        Args:
            url (str): URL to download (required)
            outfile (str, optional): Path to write file. If None, returns bytes.
            total_size (int, optional): Expected size in bytes for progress tracking.
            progress_callback (coroutine, optional): async def callback(percent: float)
            chunk_callback (coroutine, optional): async def callback(chunk: bytes)
            headers (dict, optional): HTTP headers (e.g., {'Range': 'bytes=1000-'})
            speed_callback (coroutine, optional): async def callback(bytes_per_second: float)
            redact_url (bool, optional): When True, log a redacted URL
                (scheme://host only) and suppress the response-headers dump.
                See `download_url` for details and use cases.

        Returns:
            bytes: Downloaded content (if outfile and chunk_callback are None)
            bool: True if successful (when using outfile or chunk_callback)

        Raises:
            ValueError: If both outfile and chunk_callback are provided
        """
        # Validate parameters
        if outfile and chunk_callback:
            raise ValueError(
                "Cannot use both outfile and chunk_callback. "
                "Use outfile for saving to disk, or chunk_callback for streaming."
            )

        # Compute the log-safe rendering once; used for every URL-bearing print
        # below. When redact_url is False this is just the original URL, so
        # existing behaviour is preserved verbatim.
        log_url = cls._safe_url(url) if redact_url else url

        import aiohttp
        session = aiohttp.ClientSession()
        sslctx = None # for http
        if url.lower().startswith("https"):
            import ssl
            sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            sslctx.verify_mode = ssl.CERT_OPTIONAL # CERT_REQUIRED might fail because MBEDTLS_ERR_SSL_CA_CHAIN_REQUIRED

        if __debug__: logger.debug("Downloading %s", log_url)
        
        fd = None
        try:
            headers = cls._merge_headers(headers)
            
            # State that must survive a reconnect. On a mid-stream connection
            # drop we re-issue the request with a Range header from partial_size
            # and keep writing to the same fd, so a flaky link resumes the
            # download instead of aborting it.
            from mpos import TaskManager
            chunks = []
            chunk_size = _DEFAULT_CHUNK_SIZE
            partial_size = None   # absolute byte offset reached so far (None = no connection yet)
            last_progress_pct = -1.0
            speed_bytes_since_last_update = 0
            speed_last_update_time = None
            try:
                import time
                speed_last_update_time = time.ticks_ms()
            except ImportError:
                pass  # time module not available

            reconnects_left = _MAX_RETRIES
            while True:
                attempt_headers = dict(headers)
                resuming = partial_size is not None
                if resuming:
                    # Resume from where the stream dropped. A server that supports
                    # ranges replies 206; one that does not replies 200 (handled below).
                    attempt_headers['Range'] = 'bytes=%d-' % partial_size

                reconnect_needed = False
                async with session.get(url, headers=attempt_headers, ssl=sslctx, timeout=_CHUNK_TIMEOUT_SECONDS) as response:
                    if response.status < 200 or response.status >= 400:
                        logger.error("HTTP error %s", response.status)
                        raise RuntimeError(f"HTTP {response.status}")

                    if resuming:
                        # A 206 is required to safely append; a 200 means the server
                        # ignored Range and would resend from the start (can't resume).
                        if response.status != 206:
                            raise OSError(-110, "Server does not support resume (HTTP %s)" % response.status)
                    else:
                        # ---- one-time setup, runs only on the first connection ----
                        # When redacting, suppress the headers dump entirely - response
                        # headers can include set-cookie / cf-ray tokens that correlate
                        # to a secret-bearing URL.
                        if redact_url:
                            if __debug__: logger.debug("Response headers: <redacted>")
                        else:
                            if __debug__: logger.debug("Response headers: %s", response.headers)
                        resume_offset = 0  # Starting byte offset (0 for new downloads, >0 for caller-resumed)

                        if total_size is None:
                            # response.headers is a dict (after parsing) or None/list (before parsing)
                            try:
                                if isinstance(response.headers, dict):
                                    # Content-Range wins (caller-side resume): 'bytes 1323008-3485807/3485808'
                                    content_range = response.headers.get('Content-Range')
                                    if content_range:
                                        if '/' in content_range and ' ' in content_range:
                                            range_part = content_range.split(' ')[1].split('/')[0]
                                            resume_offset = int(range_part.split('-')[0])
                                            total_size = int(content_range.split('/')[-1])
                                            if __debug__: logger.debug("Resuming from byte %s, total size: %s", resume_offset, total_size)
                                    # Fall back to Content-Length if Content-Range absent
                                    if total_size is None:
                                        content_length = response.headers.get('Content-Length')
                                        if content_length:
                                            total_size = int(content_length)
                                            if __debug__: logger.debug("Using Content-Length: %s", total_size)
                            except (AttributeError, TypeError, ValueError, IndexError) as e:
                                logger.error("Could not parse Content-Range/Content-Length: %s", e)
                            if total_size is None:
                                logger.info("Unable to determine total_size, assuming %s bytes", _DEFAULT_TOTAL_SIZE)
                                total_size = _DEFAULT_TOTAL_SIZE

                        # Setup output
                        if outfile:
                            fd = open(outfile, 'wb')
                            if not fd:
                                logger.warning("Could not open %s for writing!", outfile)
                                return False

                        partial_size = resume_offset  # Start from resume offset for accurate progress
                        if __debug__: logger.debug("Downloading %s bytes in chunks of size %s", total_size, chunk_size)

                    # ---- read this connection until EOF or a read error ----
                    while True:
                        try:
                            chunk_data = await TaskManager.wait_for(
                                response.content.read(chunk_size),
                                _CHUNK_TIMEOUT_SECONDS
                            )
                        except Exception as e:
                            # A read error (timeout / dropped connection) is recoverable:
                            # break out and resume via a Range request below.
                            logger.error("Chunk read error: %s", e)
                            reconnect_needed = True
                            break

                        if not chunk_data:
                            # Chunk is empty, download complete
                            if __debug__: logger.debug("Finished downloading %s", log_url)
                            if fd:
                                fd.close()
                                fd = None
                                return True
                            elif chunk_callback:
                                return True
                            else:
                                return b''.join(chunks)

                        # Output chunk. Write/callback errors propagate - they are not
                        # connection problems, so they must not trigger a reconnect.
                        if fd:
                            fd.write(chunk_data)
                        elif chunk_callback:
                            await chunk_callback(chunk_data)
                        else:
                            chunks.append(chunk_data)

                        # Track bytes for speed calculation
                        chunk_len = len(chunk_data)
                        partial_size += chunk_len
                        speed_bytes_since_last_update += chunk_len

                        # Report progress with 2-decimal precision (only on change)
                        progress_pct = round((partial_size * 100) / int(total_size), 2)
                        if progress_callback and progress_pct != last_progress_pct:
                            if __debug__: logger.debug("Progress: %s / %s bytes = %s%%", partial_size, total_size, progress_pct)
                            await progress_callback(progress_pct)
                            last_progress_pct = progress_pct

                        # Report speed periodically
                        if speed_callback and speed_last_update_time is not None:
                            import time
                            current_time = time.ticks_ms()
                            elapsed_ms = time.ticks_diff(current_time, speed_last_update_time)
                            if elapsed_ms >= _SPEED_UPDATE_INTERVAL_MS:
                                bytes_per_second = (speed_bytes_since_last_update * 1000) / elapsed_ms
                                if __debug__: logger.debug("Speed: %s B/s", bytes_per_second)
                                await speed_callback(bytes_per_second)
                                speed_bytes_since_last_update = 0
                                speed_last_update_time = current_time

                # Connection ended without reaching EOF. Resume if we have budget.
                if not reconnect_needed:
                    break  # defensive: read loop only exits via return or reconnect
                reconnects_left -= 1
                if reconnects_left <= 0:
                    logger.error("Failed to download chunk after retries")
                    if fd:
                        fd.close()
                    raise OSError(-110, "Failed to download chunk after retries")
                if __debug__: logger.warning("Connection lost at %s/%s bytes, resuming...", partial_size, total_size)
                await TaskManager.sleep_ms(200)
        
        except Exception as e:
            # Exception strings from aiohttp often embed the full URL —
            # scrub it before printing when the caller asked for redaction.
            err_str = str(e)
            if redact_url and url in err_str:
                err_str = err_str.replace(url, log_url)
            logger.error("Exception during download: %s", err_str)
            import sys
            sys.print_exception(e)
            if fd:
                fd.close()
            raise  # Re-raise the exception instead of suppressing it
    
    @staticmethod
    def is_network_error(exception):
        """Check if exception is a recoverable network error.
        
        Args:
            exception: Exception to check
            
        Returns:
            bool: True if this is a network error that can be retried
        """
        error_str = str(exception).lower()
        error_repr = repr(exception).lower()
        
        # Common network error codes and messages
        network_indicators = [
            '-113', '-104', '-110', '-118', '-202',  # Error codes
            'econnaborted', 'econnreset', 'etimedout', 'ehostunreach',  # Error names
            'connection reset', 'connection aborted',  # Error messages
            'broken pipe', 'network unreachable', 'host unreachable',
            'failed to download chunk'  # From download_manager OSError(-110)
        ]
        
        return any(indicator in error_str or indicator in error_repr
                  for indicator in network_indicators)
    
    @staticmethod
    def get_resume_position(outfile):
        """Get the current size of a partially downloaded file.
        
        Args:
            outfile: Path to file
            
        Returns:
            int: File size in bytes, or 0 if file doesn't exist
        """
        try:
            import os
            return os.stat(outfile)[6]  # st_size
        except OSError:
            return 0


# Module-level exports for convenience
is_network_error = DownloadManager.is_network_error
get_resume_position = DownloadManager.get_resume_position
