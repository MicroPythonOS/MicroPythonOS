"""
download_manager.py - Centralized download management for MicroPythonOS

Provides async HTTP download with flexible output modes:
- Download to memory (returns bytes)
- Download to file (returns bool)
- Streaming with chunk callback (returns bool)

Features:
- Shared aiohttp.ClientSession for performance
- Automatic session lifecycle management
- Thread-safe session access
- Retry logic (3 attempts per chunk, 10s timeout)
- Progress tracking with 2-decimal precision
- Download speed reporting
- Resume support via Range headers
- Network error detection utilities

Utility Functions:
    is_network_error(exception) - Check if error is recoverable network error
    get_resume_position(outfile) - Get file size for resume support

Example:
    from mpos import DownloadManager

    # Download to memory
    data = await DownloadManager.download_url("https://api.example.com/data.json")

    # Download to file with progress and speed
    async def on_progress(pct):
        print(f"{pct:.2f}%")  # e.g., "45.67%"

    async def on_speed(speed_bps):
        print(f"{speed_bps / 1024:.1f} KB/s")

    success = await DownloadManager.download_url(
        "https://example.com/file.bin",
        outfile="/sdcard/file.bin",
        progress_callback=on_progress,
        speed_callback=on_speed
    )

    # Stream processing
    async def process_chunk(chunk):
        # Process each chunk as it arrives
        pass

    success = await DownloadManager.download_url(
        "https://example.com/stream",
        chunk_callback=process_chunk
    )

    # Error handling with retry
    try:
        await DownloadManager.download_url(url, outfile="/sdcard/file.bin")
    except Exception as e:
        if DownloadManager.is_network_error(e):
            # Wait and retry with resume
            await asyncio.sleep(2)
            resume_from = DownloadManager.get_resume_position("/sdcard/file.bin")
            headers = {'Range': f'bytes={resume_from}-'} if resume_from > 0 else None
            await DownloadManager.download_url(url, outfile="/sdcard/file.bin", headers=headers)
        else:
            raise  # Fatal error
"""

# Constants
_DEFAULT_CHUNK_SIZE = 1024  # 1KB chunks
_DEFAULT_TOTAL_SIZE = 100 * 1024  # 100KB default if Content-Length missing
_MAX_RETRIES = 3  # Retry attempts per chunk
_CHUNK_TIMEOUT_SECONDS = 10  # Timeout per chunk read
_SPEED_UPDATE_INTERVAL_MS = 1000  # Update speed every 1 second

# Module-level state (singleton pattern)
_session = None
_session_lock = None
_session_refcount = 0


def _init():
    """Initialize DownloadManager (called automatically on first use)."""
    global _session_lock

    if _session_lock is not None:
        return  # Already initialized

    try:
        import _thread
        _session_lock = _thread.allocate_lock()
        print("DownloadManager: Initialized with thread safety")
    except ImportError:
        # Desktop mode without threading support (or MicroPython without _thread)
        _session_lock = None
        print("DownloadManager: Initialized without thread safety")


def _get_session():
    """Get or create the shared aiohttp session (thread-safe).

    Returns:
        aiohttp.ClientSession or None: The session instance, or None if aiohttp unavailable
    """
    global _session, _session_lock

    # Lazy init lock
    if _session_lock is None:
        _init()

    # Thread-safe session creation
    if _session_lock:
        _session_lock.acquire()

    try:
        if _session is None:
            try:
                import aiohttp
                _session = aiohttp.ClientSession()
                print("DownloadManager: Created new aiohttp session")
            except ImportError:
                print("DownloadManager: aiohttp not available")
                return None
        return _session
    finally:
        if _session_lock:
            _session_lock.release()


async def _close_session_if_idle():
    """Close session if no downloads are active (thread-safe).

    Note: MicroPythonOS aiohttp implementation doesn't require explicit session closing.
    Sessions are automatically closed via "Connection: close" header.
    This function is kept for potential future enhancements.
    """
    global _session, _session_refcount, _session_lock

    if _session_lock:
        _session_lock.acquire()

    try:
        if _session and _session_refcount == 0:
            # MicroPythonOS aiohttp doesn't have close() method
            # Sessions close automatically, so just clear the reference
            _session = None
            print("DownloadManager: Cleared idle session reference")
    finally:
        if _session_lock:
            _session_lock.release()


def is_session_active():
    """Check if a session is currently active.

    Returns:
        bool: True if session exists and is open
    """
    global _session, _session_lock

    if _session_lock:
        _session_lock.acquire()

    try:
        return _session is not None
    finally:
        if _session_lock:
            _session_lock.release()


async def close_session():
    """Explicitly close the session (optional, normally auto-managed).

    Useful for testing or forced cleanup. Session will be recreated
    on next download_url() call.

    Note: MicroPythonOS aiohttp implementation doesn't require explicit session closing.
    Sessions are automatically closed via "Connection: close" header.
    This function clears the session reference to allow garbage collection.
    """
    global _session, _session_lock

    if _session_lock:
        _session_lock.acquire()

    try:
        if _session:
            # MicroPythonOS aiohttp doesn't have close() method
            # Just clear the reference to allow garbage collection
            _session = None
            print("DownloadManager: Explicitly cleared session reference")
    finally:
        if _session_lock:
            _session_lock.release()


def is_network_error(exception):
    """Check if exception is a recoverable network error.
    
    Recognizes common network error codes and messages that indicate
    temporary connectivity issues that can be retried.
    
    Args:
        exception: Exception to check
        
    Returns:
        bool: True if this is a network error that can be retried
        
    Example:
        try:
            await DownloadManager.download_url(url)
        except Exception as e:
            if DownloadManager.is_network_error(e):
                # Retry or pause
                await asyncio.sleep(2)
                # retry...
            else:
                # Fatal error
                raise
    """
    error_str = str(exception).lower()
    error_repr = repr(exception).lower()
    
    # Common network error codes and messages
    # -113 = ECONNABORTED (connection aborted) - actually 103
    # -104 = ECONNRESET (connection reset by peer) - correct
    # -110 = ETIMEDOUT (connection timed out) - correct
    # -118 = EHOSTUNREACH (no route to host) - actually 113
    # -202 = DNS/connection error (network not ready)
    #
    # See lvgl_micropython/lib/esp-idf/components/lwip/lwip/src/include/lwip/errno.h
    network_indicators = [
        '-113', '-104', '-110', '-118', '-202',  # Error codes
        'econnaborted', 'econnreset', 'etimedout', 'ehostunreach',  # Error names
        'connection reset', 'connection aborted',  # Error messages
        'broken pipe', 'network unreachable', 'host unreachable',
        'failed to download chunk'  # From download_manager OSError(-110)
    ]
    
    return any(indicator in error_str or indicator in error_repr
              for indicator in network_indicators)


def get_resume_position(outfile):
    """Get the current size of a partially downloaded file.
    
    Useful for implementing resume functionality with Range headers.
    
    Args:
        outfile: Path to file
        
    Returns:
        int: File size in bytes, or 0 if file doesn't exist
        
    Example:
        resume_from = DownloadManager.get_resume_position("/sdcard/file.bin")
        if resume_from > 0:
            headers = {'Range': f'bytes={resume_from}-'}
            await DownloadManager.download_url(url, outfile=outfile, headers=headers)
    """
    try:
        import os
        return os.stat(outfile)[6]  # st_size
    except OSError:
        return 0


async def download_url(url, outfile=None, total_size=None,
                      progress_callback=None, chunk_callback=None, headers=None,
                      speed_callback=None):
    """Download a URL with flexible output modes.

    This async download function can be used in 3 ways:
    - with just a url => returns the content
    - with a url and an outfile => writes the content to the outfile
    - with a url and a chunk_callback => calls the chunk_callback(chunk_data) for each chunk

    Args:
        url (str): URL to download
        outfile (str, optional): Path to write file. If None, returns bytes.
        total_size (int, optional): Expected size in bytes for progress tracking.
                                   If None, uses Content-Length header or defaults to 100KB.
        progress_callback (coroutine, optional): async def callback(percent: float)
                                                Called with progress 0.00-100.00 (2 decimal places).
                                                Only called when progress changes by at least 0.01%.
        chunk_callback (coroutine, optional): async def callback(chunk: bytes)
                                             Called for each chunk. Cannot use with outfile.
        headers (dict, optional): HTTP headers (e.g., {'Range': 'bytes=1000-'})
        speed_callback (coroutine, optional): async def callback(bytes_per_second: float)
                                             Called periodically (every ~1 second) with download speed.

    Returns:
        bytes: Downloaded content (if outfile and chunk_callback are None)
        bool: True if successful (when using outfile or chunk_callback)

    Raises:
        ImportError: If aiohttp module is not available
        RuntimeError: If HTTP request fails (status code < 200 or >= 400)
        OSError: If chunk download times out after retries or network connection is lost
        ValueError: If both outfile and chunk_callback are provided
        Exception: Other download errors (propagated from aiohttp or chunk processing)

    Example:
        # Download to memory
        data = await DownloadManager.download_url("https://example.com/file.json")

        # Download to file with progress and speed
        async def on_progress(percent):
            print(f"Progress: {percent:.2f}%")

        async def on_speed(bps):
            print(f"Speed: {bps / 1024:.1f} KB/s")

        success = await DownloadManager.download_url(
            "https://example.com/large.bin",
            outfile="/sdcard/large.bin",
            progress_callback=on_progress,
            speed_callback=on_speed
        )

        # Stream processing
        async def on_chunk(chunk):
            process(chunk)

        success = await DownloadManager.download_url(
            "https://example.com/stream",
            chunk_callback=on_chunk
        )
    """
    # Validate parameters
    if outfile and chunk_callback:
        raise ValueError(
            "Cannot use both outfile and chunk_callback. "
            "Use outfile for saving to disk, or chunk_callback for streaming."
        )

    # Lazy init
    if _session_lock is None:
        _init()

    # Get/create session
    session = _get_session()
    if session is None:
        print("DownloadManager: Cannot download, aiohttp not available")
        raise ImportError("aiohttp module not available")

    # Increment refcount
    global _session_refcount
    if _session_lock:
        _session_lock.acquire()
    _session_refcount += 1
    if _session_lock:
        _session_lock.release()

    print(f"DownloadManager: Downloading {url}")

    fd = None
    try:
        # Ensure headers is a dict (aiohttp expects dict, not None)
        if headers is None:
            headers = {}

        async with session.get(url, headers=headers) as response:
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
    finally:
        # Decrement refcount
        if _session_lock:
            _session_lock.acquire()
        _session_refcount -= 1
        if _session_lock:
            _session_lock.release()

        # Close session if idle
        await _close_session_if_idle()
