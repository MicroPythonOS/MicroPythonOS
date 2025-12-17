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
- Progress tracking
- Resume support via Range headers

Example:
    from mpos import DownloadManager

    # Download to memory
    data = await DownloadManager.download_url("https://api.example.com/data.json")

    # Download to file with progress
    async def progress(pct):
        print(f"{pct}%")

    success = await DownloadManager.download_url(
        "https://example.com/file.bin",
        outfile="/sdcard/file.bin",
        progress_callback=progress
    )

    # Stream processing
    async def process_chunk(chunk):
        # Process each chunk as it arrives
        pass

    success = await DownloadManager.download_url(
        "https://example.com/stream",
        chunk_callback=process_chunk
    )
"""

# Constants
_DEFAULT_CHUNK_SIZE = 1024  # 1KB chunks
_DEFAULT_TOTAL_SIZE = 100 * 1024  # 100KB default if Content-Length missing
_MAX_RETRIES = 3  # Retry attempts per chunk
_CHUNK_TIMEOUT_SECONDS = 10  # Timeout per chunk read

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


async def download_url(url, outfile=None, total_size=None,
                      progress_callback=None, chunk_callback=None, headers=None):
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
        progress_callback (coroutine, optional): async def callback(percent: int)
                                                Called with progress 0-100.
        chunk_callback (coroutine, optional): async def callback(chunk: bytes)
                                             Called for each chunk. Cannot use with outfile.
        headers (dict, optional): HTTP headers (e.g., {'Range': 'bytes=1000-'})

    Returns:
        bytes: Downloaded content (if outfile and chunk_callback are None)
        bool: True if successful, False if failed (when using outfile or chunk_callback)

    Raises:
        ValueError: If both outfile and chunk_callback are provided

    Example:
        # Download to memory
        data = await DownloadManager.download_url("https://example.com/file.json")

        # Download to file with progress
        async def on_progress(percent):
            print(f"Progress: {percent}%")

        success = await DownloadManager.download_url(
            "https://example.com/large.bin",
            outfile="/sdcard/large.bin",
            progress_callback=on_progress
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
        return False if (outfile or chunk_callback) else None

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
                return False if (outfile or chunk_callback) else None

            # Figure out total size
            print("DownloadManager: Response headers:", response.headers)
            if total_size is None:
                # response.headers is a dict (after parsing) or None/list (before parsing)
                try:
                    if isinstance(response.headers, dict):
                        content_length = response.headers.get('Content-Length')
                        if content_length:
                            total_size = int(content_length)
                except (AttributeError, TypeError, ValueError) as e:
                    print(f"DownloadManager: Could not parse Content-Length: {e}")

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
            partial_size = 0
            chunk_size = _DEFAULT_CHUNK_SIZE

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
                    return False if (outfile or chunk_callback) else None

                if chunk_data:
                    # Output chunk
                    if fd:
                        fd.write(chunk_data)
                    elif chunk_callback:
                        await chunk_callback(chunk_data)
                    else:
                        chunks.append(chunk_data)

                    # Report progress
                    partial_size += len(chunk_data)
                    progress_pct = round((partial_size * 100) / int(total_size))
                    print(f"DownloadManager: Progress: {partial_size} / {total_size} bytes = {progress_pct}%")
                    if progress_callback:
                        await progress_callback(progress_pct)
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
        return False if (outfile or chunk_callback) else None
    finally:
        # Decrement refcount
        if _session_lock:
            _session_lock.acquire()
        _session_refcount -= 1
        if _session_lock:
            _session_lock.release()

        # Close session if idle
        await _close_session_if_idle()
