"""Contiguous (extent) files on littlefs2e.

An extent file is an immutable run of raw blocks. The bytes live verbatim in
that run, so a caller can map them (XIP, memory-mapped assets) or read them
without the CTZ skip-list. The inode is an ordinary littlefs file with an
extent tag. Extents use the standard littlefs 2.1 disk version: stock
littlefs can mount the image, but it treats the extent's blocks as free
space, so stock tools must be treated as read-only. The stored CRC lets a
consumer detect a stock write (or flash corruption) before using the data.

The low-level work is in the `lfs2e` C module (including the targeted
defragmenter); this file is policy: chunked streaming, the progress driver
for the defragmenter, and CRC.
"""

import asyncio
import binascii
import os

try:
    import lfs2e
except ImportError:  # desktop/web: no extents
    lfs2e = None

_CHUNK = 4096
# LFS2_ERR_NOCONTIG: free space exists, but no contiguous run of that size.
_NOCONTIG = 129
# An XIP core is mapped into the ESP32 MMU, whose page is 64 KiB.
XIP_ALIGN_BLOCKS = 16
# Defrag progress phases reported by lfs2e.defrag_step().
PHASE_SPACE = 0
PHASE_MOVE = 1
PHASE_ERASE = 2


def _abs(path):
    # The C module addresses the root littlefs directly; normalize app-relative
    # paths (the app's __file__ is usually relative) before crossing into C.
    return path if path.startswith("/") else "/" + path


def available():
    return lfs2e is not None


def geometry():
    """(block_size, block_count, disk_version)."""
    return lfs2e.geometry()


def info(path):
    """(offset, length, crc) for an extent file, or None."""
    if lfs2e is None:
        return None
    try:
        return lfs2e.info(_abs(path))
    except OSError:
        return None


def largest_run(align=1):
    if lfs2e is None:
        return 0
    return lfs2e.largest_run(align)


class Writer:
    """A streaming extent: reserve the run, write chunks, then commit.

    The installer writes a ZIP entry straight into flash as its bytes arrive,
    so it cannot go through :meth:`ensure` (which streams a finished file).
    The run is reserved up front because the ZIP header already says how long
    the payload is; ``commit()`` then turns the reservation into the inode at
    ``path``.
    """

    def __init__(self, length, align=1, defrag_first=True, _reserved=False):
        if lfs2e is None:
            raise OSError("extent support is not available on this host")
        length = int(length)
        if length <= 0:
            raise OSError("extent length must be positive")
        self.length = length
        self.offset = 0
        self._crc = 0
        self._done = False
        if _reserved:
            # open_writer() already reserved the run.
            return
        try:
            lfs2e.reserve(length, align)
        except OSError as error:
            if not defrag_first or not error.args or error.args[0] != _NOCONTIG:
                raise
            # Returns with the run reserved, like reserve().
            lfs2e.defrag(length, align)

    def write(self, data):
        if self._done:
            raise OSError("extent already committed")
        if self.offset + len(data) > self.length:
            raise OSError("extent write past its reserved length")
        lfs2e.write(self.offset, data)
        self._crc = binascii.crc32(data, self._crc)
        self.offset += len(data)

    def commit(self, path, crc=None):
        """Turn the reservation into an extent inode, and return its info."""
        if self._done:
            raise OSError("extent already committed")
        if self.offset != self.length:
            raise OSError("extent has %d of %d bytes" % (self.offset, self.length))
        if crc is None:
            crc = self._crc & 0xFFFFFFFF
        lfs2e.commit(_abs(path), crc)
        self._done = True
        return info(path)

    def abort(self):
        """Release the reservation (a no-op after a successful commit)."""
        if self._done:
            return
        self._done = True
        try:
            lfs2e.abort()
        except Exception:
            pass


async def open_writer(length, align=1, defrag_first=True, progress=None):
    """Reserve an extent, defragmenting in steps so the UI keeps painting.

    ``progress`` is awaited as ``progress(phase, percent)``; phase is one of
    ``PHASE_SPACE`` (choosing/scanning a window, no meaningful percent),
    ``PHASE_MOVE`` or ``PHASE_ERASE``, and percent is a best-effort 0..100.
    """
    if lfs2e is None:
        raise OSError("extent support is not available on this host")
    length = int(length)
    if length <= 0:
        raise OSError("extent length must be positive")
    try:
        lfs2e.reserve(length, align)
        return Writer(length, align, _reserved=True)
    except OSError as error:
        if not defrag_first or not error.args or error.args[0] != _NOCONTIG:
            raise

    shown = 0
    reported = -1
    lfs2e.defrag_begin(length, align, 0)
    try:
        while True:
            running, phase, percent = lfs2e.defrag_step()
            if phase == PHASE_MOVE:
                shown = max(shown, 40 + (40 * percent) // 100)
            elif phase == PHASE_ERASE:
                shown = max(shown, 80 + (20 * percent) // 100)
            # A step is ~17 ms; repainting per step would cost more than the
            # defrag itself, so report only when the percentage moves.
            if progress is not None and shown != reported:
                reported = shown
                await progress(phase, shown)
            if not running:
                break
            await asyncio.sleep(0)
        lfs2e.defrag_result()
        lfs2e.defrag_abort()
    except BaseException:
        lfs2e.defrag_abort()
        raise
    return Writer(length, align, _reserved=True)


def _reserve_sync(length, align, defrag_first, progress):
    """Reserve, driving the defrag steps with a *synchronous* progress hook.

    The caller's hook may repaint (``lv.refr_now()``) between steps, which is
    how a launch screen keeps its message alive without an event loop.
    """
    try:
        lfs2e.reserve(length, align)
    except OSError as error:
        if not defrag_first or not error.args or error.args[0] != _NOCONTIG:
            raise
        shown = 0
        reported = -1
        lfs2e.defrag_begin(length, align, 0)
        try:
            while True:
                running, phase, percent = lfs2e.defrag_step()
                if phase == PHASE_MOVE:
                    shown = max(shown, 40 + (40 * percent) // 100)
                elif phase == PHASE_ERASE:
                    shown = max(shown, 80 + (20 * percent) // 100)
                # A step is ~17 ms and a repaint costs about as much again, so
                # only report when the percentage moves.
                if progress is not None and shown != reported:
                    reported = shown
                    progress(phase, shown)
                if not running:
                    break
            lfs2e.defrag_result()
            lfs2e.defrag_abort()
        except BaseException:
            lfs2e.defrag_abort()
            raise


def _create(path, align, defrag_first=True, progress=None):
    path = _abs(path)
    size = os.stat(path)[6]
    if size <= 0:
        raise OSError("extent source is empty")

    _reserve_sync(size, align, defrag_first, progress)
    writer = Writer(size, align, _reserved=True)
    try:
        with open(path, "rb") as source:
            while True:
                chunk = source.read(_CHUNK)
                if not chunk:
                    break
                writer.write(chunk)
        if writer.offset != size:
            raise OSError("extent source changed while reading")
        return writer.commit(path)
    except Exception:
        writer.abort()
        raise


def ensure(path, align=1, defrag_first=True, progress=None):
    """Return (offset, length, crc) for `path`, converting it to an extent.

    An existing extent is returned as-is. A normal file (including an extent
    whose inode was later overwritten with normal data) is streamed into a
    fresh run, with one defrag attempt if the space is fragmented.
    ``progress(phase, percent)`` is called while defragmenting; it runs on the
    calling thread and may repaint.
    """
    if lfs2e is None:
        raise OSError("extent support is not available on this host")
    path = _abs(path)

    # An extent inode reports its payload length through stat, so check for
    # the extent tag before deciding that a non-empty file needs converting.
    found = info(path)
    if found is not None:
        return found

    try:
        size = os.stat(path)[6]
    except OSError:
        raise OSError("extent source not found: %s" % path)
    if size <= 0:
        raise OSError("empty file is not an extent: %s" % path)

    return _create(path, align, defrag_first, progress=progress)
