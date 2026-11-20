"""MJPEG frame reader and frame pacer for the video player.

Deliberately free of LVGL imports so it can be unit tested on desktop and
reused by other players. See docs/apps/video-performance.md for the cost model
these choices come from.
"""

import time

try:
    _ticks_diff = time.ticks_diff
except AttributeError:  # CPython, for desktop-side tooling only
    def _ticks_diff(a, b):
        return a - b

SOI = b"\xff\xd8"
EOI = b"\xff\xd9"

_SOF_MARKERS = (0xC0, 0xC1, 0xC2, 0xC3)

# A seek costs about 15ms on this SD card, and the read that finds the next
# SOI after it pulls in about one frame, so dropping a single frame is cheaper
# to read than to seek.
MIN_SEEK_FRAMES = 2


class MemoryFile:
    """Read-only file object over a clip held in RAM.

    The demuxers do seek/read/readinto, so a clip that fits in PSRAM is read
    once and then played from memory: the SD card is out of the per-frame path
    and a loop or a seek costs nothing. ``read`` returns bytes (a small copy)
    because the demuxer compares chunk ids against literals; the hot paths use
    ``readinto`` and copy nothing.
    """

    def __init__(self, data):
        self._data = data
        self._pos = 0
        self._size = len(data)

    def seek(self, offset, whence=0):
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        else:
            self._pos = self._size + offset
        if self._pos < 0:
            self._pos = 0
        elif self._pos > self._size:
            self._pos = self._size
        return self._pos

    def tell(self):
        return self._pos

    def read(self, count=-1):
        if count is None or count < 0:
            count = self._size - self._pos
        end = self._pos + count
        if end > self._size:
            end = self._size
        chunk = bytes(memoryview(self._data)[self._pos:end])
        self._pos = end
        return chunk

    def readinto(self, target):
        want = len(target)
        end = self._pos + want
        if end > self._size:
            end = self._size
        count = end - self._pos
        if count <= 0:
            return 0
        target[0:count] = memoryview(self._data)[self._pos:end]
        self._pos = end
        return count

    def close(self):
        pass


class MjpegReader:
    """Split a raw MJPEG stream into complete JPEG frames.

    Slides a small buffer over the file and returns a memoryview into it, so
    reading a frame does not copy it. The view stays valid until the next
    call to next().
    """

    def __init__(self, source, chunk=32768, cap=65536):
        if isinstance(source, str):
            self._file = open(source, "rb")
        else:
            self._file = source
        self._buf = bytearray(cap)
        self._chunk = chunk
        self._len = 0
        self._pos = 0
        self._eof = False
        self._chunk_next = 0
        self.bytes_read = 0
        self.frames = 0
        self.sum_frame_bytes = 0
        self.skipped = 0
        self.error = None
        self._seekable = True
        self._size = 0
        try:
            position = self._file.tell()
            self._size = self._file.seek(0, 2)
            self._file.seek(position)
        except OSError:
            self._seekable = False

    def _fill(self):
        # Compact first so the free space is contiguous at the end.
        if self._pos:
            remaining = self._len - self._pos
            if remaining:
                self._buf[0:remaining] = self._buf[self._pos:self._len]
            self._len = remaining
            self._pos = 0
        if self._eof:
            return False
        room = len(self._buf) - self._len
        if room <= 0:
            return False
        want = self._chunk_next or self._chunk
        self._chunk_next = 0
        if want > room:
            want = room
        n = self._file.readinto(memoryview(self._buf)[self._len:self._len + want])
        if not n:
            self._eof = True
            return False
        self._len += n
        self.bytes_read += n
        return True

    def next(self):
        while True:
            start = self._buf.find(SOI, self._pos, self._len)
            if start < 0:
                # Keep the final byte: it may be the 0xff of a split SOI.
                self._pos = self._len - 1 if self._len else 0
                if not self._fill():
                    return None
                continue
            end = self._buf.find(EOI, start + 2, self._len)
            if end < 0:
                if start == 0 and self._len >= len(self._buf):
                    # A single frame larger than the buffer: drop this SOI and
                    # resync on the next one.
                    self.error = "frame exceeds buffer"
                    self._pos = 2
                    continue
                self._pos = start
                if not self._fill():
                    return None
                continue
            self._pos = end + 2
            self.frames += 1
            self.sum_frame_bytes += end + 2 - start
            return memoryview(self._buf)[start:end + 2]

    def skip(self, n):
        """Advance past the next n frames without reading their bytes.

        Reading a dropped frame costs its bytes at SD speed. On a 320x240 30fps
        stream every frame is 23KB and the card delivers about 550KB/s, so
        reading the frames that are dropped instead of presenting them is the
        whole budget (see docs/apps/video-performance.md).

        The seek is only worth it once it avoids more bytes than the resync
        read costs, which is why n has a floor.

        Returns True when the skip happened, False when the caller has to read
        and discard instead.
        """
        if (not self._seekable or n < MIN_SEEK_FRAMES or not self.frames
                or self._size <= 0):
            return False
        average = self.sum_frame_bytes // self.frames
        if average <= 0:
            return False
        stream_pos = self._file.tell() - (self._len - self._pos)
        target = stream_pos + n * average
        if target >= self._size:
            target = self._size - 1
        if target <= stream_pos:
            return False
        try:
            self._file.seek(target)
        except OSError:
            self._seekable = False
            return False
        self._len = 0
        self._pos = 0
        self._eof = False
        self.skipped += n
        # Find the next SOI with one frame worth of read instead of a full
        # chunk, which would pull in frames nobody asked for.
        self._chunk_next = average
        return True

    def rewind(self):
        try:
            self._file.seek(0)
        except OSError:
            return False
        self._len = 0
        self._pos = 0
        self._eof = False
        return True

    def close(self):
        try:
            self._file.close()
        except Exception:
            pass


_SIGNATURES = (
    (b"ftyp", 4, "an MP4/MOV file"),
    (b"\x1aE\xdf\xa3", 0, "a Matroska/WebM file"),
    (b"OggS", 0, "an Ogg file"),
    (b"FLV\x01", 0, "a Flash video file"),
    (b"GIF8", 0, "a GIF image"),
    (b"RIFF", 0, "a RIFF file (AVI or WAV)"),
    (b"\xff\xd8", 0, "a JPEG image or MJPEG stream"),
)


def sniff_format(source, size=16):
    """Name the container from its first bytes, for a readable error.

    "no frames in foo.mjpeg" is true but useless when the file is really an
    MP4 with the wrong extension. Returns a printable description or None.
    """
    try:
        if isinstance(source, str):
            handle = open(source, "rb")
            try:
                head = handle.read(size)
            finally:
                handle.close()
        else:
            # Sniff the start of the stream, then put the cursor back where it
            # was: the caller may already be positioned for its own parsing.
            try:
                position = source.tell()
                source.seek(0)
            except (OSError, AttributeError):
                position = None
            head = source.read(size)
            if position is not None:
                try:
                    source.seek(position)
                except OSError:
                    pass
    except OSError:
        return None
    if not head:
        return None
    for signature, offset, name in _SIGNATURES:
        at = offset
        if len(head) >= at + len(signature) and head[at:at + len(signature)] == signature:
            return name
    if head[0:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "an MP3 stream"
    return None


def jpeg_dimensions(frame):
    """Return (width, height) from a JPEG's start-of-frame marker, or (None, None)."""
    i = 2
    n = len(frame)
    while i + 9 < n:
        if frame[i] != 0xFF:
            i += 1
            continue
        marker = frame[i + 1]
        if marker in _SOF_MARKERS:
            height = (frame[i + 5] << 8) | frame[i + 6]
            width = (frame[i + 7] << 8) | frame[i + 8]
            return width, height
        if marker == 0xD8 or marker == 0xD9 or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if i + 3 >= n:
            break
        segment = (frame[i + 2] << 8) | frame[i + 3]
        i += 2 + segment
    return None, None


def fps_from_name(path):
    """Get the frame rate from a name like ruler_320x240_15fps.mjpeg.

    MJPEG has no container, so the rate is not in the stream. The naming
    convention is the only source; callers can also pass an explicit "fps".
    """
    name = path.rsplit("/", 1)[-1].lower()
    end = name.find("fps")
    if end <= 0:
        return None
    start = end
    while start > 0 and name[start - 1].isdigit():
        start -= 1
    if start == end:
        return None
    try:
        value = int(name[start:end])
    except ValueError:
        return None
    return value if 1 <= value <= 120 else None


class Pacer:
    """Frame clock for playback.

    Frames are due at start + n * 1000 / fps. When a frame is shown late, the
    pacer reports how many whole intervals were missed so the player can drop
    them and keep wall-clock time.
    """

    def __init__(self, fps, now_ms, drop=True):
        self.fps = fps if fps and fps > 0 else 15
        self.start_ms = now_ms
        self.frame = 0
        self.drop = drop

    def due_ms(self):
        return self.start_ms + self.frame * 1000 // self.fps

    def wait_ms(self, now_ms):
        return _ticks_diff(self.due_ms(), now_ms)

    def mark_shown(self, now_ms):
        """Advance past the frame just presented; return how many to skip."""
        self.frame += 1
        if not self.drop:
            return 0
        late = _ticks_diff(now_ms, self.due_ms())
        if late <= 0:
            return 0
        skip = late * self.fps // 1000
        self.frame += skip
        return skip

    def reset(self, now_ms):
        self.start_ms = now_ms
        self.frame = 0
