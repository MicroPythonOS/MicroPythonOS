# Reimplement, because CPython3.3 impl is rather bloated
import os
import errno
from collections import namedtuple

_ntuple_diskusage = namedtuple("usage", ("total", "used", "free"))


def rmtree(d):
    if not d:
        raise ValueError

    # FAT32 (SD card) rejects directory paths ending with '/' for os.listdir()/os.rmdir().
    d = d.rstrip("/") or "/"
    for name, type, *_ in os.ilistdir(d):
        path = d + "/" + name
        if type & 0x4000:  # dir
            rmtree(path)
        else:  # file
            os.unlink(path)
    os.rmdir(d)


def copyfileobj(src, dest, length=512):
    if hasattr(src, "readinto"):
        buf = bytearray(length)
        while True:
            sz = src.readinto(buf)
            if not sz:
                break
            if sz == length:
                dest.write(buf)
            else:
                b = memoryview(buf)[:sz]
                dest.write(b)
    else:
        while True:
            buf = src.read(length)
            if not buf:
                break
            dest.write(buf)


def copyfile(src, dst):
    with open(src, "rb") as fsrc:
        with open(dst, "wb") as fdst:
            copyfileobj(fsrc, fdst)


def copytree(src, dst):
    # FAT32 (SD card) rejects directory paths ending with '/' for os.listdir()/os.mkdir().
    src = src.rstrip("/") or "/"
    dst = dst.rstrip("/") or "/"
    os.mkdir(dst)
    for name, type, *_ in os.ilistdir(src):
        src_path = src + "/" + name
        dst_path = dst + "/" + name
        if type & 0x4000:  # dir
            copytree(src_path, dst_path)
        else:
            copyfile(src_path, dst_path)


def move(src, dst):
    """Move src to dst.

    If dst is an existing directory, src is moved inside it.
    Tries os.rename() first (fast, same-filesystem); falls back to
    copy + delete when rename raises OSError (e.g. cross-filesystem).
    """
    # If dst is an existing directory, move src *into* it.
    # FAT32 (SD card) rejects directory paths ending with '/' for os.stat().
    try:
        st = os.stat(dst.rstrip("/") or "/")
        if st[0] & 0x4000:  # directory
            dst = dst.rstrip("/") + "/" + src.rsplit("/", 1)[-1]
    except OSError:
        pass  # dst does not exist yet — that is fine

    # Fast path: same filesystem rename.
    try:
        os.rename(src, dst)
        return
    except OSError as e:
        if e.args[0] not in (errno.EXDEV, errno.EPERM, errno.ENOTSUP):
            raise

    # Slow path: copy then remove (cross-filesystem or FAT limitation).
    # FAT32 (SD card) rejects directory paths ending with '/' for os.stat().
    try:
        st = os.stat(src.rstrip("/") or "/")
        if st[0] & 0x4000:  # directory
            copytree(src, dst)
            rmtree(src)
        else:
            copyfile(src, dst)
            os.unlink(src)
    except Exception:
        # Clean up partial destination on failure.
        try:
            os.unlink(dst)
        except OSError:
            try:
                rmtree(dst)
            except OSError:
                pass
        raise


def disk_usage(path):
    bit_tuple = os.statvfs(path)
    blksize = bit_tuple[0]  # system block size
    total = bit_tuple[2] * blksize
    free = bit_tuple[3] * blksize
    used = total - free

    return _ntuple_diskusage(total, used, free)
