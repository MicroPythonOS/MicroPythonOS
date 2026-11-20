"""Contiguous (extent) files on littlefs2e.

An extent file is an immutable run of raw blocks. The bytes live verbatim in
that run, so a caller can map them (XIP, memory-mapped assets) or read them
without the CTZ skip-list. The inode is an ordinary littlefs file with an
extent tag. Extents use the standard littlefs 2.1 disk version: stock
littlefs can mount the image, but it treats the extent's blocks as free
space, so stock tools must be treated as read-only. The stored CRC lets a
consumer detect a stock write (or flash corruption) before using the data.

The low-level work is in the `lfs2e` C module; this file is policy:
chunked streaming, CRC, and a targeted defragmenter for when the free space
is large enough but not contiguous.
"""

import binascii
import os

try:
    import lfs2e
except ImportError:  # desktop/web: no extents
    lfs2e = None

_CHUNK = 4096
# A window may not contain a directory pair: metadata is moved by littlefs
# itself, not by the defragmenter.
_NOCONTIG = 129
# An XIP core is mapped into the ESP32 MMU, whose page is 64 KiB.
XIP_ALIGN_BLOCKS = 16


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

    def __init__(self, length, align=1, defrag_first=True):
        if lfs2e is None:
            raise OSError("extent support is not available on this host")
        length = int(length)
        if length <= 0:
            raise OSError("extent length must be positive")
        self.length = length
        self.offset = 0
        self._crc = 0
        self._done = False
        try:
            lfs2e.reserve(length, align)
        except OSError as error:
            block_size, _, _ = lfs2e.geometry()
            need = (length + block_size - 1) // block_size
            if not defrag_first or not error.args or error.args[0] != _NOCONTIG:
                raise
            if not defrag(need, align):
                raise
            lfs2e.reserve(length, align)

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


def _create(path, align, defrag_first=True):
    path = _abs(path)
    size = os.stat(path)[6]
    if size <= 0:
        raise OSError("extent source is empty")

    writer = Writer(size, align, defrag_first)
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


# Defrag only relocates files on the root littlefs. Other mounts (the frozen
# /builtin VFS, an SD card) are read-only or a different filesystem; walking
# them would fail in every lfs2e call and can be very large.
_OTHER_MOUNTS = ("/builtin", "/sdcard", "/roms")


def _walk(root="/"):
    """Yield (path, size) for regular files on the root littlefs."""
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            names = os.listdir(directory)
        except OSError:
            continue
        for name in names:
            path = directory.rstrip("/") + "/" + name
            if path in _OTHER_MOUNTS:
                continue
            try:
                st = os.stat(path)
            except OSError:
                continue
            if st[0] & 0x4000:
                stack.append(path)
            elif st[0] & 0x8000:
                yield path, st[6]


def _bit_get(map_, bit):
    return (map_[bit >> 3] >> (bit & 7)) & 1


def defrag(need, align=1, budget=None):
    """Free one aligned run of `need` blocks by relocating the files in it.

    Returns True when a run of `need` blocks is available afterwards. Moves
    whole files with copy+rename (atomic per file) and excludes the window
    from the allocator while doing so. Only normal files are moved: extents
    are immutable and metadata pairs are left alone.
    """
    # TODO(later): the window scan below is O(block_count²) in Python.
    # Precompute free-run intervals (or a run list) so a candidate window's
    # outside max hole is O(runs) instead of a full map scan per candidate.
    # 77 s worst case on a full 7 MiB badge is acceptable for a one-time
    # install; do not add a progress callback until this is faster.
    if lfs2e is None:
        return False
    block_size, block_count, _ = lfs2e.geometry()
    if need <= 0 or need > block_count:
        return False
    align = max(1, align)

    used = lfs2e.used_map()
    meta = lfs2e.meta_map()
    used_blocks = 0
    for i in range(block_count):
        used_blocks += _bit_get(used, i)
    free_bytes = (block_count - used_blocks) * block_size
    extent_bytes = need * block_size
    if budget is None:
        budget = min(
            4 * extent_bytes,
            max(256 * 1024, (block_count * block_size) // 8),
            free_bytes // 2,
        )

    # Map every data block to the file that owns it. Extent blocks are
    # unmovable, so a window containing one is skipped.
    owners = {}
    files = {}
    unmovable = set()
    for path, size in _walk("/"):
        try:
            blocks = lfs2e.file_blocks(path)
        except OSError:
            continue
        if not blocks:
            continue
        if info(path) is not None:
            for block in blocks:
                unmovable.add(block)
            continue
        files[path] = (size, blocks)
        for block in blocks:
            owners[block] = path

    best = None
    best_cost = None
    for start in range(0, block_count - need + 1, align):
        ok = True
        occupants = {}
        for block in range(start, start + need):
            if _bit_get(meta, block) or block in unmovable:
                ok = False
                break
            path = owners.get(block)
            if path is not None:
                occupants[path] = True
        if not ok:
            continue
        # A file can only be moved if a run of its block count exists outside
        # the window (the copy is made before the old blocks are freed). Skip
        # windows whose occupants are too large for any available hole.
        max_hole = 0
        run = 0
        for block in range(block_count):
            if start <= block < start + need:
                run = 0
                continue
            if _bit_get(used, block):
                run = 0
            else:
                run += 1
                if run > max_hole:
                    max_hole = run
        for path in occupants:
            # The current file's block list is the exact count its copy will
            # need (CTZ packing can need one more block than ceil(size/bs)).
            blocks = len(files[path][1])
            if blocks > max_hole:
                ok = False
                break
        if not ok:
            continue
        cost = 0
        for path in occupants:
            cost += files[path][0]
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best = start
            if cost == 0:
                break

    if best is None or best_cost is None or best_cost > budget:
        return False

    # Move the occupants out of the window. The allocator exclusion keeps the
    # copies (and any metadata commit) from landing back inside it.
    lfs2e.exclude(best, need)
    try:
        for path in occupants:
            tmp = path + ".dfg"
            try:
                os.remove(tmp)
            except OSError:
                pass
            try:
                with open(path, "rb") as source:
                    with open(tmp, "wb") as dest:
                        while True:
                            chunk = source.read(_CHUNK)
                            if not chunk:
                                break
                            dest.write(chunk)
                os.rename(tmp, path)
            except OSError:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                return False
    finally:
        lfs2e.clear_exclude()

    return lfs2e.largest_run(align) >= need


def ensure(path, align=1, defrag_first=True):
    """Return (offset, length, crc) for `path`, converting it to an extent.

    An existing extent is returned as-is. A normal file (including an extent
    whose inode was later overwritten with normal data) is streamed into a
    fresh run, with one defrag attempt if the space is fragmented.
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

    return _create(path, align, defrag_first)
