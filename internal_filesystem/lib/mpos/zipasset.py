"""Load one file out of a ZIP archive without writing it to the filesystem.

A game's data is often a single read-only blob read at random offsets: Doom's
1.8 MiB WAD, later Duke's 3.6 MiB GRP. Shipping it deflated and inflating it
once at launch into a RAM buffer is the way to get it there on a badge:

* the download and the flash copy stay small (a WAD deflates to about 40 %);
* the engine reads it from RAM instead of through littlefs, which is the
  difference between a few milliseconds and ~1.3 MB/s of flash reads on an
  asset that every frame touches;
* the buffer is volatile, so the unpack is paid on each launch. That is why
  the caller gets a progress callback: it owns the "Unpacking..." screen.

Only the local file headers are parsed, which is all a stream needs. The
entry's declared uncompressed size is used to allocate the buffer before any
data is read, so a truncated or lying archive fails instead of growing.
"""

import binascii
import struct

_LOCAL_HEADER_MAGIC = b"PK\x03\x04"
_LOCAL_HEADER_STRUCT = "<4s2B4HL2L2H"
_LOCAL_HEADER_SIZE = struct.calcsize(_LOCAL_HEADER_STRUCT)

_FH_COMPRESSION_METHOD = 4
_FH_CRC = 7
_FH_COMPRESSED_SIZE = 8
_FH_UNCOMPRESSED_SIZE = 9
_FH_FILENAME_LENGTH = 10
_FH_EXTRA_FIELD_LENGTH = 11

ZIP_STORED = 0
ZIP_DEFLATED = 8

_READ_CHUNK = 64 * 1024


class ZipAssetError(RuntimeError):
    """The archive is missing the entry, or the entry is corrupt."""


def entries(path):
    """The file names in the archive, in storage order."""
    names = []
    with open(path, "rb") as archive:
        while True:
            entry = _read_header(archive)
            if entry is None:
                break
            if not entry["name"].endswith("/"):
                names.append(entry["name"])
            _skip(archive, entry["compressed_size"])
    return names


def entry_size(path, entry=None):
    """The entry's declared uncompressed size, or 0 when it is missing."""
    try:
        with open(path, "rb") as archive:
            found = _find(archive, entry)
    except OSError:
        return 0
    return found["uncompressed_size"] if found is not None else 0


def load(path, entry=None, progress=None, buffer=None):
    """Inflate ``entry`` (default: the first file) and return its buffer.

    Returns ``(buffer, size)``. ``progress(done, total)`` is called as bytes
    land in the buffer. Raises :class:`ZipAssetError` when the entry is
    missing, unknown-sized, uses an unsupported method, or fails its CRC.

    ``buffer`` is an optional destination with the exact uncompressed size (for
    a caller that keeps the asset in C-heap memory, see ``mpos_core.buffer``);
    it is filled in place. Without it a ``bytearray`` is allocated here.
    """
    try:
        with open(path, "rb") as archive:
            wanted = _find(archive, entry)
            if wanted is None:
                raise ZipAssetError("%s: no entry %s" % (path, entry or "<first>"))
            size = wanted["uncompressed_size"]
            if size <= 0:
                raise ZipAssetError("%s: entry %s has no declared size"
                                    % (path, wanted["name"]))
            if buffer is None:
                buffer = bytearray(size)
            elif len(buffer) != size:
                raise ZipAssetError(
                    "%s: buffer holds %d bytes, the entry needs %d"
                    % (path, len(buffer), size))
            if wanted["method"] == ZIP_STORED:
                _read_stored(archive, buffer, progress)
            elif wanted["method"] == ZIP_DEFLATED:
                _read_deflated(archive, buffer, progress)
            else:
                raise ZipAssetError("%s: unsupported compression method %d"
                                    % (path, wanted["method"]))
    except ZipAssetError:
        raise
    except Exception as error:
        # A corrupt deflate stream raises EOFError/ValueError/OSError
        # depending on where it breaks; the caller only wants one error.
        raise ZipAssetError("%s: %s" % (path, error))

    crc = binascii.crc32(buffer, 0) & 0xFFFFFFFF
    if wanted["crc"] != 0 and crc != wanted["crc"]:
        raise ZipAssetError("%s: %s failed its CRC (expected %08x, got %08x)"
                            % (path, wanted["name"], wanted["crc"], crc))
    return buffer, size


def _read_header(archive):
    header = archive.read(_LOCAL_HEADER_SIZE)
    if len(header) < _LOCAL_HEADER_SIZE:
        return None
    if header[:4] != _LOCAL_HEADER_MAGIC:
        return None
    vals = struct.unpack(_LOCAL_HEADER_STRUCT, header)
    name_len = vals[_FH_FILENAME_LENGTH]
    extra_len = vals[_FH_EXTRA_FIELD_LENGTH]
    raw = archive.read(name_len)
    try:
        name = raw.decode("utf-8")
    except UnicodeError:
        name = raw.decode("latin-1")
    if extra_len:
        archive.read(extra_len)
    return {
        "name": name,
        "method": vals[_FH_COMPRESSION_METHOD],
        "crc": vals[_FH_CRC],
        "compressed_size": vals[_FH_COMPRESSED_SIZE],
        "uncompressed_size": vals[_FH_UNCOMPRESSED_SIZE],
    }


def _skip(archive, count):
    try:
        archive.seek(count, 1)
    except OSError:
        for _ in range(count):
            archive.read(1)


def _find(archive, entry):
    while True:
        header = _read_header(archive)
        if header is None:
            return None
        name = header["name"]
        if name.endswith("/"):
            continue
        if entry is None or name == entry or name.endswith("/" + entry):
            return header
        _skip(archive, header["compressed_size"])


def _read_stored(archive, buffer, progress):
    done = 0
    while done < len(buffer):
        chunk = archive.read(min(_READ_CHUNK, len(buffer) - done))
        if not chunk:
            raise ZipAssetError("truncated entry")
        buffer[done:done + len(chunk)] = chunk
        done += len(chunk)
        if progress is not None:
            progress(done, len(buffer))


def _read_deflated(archive, buffer, progress):
    try:
        import deflate
    except ImportError:
        raise ZipAssetError("this firmware cannot inflate assets")
    stream = deflate.DeflateIO(archive, deflate.RAW, 15)
    view = memoryview(buffer)
    done = 0
    try:
        while done < len(buffer):
            count = stream.readinto(view[done:done + _READ_CHUNK])
            if not count:
                break
            done += count
            if progress is not None:
                progress(done, len(buffer))
    finally:
        try:
            stream.close()
        except Exception:
            pass
    if done != len(buffer):
        raise ZipAssetError("entry is shorter than its declared size (%d of %d)"
                            % (done, len(buffer)))
