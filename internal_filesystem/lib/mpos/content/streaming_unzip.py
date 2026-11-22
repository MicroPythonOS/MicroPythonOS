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

Native files
------------
A manifest may carry a ``"native"`` map (platform key -> file names). This
extractor installs only the files selected for the running host (see
``mpos.platform``) and skips the ones built for other platforms, so one .mpk
serves every target. A ``*.xip`` selected that way is streamed straight into
a littlefs2e extent instead of a normal file: the engine is then mapped from
flash without a first-launch conversion.

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
import json
import logging
import os
import struct

from .. import extent as extent_files
from .. import platform as mpos_platform

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

MANIFEST_NAME = "MANIFEST.JSON"
# A manifest is a few KB; refuse to buffer something that is not one.
_MANIFEST_MAX = 64 * 1024


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
    """MicroPython-compatible \"os.makedirs\"."""
    parts = path.split("/")
    acc = ""
    for part in parts:
        if not part:
            continue
        acc += part + "/"
        try:
            # FAT32 (SD card) rejects directory paths ending with '/' for os.mkdir().
            os.mkdir(acc.rstrip("/") or "/")
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
        Bytes required per extracted entry, or a callable that receives each
        entry's uncompressed size and raises an exception if space is
        insufficient. Checked as each entry starts, so the check reflects the
        free space that is actually left. When ``None`` (default), no
        pre-extraction space check is performed.
    native_keys : list of str
        Platform keys (``mpos.platform.native_keys()``) whose native files are
        installed. The parameter exists so tests can pretend to be a board.
    """

    def __init__(self, dest_folder, expected_app_name, free_space_limit=None,
                 native_keys=None):
        if not dest_folder:
            raise ValueError("dest_folder required")
        if not expected_app_name:
            raise ValueError("expected_app_name required")
        self.dest_folder = dest_folder.rstrip(os.sep)
        self.expected_app_name = expected_app_name
        self.free_space_limit = free_space_limit
        self.native_keys = (mpos_platform.native_keys()
                            if native_keys is None else list(native_keys))
        self._buf = bytearray()
        self._state = "idle"
        self._current_header = None
        self._file_fd = None
        self._deflate_buf = None
        self._crc = 0
        self._files_extracted = 0
        self._files_skipped = 0
        self._first_header_checked = False
        # The manifest's "native" map: None until the manifest is extracted,
        # then a dict (empty when the app ships no native files).
        self._native = None
        self._native_files = ()
        self._selected_native = ()
        self._manifest_buf = None
        # The running extent sink for a selected .xip, if any.
        self._extent = None
        self._extent_target = None
        # (length, align) while the parser waits for an extent writer.
        self._space_request = None
        self._skip_remaining = 0

    def feed(self, data):
        """Inject the next chunk.

        Returns None, or ``(length, align)`` when the parser reached a file
        that must be written as an extent: the caller reserves it (which may
        defragment) and hands the writer back with :meth:`resume`.
        """
        if data:
            self._buf += data
        return self._process()

    def _process(self):
        try:
            while True:
                if self._state == "space":
                    return self._space_request
                if self._state == "idle":
                    if not self._parse_next_header():
                        break
                elif self._state == "data":
                    if not self._consume_data():
                        break
                elif self._state == "skip":
                    if not self._consume_skip():
                        break
                else:
                    break
        except Exception:
            self._abort_extent()
            if self._file_fd is not None:
                try:
                    self._file_fd.close()
                except OSError:
                    pass
                self._file_fd = None
            raise
        return None

    def resume(self, writer):
        """Attach the writer for the last space request and keep parsing."""
        self._extent = writer
        self._space_request = None
        self._state = "data"
        return self._process()

    def feed_all(self, data, space_handler=None):
        """Drive :meth:`feed` to completion synchronously."""
        request = self.feed(data)
        while request is not None:
            if space_handler is not None:
                writer = space_handler(request[0], request[1])
            else:
                writer = extent_files.Writer(
                    request[0], request[1], defrag_first=True)
            request = self.resume(writer)
        return None

    async def feed_async(self, data, space_handler):
        """Like :meth:`feed_all`, awaiting the handler between chunks."""
        request = self.feed(data)
        while request is not None:
            writer = await space_handler(request[0], request[1])
            request = self.resume(writer)
        return None

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
        if self._extent is not None:
            name = self._extent_target
            logger.warning(
                "finish() called with an extent still open: %s (truncated download?)",
                name,
            )
            self._abort_extent()
            raise RuntimeError("truncated package: %s is incomplete" % (name,))
        self._state = "idle"

    def _abort_extent(self):
        writer = self._extent
        self._extent = None
        self._extent_target = None
        if writer is not None:
            writer.abort()

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

                # The top-level directory entry itself is consumed (skip)
                self._buf = self._buf[header_total:]
                continue

            filename = _sanitize_path(filename)

            # Every subsequent entry must live under the top-level dir
            if not filename.startswith(self.expected_app_name + "/"):
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

            action = self._classify(filename, vals[_FH_UNCOMPRESSED_SIZE])

            if action == "skip":
                self._skip_remaining = vals[_FH_COMPRESSED_SIZE]
                self._current_header = {"filename": filename}
                if self._skip_remaining <= 0:
                    # Nothing to discard: keep parsing headers in this buffer.
                    self._finish_skip()
                    continue
                self._state = "skip"
                return True

            target = self.dest_folder + os.sep + filename
            parent = target.rsplit(os.sep, 1)[0]
            if parent and parent != self.dest_folder:
                _makedirs(parent)

            self._crc = 0
            if action == "xip":
                self._extent_target = target
                self._file_fd = None
                # Reserving the run may defragment the filesystem, which has
                # to yield to the UI and must not straddle an open archive.
                # Stop here and let the caller build the writer.
                self._space_request = (
                    int(vals[_FH_UNCOMPRESSED_SIZE]),
                    extent_files.XIP_ALIGN_BLOCKS)
                next_state = "space"
            else:
                self._file_fd = open(target, "wb")
                next_state = "data"
            self._current_header = {
                "filename": filename,
                "target": target,
                "compressed_size": vals[_FH_COMPRESSED_SIZE],
                "uncompressed_size": vals[_FH_UNCOMPRESSED_SIZE],
                "crc": vals[_FH_CRC],
                "method": comp_method,
                "header_total": header_total,
                "action": action,
            }
            if filename == MANIFEST_NAME:
                self._manifest_buf = bytearray()
            self._state = next_state
            return True

    def _classify(self, filename, uncompressed_size):
        """Decide what to do with an entry: extract, xip, or skip.

        Native files are the ones listed under any ``"native"`` key. The
        selected ones belong to this host; the others are for another board or
        desktop and are not installed.
        """
        native = self._native
        if native is not None and filename in self._native_files:
            if filename not in self._selected_native:
                self._files_skipped += 1
                return "skip"

        # The manifest must come before the files it describes: a native file
        # that arrives earlier cannot be classified, and extracting it "just in
        # case" would leave a file for the wrong platform on the device.
        if native is None and self._looks_native(filename):
            raise RuntimeError(
                "Out-of-spec archive: '%s' comes before %s"
                % (filename, MANIFEST_NAME)
            )

        if self.free_space_limit is not None:
            _run_free_space_check(self.free_space_limit, uncompressed_size)

        if filename.endswith(".xip") and extent_files.available():
            return "xip"
        return "extract"

    @staticmethod
    def _looks_native(filename):
        return filename.endswith(".xip") or (
            filename.startswith("module_") and filename.endswith(".mpy"))

    def _parse_manifest(self):
        data = self._manifest_buf
        self._manifest_buf = None
        if not data:
            self._native = {}
            return
        try:
            manifest = json.loads(bytes(data).decode("utf-8"))
        except Exception as error:
            raise RuntimeError(
                "Invalid %s in %s: %s"
                % (MANIFEST_NAME, self.expected_app_name, error))
        native = manifest.get("native")
        if not isinstance(native, dict):
            self._native = {}
            return
        files = {}
        selected = {}
        for key in native:
            entries = native[key]
            if not isinstance(entries, list):
                raise RuntimeError(
                    "Invalid native list for '%s' in %s"
                    % (key, self.expected_app_name))
            for name in entries:
                files[name] = True
                if key in self.native_keys:
                    selected[name] = True
        self._native = native
        self._native_files = tuple(files)
        self._selected_native = tuple(selected)

    def _consume_skip(self):
        """Discard the body of an entry that is for another platform."""
        if self._skip_remaining <= 0:
            self._finish_skip()
            return True
        available = min(len(self._buf), self._skip_remaining)
        if available == 0:
            return False
        self._buf = self._buf[available:]
        self._skip_remaining -= available
        if self._skip_remaining <= 0:
            self._finish_skip()
        return True

    def _finish_skip(self):
        self._current_header = None
        self._state = "idle"
        self._files_extracted += 1

    def _write_out(self, data):
        if self._extent is not None:
            self._extent.write(data)
        elif self._file_fd is not None:
            self._file_fd.write(data)

    def _consume_data(self):
        """Write file data from ``self._buf`` into the current output sink.

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
            self._write_out(data)
            self._crc = _crc32(data, self._crc)
            if info["filename"] == MANIFEST_NAME:
                self._capture_manifest(data)
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
                decompressed = _inflate(self._deflate_buf)
                self._deflate_buf = None
                self._write_out(decompressed)
                self._crc = _crc32(decompressed, self._crc)
                if info["filename"] == MANIFEST_NAME:
                    self._capture_manifest(decompressed)
                self._finish_file()
            return True

        return False

    def _capture_manifest(self, data):
        if self._manifest_buf is None:
            return
        if len(self._manifest_buf) + len(data) > _MANIFEST_MAX:
            raise RuntimeError("%s in %s is too large" % (MANIFEST_NAME, self.expected_app_name))
        self._manifest_buf += data

    def _finish_file(self):
        """Close the current sink, validate its CRC, and commit an extent."""
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
                if self._extent is not None:
                    self._abort_extent()
                raise RuntimeError(
                    "CRC mismatch for %s: expected %08x got %08x"
                    % (info["filename"], expected, got)
                )
        extent = self._extent
        target = self._extent_target
        self._extent = None
        self._extent_target = None
        if extent is not None:
            try:
                extent.commit(target, info["crc"] & 0xFFFFFFFF)
            except Exception:
                extent.abort()
                raise
        if info["filename"] == MANIFEST_NAME and self._manifest_buf is not None:
            self._parse_manifest()
        self._current_header = None
        self._state = "idle"
        self._files_extracted += 1


def _crc32(data, crc):
    try:
        import binascii
        return binascii.crc32(data, crc)
    except ImportError:
        return crc


def _inflate(compressed):
    try:
        import deflate
        return deflate.DeflateIO(
            io.BytesIO(compressed), deflate.RAW, 15).read()
    except ImportError:
        import zlib
        return zlib.decompress(bytes(compressed), -15)


# ------------------------------------------------------------------
# Helpers for free-space checking
# ------------------------------------------------------------------

def _run_free_space_check(limit_or_callable, required_bytes):
    """Invoke the user's free-space check for one entry.

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


def get_zip_crc32(zip_path):
    """Return CRC32 of the first file entry in a ZIP archive, or None."""
    try:
        with open(zip_path, "rb") as f:
            header = f.read(_LOCAL_HEADER_SIZE)
    except OSError:
        return None
    if len(header) < _LOCAL_HEADER_SIZE:
        return None
    try:
        fields = struct.unpack(_LOCAL_HEADER_STRUCT, header)
    except Exception:
        return None
    if fields[0] != _LOCAL_HEADER_MAGIC:
        return None
    return fields[_FH_CRC]
