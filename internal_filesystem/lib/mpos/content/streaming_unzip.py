""" streaming_unzip.py -- stream-extract a ZIP file from download chunks.

Avoids writing a temporary .mpk to storage by parsing local file headers
as the download stream arrives and extracting files on the fly.

Usage:
    from mpos.content.streaming_unzip import StreamingUnzip

    async def download_and_extract(url, dest_folder):
        extractor = StreamingUnzip(dest_folder)
        # Optional: pre-peek strip prefix from first chunk
        result = await DownloadManager.download_url(
            url,
            chunk_callback=extractor.feed,
        )
        extractor.finish()

Requires `deflate` module (MicroPython) or `zlib` (CPython).
Assumes local file headers contain accurate compressed_size/uncompressed_size
(data descriptor flag NOT set).
"""

import io
import os
import struct

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
    """Prevent path traversal by rejecting '..' components."""
    if not name:
        return ""
    parts = name.split("/")
    filtered = []
    for p in parts:
        if p == "..":
            raise RuntimeError("Path traversal detected: %s" % name)
        if p and p != ".":
            filtered.append(p)
    return "/".join(filtered)


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


class StreamingUnzip:
    """Feed download chunks; extract ZIP members as they arrive.

    Parameters
    ----------
    dest_folder : str
        Root directory to write into.
    strip_prefix : str
        If set, remove this prefix (and trailing slash) from every
        archive member name before extraction.
    """

    def __init__(self, dest_folder, strip_prefix=""):
        if not dest_folder:
            raise ValueError("dest_folder required")
        self.dest_folder = dest_folder.rstrip(os.sep)
        self.strip_prefix = strip_prefix
        self._buf = bytearray()
        # State machine: 'idle' -> reading member's 'data'
        self._state = "idle"
        self._current_header = None  # dict with parsed header fields
        self._file_fd = None
        self._deflate_buf = None  # bytearray for accumulated compressed data
        self._crc = 0
        self._files_extracted = 0

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

        Leaves any trailing non-header bytes in self._buf (usually the
        central directory or end-of-CD marker).
        """
        if self._file_fd is not None:
            try:
                self._file_fd.close()
            except OSError:
                pass
            self._file_fd = None
        self._state = "idle"

    def _parse_next_header(self):
        """Try to parse a local file header from self._buf.

        Returns True if a header was consumed and state switched to 'data'.
        Returns False if there is not enough data yet.
        """
        while True:
            if len(self._buf) < _LOCAL_HEADER_SIZE:
                return False
            if bytes(self._buf[:4]) != _LOCAL_HEADER_MAGIC:
                # skip ahead to next magic, or declare end of headers
                idx = self._buf.find(_LOCAL_HEADER_MAGIC, 1)
                if idx == -1:
                    # Keep at most suffix that could be start of magic
                    # (3 bytes) so we don't split PK across chunks
                    if len(self._buf) > 3:
                        self._buf = self._buf[-3:]
                    return False
                self._buf = self._buf[idx:]
                continue

            # Parse fixed header fields
            vals = struct.unpack(_LOCAL_HEADER_STRUCT, self._buf[:_LOCAL_HEADER_SIZE])
            fname_len = vals[_FH_FILENAME_LENGTH]
            extra_len = vals[_FH_EXTRA_FIELD_LENGTH]
            header_total = _LOCAL_HEADER_SIZE + fname_len + extra_len
            if len(self._buf) < header_total:
                return False

            # Extract filename (bytes -> str via utf-8)
            raw_name = bytes(self._buf[_LOCAL_HEADER_SIZE: _LOCAL_HEADER_SIZE + fname_len])
            try:
                filename = raw_name.decode("utf-8")
            except UnicodeError:
                filename = raw_name.decode("latin-1")

            filename = _strip_leading_slash(filename)
            filename = _sanitize_path(filename)

            if self.strip_prefix:
                if filename.startswith(self.strip_prefix):
                    filename = filename[len(self.strip_prefix):]
                    if filename.startswith("/"):
                        filename = filename[1:]
                else:
                    # skip this entry entirely
                    compressed_size = vals[_FH_COMPRESSED_SIZE]
                    self._buf = self._buf[header_total + compressed_size:]
                    continue

            if not filename:
                # Likely root directory entry; skip
                compressed_size = vals[_FH_COMPRESSED_SIZE]
                self._buf = self._buf[header_total + compressed_size:]
                continue

            # Determine compression method and sizes
            comp_method = vals[_FH_COMPRESSION_METHOD]
            _check_compression(comp_method)

            # Consume header bytes so they are not included in file data
            self._buf = self._buf[header_total:]

            # Build target path
            target = self.dest_folder + os.sep + filename if filename else self.dest_folder

            if filename.endswith("/") or (vals[_FH_UNCOMPRESSED_SIZE] == 0 and vals[_FH_COMPRESSED_SIZE] == 0):
                # Directory entry
                _makedirs(target)
                # header already consumed above
                self._files_extracted += 1
                continue

            # File entry: open output handle and prepare for data
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
        """Write file data from self._buf into the current output file.

        Returns True if more work may be possible; False to wait for more data.
        """
        info = self._current_header
        total_data = info["compressed_size"]
        method = info["method"]

        if method == ZIP_STORED:
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
            available = min(len(self._buf), total_data)
            if available == 0:
                return False
            if self._deflate_buf is None:
                self._deflate_buf = bytearray()
            self._deflate_buf += self._buf[:available]
            self._buf = self._buf[available:]
            self._current_header["compressed_size"] = total_data - available
            if self._current_header["compressed_size"] <= 0:
                # Decompress and write
                try:
                    import deflate
                    comp_stream = io.BytesIO(self._deflate_buf)
                    with deflate.DeflateIO(comp_stream, deflate.RAW, 15) as d:
                        decompressed = d.read()
                except ImportError:
                    # CPython fallback (no deflate module)
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

        # Should never reach here
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
        # CRC check (optional)
        if info["crc"] != 0:
            expected = info["crc"] & 0xFFFFFFFF
            got = self._crc & 0xFFFFFFFF
            if expected != got:
                raise RuntimeError("CRC mismatch for %s: expected %08x got %08x" % (info["filename"], expected, got))
        self._current_header = None
        self._state = "idle"
        self._files_extracted += 1


def peek_strip_prefix(data_bytes, expected_name):
    """Peek at local headers in the first chunk to figure out strip_prefix.

    Returns the strip_prefix string to use with StreamingUnzip, or
    raises ValueError on mismatch.
    """
    buf = bytearray(data_bytes)
    top_dirs = set()
    has_top_files = False

    while True:
        if len(buf) < _LOCAL_HEADER_SIZE:
            break
        if bytes(buf[:4]) != _LOCAL_HEADER_MAGIC:
            idx = buf.find(_LOCAL_HEADER_MAGIC, 1)
            if idx == -1:
                break
            buf = buf[idx:]
            continue
        vals = struct.unpack(_LOCAL_HEADER_STRUCT, buf[:_LOCAL_HEADER_SIZE])
        fname_len = vals[_FH_FILENAME_LENGTH]
        extra_len = vals[_FH_EXTRA_FIELD_LENGTH]
        header_total = _LOCAL_HEADER_SIZE + fname_len + extra_len
        if len(buf) < header_total:
            break
        raw_name = bytes(buf[_LOCAL_HEADER_SIZE: _LOCAL_HEADER_SIZE + fname_len])
        try:
            filename = raw_name.decode("utf-8")
        except UnicodeError:
            filename = raw_name.decode("latin-1")
        filename = _strip_leading_slash(filename).strip("/")
        compressed_size = vals[_FH_COMPRESSED_SIZE]
        uncomp_size = vals[_FH_UNCOMPRESSED_SIZE]

        if filename:
            if "/" in filename:
                top_dirs.add(filename.split("/", 1)[0])
            else:
                if uncomp_size != 0 or compressed_size != 0:
                    has_top_files = True
                else:
                    top_dirs.add(filename)

        buf = buf[header_total + compressed_size:]
        if len(buf) < _LOCAL_HEADER_SIZE:
            break

    if has_top_files or len(top_dirs) != 1:
        return ""
    sole = next(iter(top_dirs))
    if sole == expected_name:
        return sole + "/"
    else:
        raise ValueError("Invalid top-level dir '%s' (expected '%s')" % (sole, expected_name))
