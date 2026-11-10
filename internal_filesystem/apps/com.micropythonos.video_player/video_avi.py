"""AVI (RIFF) demuxer: MJPEG video, optionally with a PCM or IMA audio stream.

The point of AVI is one file that plays everywhere: VLC opens MJPEG-in-AVI with
LPCM out of the box, and so does this player, so the sample clips no longer
need a separate .wav sidecar to carry sound.

Only what a player needs is parsed: the two stream headers, the frame rate, and
the chunk layout of the `movi` list. Every chunk carries its own size, so
dropping a frame is a seek past one header instead of an SOI scan.

OpenDML files (a second `AVIX` riff with a continued `movi` list, only used
above 1 GB) are read up to the end of their first `movi` list.
"""

WAVE_FORMAT_PCM = 1
WAVE_FORMAT_MS_ADPCM = 0x0002
WAVE_FORMAT_IMA_ADPCM = 0x0011
WAVE_FORMAT_MP3 = 0x0055
WAVE_FORMAT_MPEG = 0x0050

_AUDIO_NAMES = {
    0x0003: "IEEE float",
    0x0006: "A-law",
    0x0007: "mu-law",
    0x0050: "MPEG audio",
    0x0055: "MP3",
    0x00FF: "AAC",
    0x2000: "AC-3",
}

_VIDEO_CODECS = (b"MJPG", b"JPEG")

# How much sound the demuxer may run ahead of the pictures. The audio track
# asks for a lead of ~180ms, so this holds several times that and leaves room
# for a stalled pump without dropping sound.
AUDIO_FEED_BYTES = 96 * 1024
# Frames the demuxer keeps read ahead of the one being presented. The sound
# that goes with them is what the audio track's lead is built from: without a
# lookahead the interleave ties sound to pictures one-to-one, so priming the
# sink would eat the whole queue and every slow frame would starve the sound.
# Six frames keep ~400ms of sound in hand, of which the prime takes 180ms.
LOOKAHEAD_FRAMES = 6


class _Feed:
    """Fixed byte ring: the demuxer writes, the audio track drains."""

    def __init__(self, size):
        self.buf = bytearray(size)
        self.len = 0
        self.pos = 0

    def buffered(self):
        return self.len - self.pos

    def reset(self):
        self.len = 0
        self.pos = 0

    def append(self, data):
        size = len(data)
        if size > len(self.buf) - self.len:
            self._compact()
            if size > len(self.buf) - self.len:
                return 0
        self.buf[self.len:self.len + size] = data
        self.len += size
        return size

    def take(self, dest, offset, count):
        available = self.buffered()
        if count > available:
            count = available
        if count <= 0:
            return 0
        dest[offset:offset + count] = memoryview(self.buf)[self.pos:self.pos + count]
        self.pos += count
        if self.pos >= self.len:
            self.pos = 0
            self.len = 0
        elif self.pos >= len(self.buf) // 2:
            self._compact()
        return count

    def drop(self, count):
        available = self.buffered()
        if count > available:
            count = available
        if count <= 0:
            return 0
        self.pos += count
        if self.pos >= self.len:
            self.pos = 0
            self.len = 0
        return count

    def _compact(self):
        tail = self.len - self.pos
        if tail:
            self.buf[0:tail] = memoryview(self.buf)[self.pos:self.len]
        self.len = tail
        self.pos = 0


class UnsupportedFormat(Exception):
    """A container or codec this player cannot play, with a readable reason."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _u16(buf, at):
    return buf[at] | (buf[at + 1] << 8)


def _u32(buf, at):
    return (buf[at] | (buf[at + 1] << 8) | (buf[at + 2] << 16)
            | (buf[at + 3] << 24))


def _fourcc_name(codec):
    try:
        name = bytes(codec).decode()
    except Exception:
        return "unknown"
    name = name.strip("\x00 ").strip()
    return name or "unknown"


def codec_name(tag):
    """Readable name for a WAVE format tag."""
    return _AUDIO_NAMES.get(tag, "%#06x" % tag)


class AviReader:
    """Demux an AVI file into MJPEG frames plus optional audio.

    ``next()`` returns one video payload as a memoryview into an internal
    buffer, valid until the next call, exactly like ``MjpegReader``.
    ``audio_source()`` returns the matching ``AviAudioSource`` or raises
    ``UnsupportedFormat`` when the audio codec is one this player cannot play.
    """

    def __init__(self, source):
        self._file = open(source, "rb") if isinstance(source, str) else source
        self._path = source if isinstance(source, str) else None
        self._buf = bytearray(0)
        self._pos = 0
        self.frames = 0
        self.sum_frame_bytes = 0
        self.skipped = 0
        self.error = None
        self.width = 0
        self.height = 0
        self.fps = None
        self.frame_count = 0
        self.microsec_per_frame = 0
        self.movi_start = 0
        self.movi_end = 0
        self.video_id = b"00dc"
        self._audio_id = b"01wb"
        self.video_codec = b""
        self.video_found = False
        self.audio = None
        self.feed = None
        self.audio_lost = 0
        self._pending = []
        self._streams = 0
        self._parse()
        self._pos = self.movi_start

    # ----- parsing ------------------------------------------------------

    def _read_at(self, offset, count):
        self._file.seek(offset)
        return self._file.read(count)

    def _parse(self):
        size = self._file.seek(0, 2)
        head = self._read_at(0, 12)
        if len(head) < 12 or head[0:4] != b"RIFF" or head[8:12] != b"AVI ":
            raise UnsupportedFormat(
                "not an AVI file (only AVI with MJPEG video is supported)")
        pos = 12
        while pos + 8 <= size:
            chunk = self._read_at(pos, 12)
            if len(chunk) < 8:
                break
            chunk_id = chunk[0:4]
            chunk_size = _u32(chunk, 4)
            data = pos + 8
            if chunk_id == b"LIST" and len(chunk) >= 12:
                kind = chunk[8:12]
                if kind == b"hdrl":
                    self._parse_hdrl(data + 4, data + chunk_size)
                elif kind == b"movi":
                    self.movi_start = data + 4
                    self.movi_end = data + chunk_size
                    break
            pos = data + chunk_size + (chunk_size & 1)
        if self.audio:
            self._audio_id = self.audio["id"]
        if not self.movi_start or not self.video_found:
            raise UnsupportedFormat(
                "no video stream in this AVI (only MJPEG video is supported)")
        if self.video_codec and self.video_codec.upper() not in _VIDEO_CODECS:
            raise UnsupportedFormat(
                "unsupported video codec: %s (this player plays MJPEG)"
                % _fourcc_name(self.video_codec))
        if not self.fps:
            if self.microsec_per_frame:
                self.fps = 1000000 // self.microsec_per_frame
            else:
                self.fps = 15

    def _parse_hdrl(self, start, end):
        pos = start
        while pos + 8 <= end:
            chunk = self._read_at(pos, 12)
            if len(chunk) < 8:
                return
            chunk_id = chunk[0:4]
            chunk_size = _u32(chunk, 4)
            data = pos + 8
            if chunk_id == b"avih":
                header = self._read_at(data, min(chunk_size, 40))
                if len(header) >= 40:
                    self.microsec_per_frame = _u32(header, 0)
                    self.frame_count = _u32(header, 16)
                    self.width = _u32(header, 32)
                    self.height = _u32(header, 36)
            elif chunk_id == b"LIST" and len(chunk) >= 12:
                if chunk[8:12] == b"strl":
                    self._parse_strl(data + 4, data + chunk_size)
            pos = data + chunk_size + (chunk_size & 1)

    def _parse_strl(self, start, end):
        index = self._streams
        self._streams += 1
        stream_type = None
        scale = 0
        rate = 0
        length = 0
        fmt = b""
        pos = start
        while pos + 8 <= end:
            chunk = self._read_at(pos, 8)
            if len(chunk) < 8:
                break
            chunk_id = chunk[0:4]
            chunk_size = _u32(chunk, 4)
            data = pos + 8
            if chunk_id == b"strh":
                header = self._read_at(data, min(chunk_size, 48))
                if len(header) >= 36:
                    stream_type = header[0:4]
                    scale = _u32(header, 20)
                    rate = _u32(header, 24)
                    length = _u32(header, 32)
            elif chunk_id == b"strf":
                fmt = self._read_at(data, min(chunk_size, 64))
            pos = data + chunk_size + (chunk_size & 1)
        if stream_type == b"vids":
            self.video_found = True
            self.video_id = ("%02d" % index).encode() + b"dc"
            if len(fmt) >= 20:
                self.video_codec = fmt[16:20]
            if scale and rate:
                self.fps = int((rate + scale // 2) // scale)
            if length:
                self.frame_count = length
        elif stream_type == b"auds" and self.audio is None:
            self.audio = self._audio_info(index, fmt, length)

    @staticmethod
    def _audio_info(index, fmt, length):
        info = {
            "id": ("%02d" % index).encode() + b"wb",
            "tag": 0,
            "channels": 1,
            "rate": 0,
            "bits": 16,
            "block_align": 0,
            "samples_per_block": 0,
            "bytes": 0,
        }

        def fill(buf, at):
            if len(buf) < at + 2:
                return 0
            return _u16(buf, at)

        def fill32(buf, at):
            if len(buf) < at + 4:
                return 0
            return _u32(buf, at)

        info["tag"] = fill(fmt, 0)
        info["channels"] = fill(fmt, 2) or 1
        info["rate"] = fill32(fmt, 4)
        info["block_align"] = fill(fmt, 12)
        info["bits"] = fill(fmt, 14)
        extra = fill(fmt, 16)
        if extra >= 2:
            info["samples_per_block"] = fill(fmt, 18)
        if length and info["block_align"]:
            info["bytes"] = length * info["block_align"]
        return info

    # ----- chunk stepping -----------------------------------------------

    def _step(self):
        """Read the next chunk header; return (id, size, data_pos) or None.

        Leaves the cursor after the chunk (header included) and does not touch
        the payload, so the caller decides whether to read it.
        """
        if self._pos >= self.movi_end:
            return None
        self._file.seek(self._pos)
        header = self._file.read(8)
        if len(header) < 8:
            self._pos = self.movi_end
            return None
        chunk_id = header[0:4]
        chunk_size = _u32(header, 4)
        data = self._pos + 8
        self._pos = data + chunk_size + (chunk_size & 1)
        return chunk_id, chunk_size, data

    def _read_audio(self, size, data):
        """Copy an audio chunk into the feed; False when it does not fit."""
        if self.feed is None or size <= 0:
            return True
        feed = self.feed
        if size > len(feed.buf) - feed.len:
            feed._compact()
        if size > len(feed.buf) - feed.len:
            # The pump is behind: drop the queued sound rather than stall the
            # pictures, exactly like the audio track's own resync.
            feed.drop(feed.buffered())
            self.audio_lost += size
            return False
        self._file.seek(data)
        got = self._file.readinto(memoryview(feed.buf)[feed.len:feed.len + size])
        if got != size:
            return False
        feed.len += size
        return True

    def _read_frame(self, size, data):
        buf = self._buf
        if size > len(buf):
            buf = bytearray(size)
            self._buf = buf
        self._file.seek(data)
        got = self._file.readinto(memoryview(buf)[:size])
        if got != size:
            self.error = "short frame read"
            return None
        self.frames += 1
        self.sum_frame_bytes += size
        return memoryview(buf)[:size]

    # ----- video --------------------------------------------------------

    def _advance(self, sound=True):
        """Walk one chunk: queue a frame, or feed its sound. False at the end."""
        chunk = self._step()
        if chunk is None:
            return False
        chunk_id, chunk_size, data = chunk
        if chunk_id == self.video_id and chunk_size > 0:
            self._pending.append((chunk_size, data))
        elif self.feed is not None and chunk_id == self._audio_id and sound:
            self._read_audio(chunk_size, data)
        return True

    def _top_up(self):
        while len(self._pending) < LOOKAHEAD_FRAMES:
            if not self._advance():
                return

    def next(self):
        self._top_up()
        if not self._pending:
            return None
        size, data = self._pending.pop(0)
        return self._read_frame(size, data)

    def skip(self, n, sound=True):
        """Drop n queued or upcoming frames without reading their payloads.

        With sound=True the sound that belongs to them still flows, so a drop
        keeps the pictures and the sound on the same clock. A seek passes
        sound=False: it wants the sound to jump too, not to play what it
        skipped over.
        """
        dropped = 0
        while dropped < n:
            if self._pending:
                self._pending.pop(0)
                dropped += 1
                continue
            if not self._advance(sound):
                break
        self.skipped += dropped
        self._top_up()
        return dropped == n

    def prefill_audio(self, ms):
        """Run the demuxer ahead until it has ``ms`` of sound queued.

        The frames walked on the way stay queued, in order, so nothing is
        skipped; their sound is what the sink is primed with.
        """
        if self.feed is None or not self.audio or not self.audio["rate"]:
            return 0
        want = self.audio["rate"] * self.audio["channels"] * 2 * ms // 1000
        if self.audio["tag"] == WAVE_FORMAT_IMA_ADPCM:
            per_block = self._ima_per_block()
            if per_block:
                want = (want + per_block - 1) // per_block * self._ima_payload()
        while self.feed.buffered() < want:
            if not self._advance():
                break
        return self.feed.buffered()

    def _ima_payload(self):
        return self.audio["block_align"] if self.audio else 0

    def _ima_per_block(self):
        if not self.audio:
            return 0
        channels = self.audio["channels"]
        samples = self.audio["samples_per_block"]
        if not samples:
            samples = 1 + (self.audio["block_align"] - 4 * channels) * 2 // channels
        return samples * 2 * channels

    def at_end(self):
        return self._pos >= self.movi_end and not self._pending

    def audio_at_end(self):
        """True when the demuxer has walked the file and the feed is drained."""
        return self._pos >= self.movi_end and self.feed is not None and self.feed.buffered() == 0

    def rewind(self):
        self._pos = self.movi_start
        self._pending = []
        if self.feed is not None:
            self.feed.reset()
        return True

    def close(self):
        try:
            self._file.close()
        except Exception:
            pass

    # ----- audio --------------------------------------------------------

    def audio_source(self):
        if self.audio is None:
            return None
        source = AviAudioSource(self, self.audio)
        self.feed = _Feed(AUDIO_FEED_BYTES)
        self.audio_lost = 0
        return source


class AviAudioSource:
    """Decoded PCM from the audio stream the demuxer is carrying.

    Presents the same surface as ``WavSource``: ``read_into`` fills a buffer
    with 16-bit PCM, so the player's audio track does not care where the sound
    came from. The bytes arrive as a side effect of reading the pictures: the
    demuxer walks the interleaved chunks in order, so the sound costs no seek
    and no second pass over the file.
    """

    def __init__(self, reader, info):
        tag = info["tag"]
        if tag == WAVE_FORMAT_PCM:
            if info["bits"] not in (8, 16):
                raise UnsupportedFormat(
                    "unsupported audio: %d-bit PCM (this player plays 8/16-bit "
                    "or IMA ADPCM)" % info["bits"])
            self.format_name = "pcm16" if info["bits"] == 16 else "pcm8"
            self._ima = False
        elif tag == WAVE_FORMAT_IMA_ADPCM:
            if info["block_align"] <= 0 or info["channels"] < 1:
                raise UnsupportedFormat(
                    "unsupported audio: broken IMA ADPCM header")
            self.format_name = "ima"
            self._ima = True
        else:
            raise UnsupportedFormat(
                "unsupported audio codec: %s (this player plays 8/16-bit PCM "
                "or IMA ADPCM)" % codec_name(tag))
        if not info["rate"]:
            raise UnsupportedFormat("unsupported audio: no sample rate in the AVI")
        self._reader = reader
        self._bits = info["bits"]
        self.channels = info["channels"]
        self.playback_rate = info["rate"]
        self.upsample = 1
        self.byte_rate = self.playback_rate * self.channels * 2
        self._block_align = info["block_align"]
        self._samples_per_block = info["samples_per_block"]
        if self._ima and not self._samples_per_block:
            self._samples_per_block = 1 + (self._block_align - 4 * self.channels) * 2 // self.channels
        self._block = bytearray(self._block_align) if self._ima else None
        self._widen = bytearray(1024) if (not self._ima and self._bits == 8) else None
        total = info["bytes"]
        self.total_frames = total // (self.channels * 2) if total else 0

    # The audio track asks for this interface.
    @property
    def in_memory(self):
        return False

    @property
    def remaining_bytes(self):
        return 0 if self.exhausted else 1 << 30

    @property
    def exhausted(self):
        return self._reader.audio_at_end()

    def preload(self):
        return False

    def read_into(self, dest, offset, max_bytes):
        if max_bytes <= 0:
            return 0
        feed = self._reader.feed
        if not self._ima:
            if self._bits == 16:
                return feed.take(dest, offset, max_bytes)
            return self._take_pcm8(dest, offset, max_bytes)
        from mpos.audio.adpcm_ima import decode_block_into

        per_block = self._samples_per_block * 2 * self.channels
        if per_block <= 0:
            return 0
        written = 0
        while max_bytes - written >= per_block:
            if not self._fill_block():
                break
            decode_block_into(memoryview(self._block), self.channels,
                              self._block_align, dest, offset + written)
            written += per_block
        return written

    def _take_pcm8(self, dest, offset, max_bytes):
        """Widen unsigned 8-bit samples to signed 16-bit, centred on zero."""
        feed = self._reader.feed
        scratch = self._widen
        out = offset
        written = 0
        while max_bytes - written >= 2:
            count = len(scratch)
            if count > (max_bytes - written) // 2:
                count = (max_bytes - written) // 2
            got = feed.take(scratch, 0, count)
            if got <= 0:
                break
            for i in range(got):
                sample = (scratch[i] - 128) << 8
                dest[out] = sample & 0xFF
                dest[out + 1] = (sample >> 8) & 0xFF
                out += 2
            written += got * 2
        return written

    def _fill_block(self):
        feed = self._reader.feed
        need = self._block_align
        got = 0
        while got < need:
            if feed.buffered() <= 0:
                return False
            take = feed.buffered()
            if take > need - got:
                take = need - got
            got += feed.take(self._block, got, take)
        return True

    def skip_bytes(self, n):
        """Drop n bytes of decoded PCM; return how many were dropped.

        A skip only has to move the feed's read cursor: the demuxer keeps
        pulling the same bytes off the card either way, so nothing is re-read.
        """
        if n <= 0:
            return 0
        feed = self._reader.feed
        if self._ima:
            per_block = self._samples_per_block * 2 * self.channels
            if per_block <= 0 or not self._block_align:
                return 0
            blocks = n // per_block
            dropped = feed.drop(blocks * self._block_align)
            return (dropped // self._block_align) * per_block
        if self._bits == 8:
            return feed.drop(n // 2) * 2
        return feed.drop(n)

    def close(self):
        pass
