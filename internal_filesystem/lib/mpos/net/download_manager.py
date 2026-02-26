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

# Constants
_DEFAULT_CHUNK_SIZE = 4 * 1024
_DEFAULT_TOTAL_SIZE = 100 * 1024  # 100KB default if Content-Length missing
_MAX_RETRIES = 3  # Retry attempts per chunk
_CHUNK_TIMEOUT_SECONDS = 10  # Timeout per chunk read
_SPEED_UPDATE_INTERVAL_MS = 1000  # Update speed every 1 second


class DownloadManager:
    """Centralized HTTP download service with flexible output modes."""
    
    @classmethod
    def download_url(cls, url, outfile=None, total_size=None,
                    progress_callback=None, chunk_callback=None, headers=None,
                    speed_callback=None):
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
                                              speed_callback)
            except RuntimeError:
                # No running event loop, run synchronously
                return asyncio.run(cls._download_url_async(url, outfile, total_size,
                                                          progress_callback, chunk_callback, headers,
                                                          speed_callback))
        except ImportError:
            # asyncio not available, shouldn't happen but handle gracefully
            raise ImportError("asyncio module not available")
    
    @classmethod
    async def _download_url_async(cls, url, outfile=None, total_size=None,
                                 progress_callback=None, chunk_callback=None, headers=None,
                                 speed_callback=None):
        """Download a URL with flexible output modes.
        
        Args:
            url (str): URL to download (required)
            outfile (str, optional): Path to write file. If None, returns bytes.
            total_size (int, optional): Expected size in bytes for progress tracking.
            progress_callback (coroutine, optional): async def callback(percent: float)
            chunk_callback (coroutine, optional): async def callback(chunk: bytes)
            headers (dict, optional): HTTP headers (e.g., {'Range': 'bytes=1000-'})
            speed_callback (coroutine, optional): async def callback(bytes_per_second: float)
        
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

        import aiohttp
        session = aiohttp.ClientSession()
        sslctx = None # for http
        if url.lower().startswith("https"):
            import ssl
            sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            sslctx.verify_mode = ssl.CERT_OPTIONAL # CERT_REQUIRED might fail because MBEDTLS_ERR_SSL_CA_CHAIN_REQUIRED

        print(f"DownloadManager: Downloading {url}")
        
        fd = None
        try:
            # Ensure headers is a dict (aiohttp expects dict, not None)
            if headers is None:
                headers = {}
            
            async with session.get(url, headers=headers, ssl=sslctx) as response:
                if response.status < 200 or response.status >= 400:
                    print(f"DownloadManager: HTTP error {response.status}")
                    raise RuntimeError(f"HTTP {response.status}")
                
                # Figure out total size and starting offset (for resume support)
                print("DownloadManager: Response headers:", response.headers)
                resume_offset = 0  # Starting byte offset (0 for new downloads, >0 for resumed)
                
                if total_size is None:
                    # response.headers is a dict (after parsing) or None/list (before parsing)
                    try:
                        if isinstance(response.headers, dict):
                            # Check for Content-Range first (used when resuming with Range header)
                            # Format: 'bytes 1323008-3485807/3485808'
                            # START is the resume offset, TOTAL is the complete file size
                            content_range = response.headers.get('Content-Range')
                            if content_range:
                                # Parse total size and starting offset from Content-Range header
                                # Example: 'bytes 1323008-3485807/3485808' -> offset=1323008, total=3485808
                                if '/' in content_range and ' ' in content_range:
                                    # Extract the range part: '1323008-3485807'
                                    range_part = content_range.split(' ')[1].split('/')[0]
                                    # Extract starting offset
                                    resume_offset = int(range_part.split('-')[0])
                                    # Extract total size
                                    total_size = int(content_range.split('/')[-1])
                                    print(f"DownloadManager: Resuming from byte {resume_offset}, total size: {total_size}")
                            
                            # Fall back to Content-Length if Content-Range not present
                            if total_size is None:
                                content_length = response.headers.get('Content-Length')
                                if content_length:
                                    total_size = int(content_length)
                                    print(f"DownloadManager: Using Content-Length: {total_size}")
                    except (AttributeError, TypeError, ValueError, IndexError) as e:
                        print(f"DownloadManager: Could not parse Content-Range/Content-Length: {e}")
                    
                    if total_size is None:
                        print(f"DownloadManager: WARNING: Unable to determine total_size, assuming {_DEFAULT_TOTAL_SIZE} bytes")
                        total_size = _DEFAULT_TOTAL_SIZE
                
                # Setup output
                if outfile:
                    fd = open(outfile, 'wb')
                    if not fd:
                        print(f"DownloadManager: WARNING: could not open {outfile} for writing!")
                        return False
                
                chunks = []
                partial_size = resume_offset  # Start from resume offset for accurate progress
                chunk_size = _DEFAULT_CHUNK_SIZE
                
                # Progress tracking with 2-decimal precision
                last_progress_pct = -1.0  # Track last reported progress to avoid duplicates
                
                # Speed tracking
                speed_bytes_since_last_update = 0
                speed_last_update_time = None
                try:
                    import time
                    speed_last_update_time = time.ticks_ms()
                except ImportError:
                    pass  # time module not available
                
                print(f"DownloadManager: {'Writing to ' + outfile if outfile else 'Downloading'} {total_size} bytes in chunks of size {chunk_size}")
                
                # Download loop with retry logic
                while True:
                    tries_left = _MAX_RETRIES
                    chunk_data = None
                    while tries_left > 0:
                        try:
                            # Import TaskManager here to avoid circular imports
                            from mpos import TaskManager
                            chunk_data = await TaskManager.wait_for(
                                response.content.read(chunk_size),
                                _CHUNK_TIMEOUT_SECONDS
                            )
                            break
                        except Exception as e:
                            print(f"DownloadManager: Chunk read error: {e}")
                            tries_left -= 1
                    
                    if tries_left == 0:
                        print("DownloadManager: ERROR: failed to download chunk after retries!")
                        if fd:
                            fd.close()
                        raise OSError(-110, "Failed to download chunk after retries")
                    
                    if chunk_data:
                        # Output chunk
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
                        
                        # Report progress with 2-decimal precision
                        # Only call callback if progress changed by at least 0.01%
                        progress_pct = round((partial_size * 100) / int(total_size), 2)
                        if progress_callback and progress_pct != last_progress_pct:
                            print(f"DownloadManager: Progress: {partial_size} / {total_size} bytes = {progress_pct:.2f}%")
                            await progress_callback(progress_pct)
                            last_progress_pct = progress_pct
                        
                        # Report speed periodically
                        if speed_callback and speed_last_update_time is not None:
                            import time
                            current_time = time.ticks_ms()
                            elapsed_ms = time.ticks_diff(current_time, speed_last_update_time)
                            if elapsed_ms >= _SPEED_UPDATE_INTERVAL_MS:
                                # Calculate bytes per second
                                bytes_per_second = (speed_bytes_since_last_update * 1000) / elapsed_ms
                                print(f"DownloadManager: Speed: {bytes_per_second} bytes / second")
                                await speed_callback(bytes_per_second)
                                # Reset for next interval
                                speed_bytes_since_last_update = 0
                                speed_last_update_time = current_time
                    else:
                        # Chunk is None, download complete
                        print(f"DownloadManager: Finished downloading {url}")
                        if fd:
                            fd.close()
                            fd = None
                            return True
                        elif chunk_callback:
                            return True
                        else:
                            return b''.join(chunks)
        
        except Exception as e:
            print(f"DownloadManager: Exception during download: {e}")
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
