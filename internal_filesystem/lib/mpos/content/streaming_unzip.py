""" streaming_unzip.py -- stream-extract a ZIP file from download chunks.

Avoids writing a temporary .mpk to storage by parsing local file headers
as the download stream arrives and extracting files on the fly.

MPK file format assumptions (strict)
------------------------------------
- Each .mpk is a valid ZIP archive.
- The **first** local file header MUST be a directory entry whose name
  matches the app's full name followed by ``/``
  (e.g. ``com.micropythonos.helloworld/``).
- That top-level directory MUST be the **only** top-level entry.
- All files are stored under that single top-level directory.
- Well-behaved tools parent directories before children, so the first entry
  gives us a reliable check before any large file data arrives.
- Only ``ZIP_STORED`` (0) and ``ZIP_DEFLATED`` (8) are supported.
- Local file headers contain accurate ``compressed_size`` and
  ``uncompressed_size`` (data descriptor flag must NOT be set).

Any archive violating these rules is rejected with ``RuntimeError`` so the
user knows the package is malformed or out of spec.

Usage:
    from mpos.content.streaming_unzip import StreamingUnzip

    async def download_and_extract(url, dest_folder):
        extractor = StreamingUnzip(dest_folder, expected_app_name="com.micropythonos.helloworld")
        result = await DownloadManager.download_url(
            url,
            chunk_callback=extractor.feed,
        )
        extractor.finish()
"""

import io
import logging
import os
import struct

logger = logging.getLogger(__name__)

# Local file header constants
_LOCAL_HEADER_MAGIC = b"PK\x03\x04"
_LOCAL_HEADER_STRUCT = "<4s2B4HL2L2H"
_LOCAL_HEADER_SIZE = struct.calcsize(_LOCAL_HEADER_STRUCT)

# Indices into unpacked local header tuple
_FH_GENERAL_PURPOSE_FLAG_BITS = 3
_FH_COMPRESSION_METHOD = 4
_FH_CRC = 7
_FH_COMPRESSED_SIZE = 8
_FH_UNCOMPRESSED_SIZE = 9
_FH_FILENAME_LENGTH = 10
_FH_EXTRA_FIELD_LENGTH = 11

ZIP_STORED = 0
ZIP_DEFLATED = 8


def _check_compression(method):
    if method not in (ZIP_STORED, ZIP_DEFLATED):
        raise RuntimeError("Unsupported compression method %d" % method)


def _sanitize_path(name):
    """Prevent path traversal by rejecting '..' components.  Preserves trailing slashes."""
    if not name:
        return ""
    trailing_slash = name.endswith("/")
    parts = name.split("/")
    filtered = []
    for p in parts:
        if p == "..":
            raise RuntimeError("Path traversal detected: %s" % name)
        if p and p != ".":
            filtered.append(p)
    result = "/".join(filtered)
    if trailing_slash:
        result += "/"
    return result


def _strip_leading_slash(name):
    if name.startswith("/"):
        name = name[1:]
    return name


def _makedirs(path):
    """MicroPython-compatible "os.makedirs"."""
    parts = path.split("/")
    acc = ""
    for part in parts:
        if not part:
            continue
        acc += part + "/"
        try:
            os.mkdir(acc)
        except OSError:
            pass


def _check_top_dir(filename, expected_app_name):
    """Validate the first ZIP entry is the expected top-level directory.

    Raises RuntimeError if the archive violates MPK spec.
    """
    if not filename.endswith("/"):
        raise RuntimeError(
            "First entry '%s' is not a directory. "
            "MPK archives must start with the top-level folder." % filename
        )
    top_dir = filename.rstrip("/")
    if top_dir != expected_app_name:
        raise RuntimeError(
            "Invalid top-level dir '%s' (expected '%s')" % (top_dir, expected_app_name)
        )


class StreamingUnzip:
    """Feed download chunks; extract ZIP members as they arrive.

    Parameters
    ----------
    dest_folder : str
        Root directory to write into.
    expected_app_name : str
        The app fullname that must appear as the single top-level directory.
        Example: ``"com.micropythonos.helloworld"``.
    free_space_limit : int or callable
        Bytes required before extraction begins, or a callable that receives
        the *total* archive bytes (sum of all ``uncompressed_size`` fields)
        and raises an exception if space is insufficient.
        When ``None`` (default), no pre-extraction space check is performed.
    """

    def __init__(self, dest_folder, expected_app_name, free_space_limit=None):
        if not dest_folder:
            raise ValueError("dest_folder required")
        if not expected_app_name:
            raise ValueError("expected_app_name required")
        self.dest_folder = dest_folder.rstrip(os.sep)
        self.expected_app_name = expected_app_name
        self.free_space_limit = free_space_limit
        self._buf = bytearray()
        self._state = "idle"
        self._current_header = None
        self._file_fd = None
        self._deflate_buf = None
        self._crc = 0
        self._files_extracted = 0
        self._first_header_checked = False
        self._total_uncompressed_estimate = 0

    def feed(self, data):
        """Inject the next download chunk (bytes)."""
        if not data:
            return
        self._buf += data
        while True:
            if self._state == "idle":
                if not self._parse_next_header():
                    break
            elif self._state == "data":
                if not self._consume_data():
                    break
            else:
                break

    def finish(self):
        """Called when the download stream is closed.

        Leaves any trailing non-header bytes in ``self._buf`` (usually the
        central directory or end-of-CD marker).
        """
        if self._file_fd is not None:
            logger.warning(
                "finish() called with file still open: %s (truncated download?)",
                self._current_header["filename"] if self._current_header else "<unknown>",
            )
            try:
                self._file_fd.close()
            except OSError:
                pass
            self._file_fd = None
        self._state = "idle"

    def _parse_next_header(self):
        """Try to parse a local file header from ``self._buf``.

        Returns ``True`` if a header was consumed and state switched to
        ``'data'``.  Returns ``False`` if there is not enough data yet.
        """
        while True:
            if len(self._buf) < _LOCAL_HEADER_SIZE:
                return False
            if bytes(self._buf[:4]) != _LOCAL_HEADER_MAGIC:
                # Skip ahead to next magic, or declare end of headers
                idx = self._buf.find(_LOCAL_HEADER_MAGIC, 1)
                if idx == -1:
                    # Keep at most suffix that could be a start of magic
                    # (3 bytes) so we don't split PK across chunks.
                    if len(self._buf) > 3:
                        self._buf = self._buf[-3:]
                    return False
                logger.warning(
                    "skipping %d unexpected bytes before next local header in %s",
                    idx,
                    self.expected_app_name,
                )
                self._buf = self._buf[idx:]
                continue

            vals = struct.unpack(_LOCAL_HEADER_STRUCT, self._buf[:_LOCAL_HEADER_SIZE])
            fname_len = vals[_FH_FILENAME_LENGTH]
            extra_len = vals[_FH_EXTRA_FIELD_LENGTH]
            header_total = _LOCAL_HEADER_SIZE + fname_len + extra_len
            if len(self._buf) < header_total:
                return False

            raw_name = bytes(self._buf[_LOCAL_HEADER_SIZE:_LOCAL_HEADER_SIZE + fname_len])
            try:
                filename = raw_name.decode("utf-8")
            except UnicodeError:
                filename = raw_name.decode("latin-1")

            # Decode and clean the filename, but preserve the raw version for
            # top-dir validation (sanitization strips trailing slashes).
            filename = _strip_leading_slash(filename)

            if not self._first_header_checked:
                _check_top_dir(filename, self.expected_app_name)
                self._first_header_checked = True
                _makedirs(self.dest_folder)

                # After validation of the top dir, sanity-check free space
                # by summing all headers we can currently see.
                if self.free_space_limit is not None:
                    self._total_uncompressed_estimate = _estimate_remaining(
                        self._buf[header_total:], vals[_FH_UNCOMPRESSED_SIZE]
                    )
                    _run_free_space_check(self.free_space_limit, self._total_uncompressed_estimate)

                # The top-level directory entry itself is consumed (skip)
                self._buf = self._buf[header_total:]
                continue

            filename = _sanitize_path(filename)

            # Every subsequent entry must live under the top-level dir
            if not filename.startswith(self.expected_app_name + "/"):
                extra = filename.split("/")[0] if "/" in filename else filename
                raise RuntimeError(
                    "Out-of-spec archive: entry '%s' is outside top-level dir '%s'"
                    % (filename, self.expected_app_name)
                )

            # Remove the prefix from the member name for extraction
            filename = filename[len(self.expected_app_name) + 1:]

            # Determine compression method and sizes
            comp_method = vals[_FH_COMPRESSION_METHOD]
            _check_compression(comp_method)

            # Consume header bytes so they are not included in file data
            self._buf = self._buf[header_total:]

            if not filename or filename.endswith("/"):
                # Directory entry
                target = self.dest_folder + os.sep + filename if filename else self.dest_folder
                _makedirs(target)
                self._files_extracted += 1
                continue

            # File entry
            target = self.dest_folder + os.sep + filename
            parent = target.rsplit(os.sep, 1)[0]
            if parent and parent != self.dest_folder:
                _makedirs(parent)

            self._file_fd = open(target, "wb")
            self._crc = 0
            self._current_header = {
                "filename": filename,
                "target": target,
                "compressed_size": vals[_FH_COMPRESSED_SIZE],
                "uncompressed_size": vals[_FH_UNCOMPRESSED_SIZE],
                "crc": vals[_FH_CRC],
                "method": comp_method,
                "header_total": header_total,
            }
            self._state = "data"
            return True

    def _consume_data(self):
        """Write file data from ``self._buf`` into the current output file.

        Returns ``True`` if more work may be possible; ``False`` to wait for
        more data.
        """
        info = self._current_header
        total_data = info["compressed_size"]
        method = info["method"]

        if method == ZIP_STORED:
            if total_data == 0:
                self._finish_file()
                return True
            available = min(len(self._buf), total_data)
            if available == 0:
                return False
            data = bytes(self._buf[:available])
            self._file_fd.write(data)
            try:
                import binascii
                self._crc = binascii.crc32(data, self._crc)
            except ImportError:
                pass
            self._buf = self._buf[available:]
            self._current_header["compressed_size"] = total_data - available
            if self._current_header["compressed_size"] <= 0:
                self._finish_file()
            return True

        if method == ZIP_DEFLATED:
            if total_data == 0:
                self._finish_file()
                return True
            available = min(len(self._buf), total_data)
            if available == 0:
                return False
            if self._deflate_buf is None:
                self._deflate_buf = bytearray()
            self._deflate_buf += self._buf[:available]
            self._buf = self._buf[available:]
            self._current_header["compressed_size"] = total_data - available
            if self._current_header["compressed_size"] <= 0:
                try:
                    import deflate
                    comp_stream = io.BytesIO(self._deflate_buf)
                    with deflate.DeflateIO(comp_stream, deflate.RAW, 15) as d:
                        decompressed = d.read()
                except ImportError:
                    import zlib
                    decompressed = zlib.decompress(bytes(self._deflate_buf), -15)
                self._file_fd.write(decompressed)
                try:
                    import binascii
                    self._crc = binascii.crc32(decompressed, self._crc)
                except ImportError:
                    pass
                self._deflate_buf = None
                self._finish_file()
            return True

        return False

    def _finish_file(self):
        """Close current file and validate CRC if possible."""
        if self._file_fd is not None:
            try:
                self._file_fd.close()
            except OSError:
                pass
            self._file_fd = None
        info = self._current_header
        if info["crc"] != 0:
            expected = info["crc"] & 0xFFFFFFFF
            got = self._crc & 0xFFFFFFFF
            if expected != got:
                logger.warning(
                    "CRC mismatch for %s: expected %08x got %08x",
                    info["filename"],
                    expected,
                    got,
                )
                raise RuntimeError(
                    "CRC mismatch for %s: expected %08x got %08x"
                    % (info["filename"], expected, got)
                )
        self._current_header = None
        self._state = "idle"
        self._files_extracted += 1


# ------------------------------------------------------------------
# Helpers for free-space checking
# ------------------------------------------------------------------

def _estimate_remaining(buf, first_uncompressed):
    """Scan the remaining buffer for all local headers and sum uncompressed sizes.

    Called immediately after validating the first header (which is the
    top-level directory).  ``first_uncompressed`` is 0 for a directory entry.
    This is a quick scan of headers already in ``buf``; it does NOT attempt
    to parse across large file bodies that span future chunks.
    """
    total = first_uncompressed
    b = bytearray(buf)
    while True:
        if len(b) < _LOCAL_HEADER_SIZE:
            break
        if bytes(b[:4]) != _LOCAL_HEADER_MAGIC:
            idx = b.find(_LOCAL_HEADER_MAGIC, 1)
            if idx == -1:
                break
            b = b[idx:]
            continue
        vals = struct.unpack(_LOCAL_HEADER_STRUCT, b[:_LOCAL_HEADER_SIZE])
        fname_len = vals[_FH_FILENAME_LENGTH]
        extra_len = vals[_FH_EXTRA_FIELD_LENGTH]
        header_total = _LOCAL_HEADER_SIZE + fname_len + extra_len
        if len(b) < header_total:
            break
        total += vals[_FH_UNCOMPRESSED_SIZE]
        compressed_size = vals[_FH_COMPRESSED_SIZE]
        if len(b) >= header_total + compressed_size:
            b = b[header_total + compressed_size:]
        else:
            remainder = b[header_total:]
            idx = remainder.find(_LOCAL_HEADER_MAGIC)
            if idx >= 0:
                b = b[header_total + idx:]
            else:
                break
        if len(b) < _LOCAL_HEADER_SIZE:
            break
    return total


def _run_free_space_check(limit_or_callable, required_bytes):
    """Invoke the user's free-space check.

    If ``limit_or_callable`` is an integer, raise ``RuntimeError`` when
    ``required_bytes`` exceeds it.  If it is callable, call it with
    ``required_bytes`` and let it raise whatever exception it wants.
    """
    if callable(limit_or_callable):
        limit_or_callable(required_bytes)
    elif required_bytes > limit_or_callable:
        raise RuntimeError(
            "Not enough free space (limit: %d bytes, needed: %d bytes)"
            % (limit_or_callable, required_bytes)
        )
