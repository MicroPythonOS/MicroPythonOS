"""WAV sidecar audio for the video player.

MJPEG has no room for sound, so the player looks for a WAV file next to the
clip (``clip.mjpeg`` -> ``clip.wav``) and streams it against the same wall
clock the frames are paced with. That keeps sound and pictures together
without a second thread: ``AudioManager.player()`` runs a reader thread of its
own, and on this board the SD card is the bottleneck already, so two readers
would take turns costing each other frames.

The pump tops the sink up a fixed number of milliseconds ahead of the video
clock. If the pump stalls for longer than that, audio is skipped forward
instead of drifting: the pictures are the reference, same as dropped frames.

Import-light on purpose (no LVGL, no ``mpos`` at import time) so the parsing
and pacing rules can be unit tested on desktop. See
docs/apps/video-performance.md for the budget these choices come from.
"""

import time

try:
    _ticks_ms = time.ticks_ms
    _ticks_us = time.ticks_us
    _ticks_diff = time.ticks_diff
except AttributeError:  # CPython, for desktop-side tooling only
    def _ticks_ms():
        return int(time.monotonic() * 1000)

    def _ticks_us():
        return int(time.monotonic() * 1000000)

    def _ticks_diff(a, b):
        return a - b


WAVE_FORMAT_PCM = 0x0001
WAVE_FORMAT_IMA_ADPCM = 0x0011
WAVE_FORMAT_EXTENSIBLE = 0xFFFE

# How far ahead of the video clock the sink is kept fed. One frame of picture
# work is 70ms at 320x240 and cannot be interrupted, and on a slow frame the
# pump does not get back to the sound for over 100ms, so the lead has to cover
# a whole frame period plus scheduler jitter. Measured: at 120ms the queue
# still went dry between frames and every underrun was paid for by skipping
# sound forward, and at 250ms a top-up no longer fits the DMA ring in one
# write, which costs the wall time back. 180ms of lead against a 120ms floor
# keeps between two and three frames of sound queued.
AUDIO_LEAD_MS = 180
# Refill whenever the queue drops below this. The ring therefore holds between
# LOW and LEAD ms of sound, and a refill never asks for more than
# LEAD-LOW ms, which is what keeps the write landing in free space instead of
# blocking until the sink has played it.
AUDIO_LOW_MS = 120
# Most source bytes decoded per pump pass, so a refill is spread over ticks
# instead of landing inside one frame's budget.
AUDIO_READ_BYTES = 8192
# A sidecar this small is read into RAM before the first frame: on this board
# one 4KB SD read costs about 10ms, so pulling 44KB/s of PCM a frame at a time
# takes the frame budget below real time (measured 10.9fps at 320x240). In RAM
# the sound costs only the decode and the I2S write.
AUDIO_PRELOAD_BYTES = 512 * 1024
# Bigger sidecars stream through a read-ahead buffer, refilled in one large
# read per ~700ms rather than a small one per frame (same bytes, a third of the
# per-call overhead).
AUDIO_QUEUE_BYTES = 32768
AUDIO_QUEUE_LOW = 8192


def _u16(buf, off=0):
    return buf[off] | (buf[off + 1] << 8)


def _u32(buf, off=0):
    return buf[off] | (buf[off + 1] << 8) | (buf[off + 2] << 16) | (buf[off + 3] << 24)


def _next_pow2(n):
    value = 1024
    while value < n:
        value <<= 1
    return value


def sidecar_path(path, extensions=(".wav", ".WAV")):
    """Return the first audio sidecar that exists next to a video, or None."""
    import os

    name = path.rsplit("/", 1)[-1]
    dot = name.rfind(".")
    base = path[: len(path) - len(name) + dot] if dot > 0 else path
    for ext in extensions:
        candidate = base + ext
        try:
            os.stat(candidate)
        except OSError:
            continue
        return candidate
    return None


def playback_rate(original_rate, preferred_rate=None):
    """Return (sink_rate, upsample_factor).

    Boards with a fixed codec rate ask for one through the output descriptor;
    the player repeats samples rather than resampling, which is what the WAV
    stream in mpos.audio does and costs nothing measurable at these rates.
    """
    if original_rate <= 0:
        return original_rate, 1
    if preferred_rate and preferred_rate > original_rate:
        factor = (preferred_rate + original_rate - 1) // original_rate
        return original_rate * factor, factor
    if original_rate < 8000:
        factor = (8000 + original_rate - 1) // original_rate
        return original_rate * factor, factor
    return original_rate, 1


def _upsample(data, factor):
    """Repeat every 16-bit sample ``factor`` times."""
    if factor <= 1:
        return data
    out = bytearray()
    for i in range(0, len(data), 2):
        sample = data[i:i + 2]
        for _ in range(factor):
            out.extend(sample)
    return out


def _to_s16(raw, bits):
    """Convert 8/16/24/32-bit PCM to 16-bit little endian."""
    if bits == 16:
        return raw
    if bits == 8:
        out = bytearray(len(raw) * 2)
        for i in range(len(raw)):
            value = (raw[i] - 128) << 8
            out[i * 2] = value & 0xFF
            out[i * 2 + 1] = (value >> 8) & 0xFF
        return out
    if bits == 24:
        samples = len(raw) // 3
        out = bytearray(samples * 2)
        j = 0
        for i in range(samples):
            out[i * 2] = raw[j + 1]
            out[i * 2 + 1] = raw[j + 2]
            j += 3
        return out
    if bits == 32:
        samples = len(raw) // 4
        out = bytearray(samples * 2)
        j = 0
        for i in range(samples):
            out[i * 2] = raw[j + 2]
            out[i * 2 + 1] = raw[j + 3]
            j += 4
        return out
    raise ValueError("unsupported bit depth: %s" % bits)


class WavSource:
    """Sequential 16-bit PCM reader over a WAV sidecar.

    Supports PCM (8/16/24/32-bit, mono or stereo) and IMA ADPCM, which are the
    formats the test pairs and ClipTV's sidecars use. Anything else (MS ADPCM,
    MP3) is rejected by the header parse and the player plays on silently.
    """

    def __init__(self, source, preferred_rate=None, preload_bytes=AUDIO_PRELOAD_BYTES):
        if isinstance(source, str):
            self._file = open(source, "rb")
            self.path = source
        else:
            self._file = source
            self.path = getattr(source, "name", "")
        self._format_tag = 0
        self._channels = 0
        self._bits = 0
        self._block_align = 0
        self._data_start = 0
        self._data_size = 0
        self._consumed = 0
        self._samples_per_block = 0
        self._mem = None
        self._mv = None
        self._mem_pos = 0
        self._ima_scratch = None
        self.rate = 0
        self.total_frames = 0
        self._parse()
        self.playback_rate, self.upsample = playback_rate(self.rate, preferred_rate)
        self.byte_rate = self.playback_rate * self._channels * 2
        self.duration_ms = self.total_frames * 1000 // self.rate if self.rate else 0
        self.preload_bytes = preload_bytes

    def preload(self):
        """Read the whole sidecar into RAM if it is small enough."""
        if self.preload_bytes and self._data_size <= self.preload_bytes and self._mem is None:
            return self._preload()
        return False

    def _preload(self):
        """Read the whole data chunk into RAM and release the file."""
        data = self._file.read(self._data_size)
        if not data or len(data) != self._data_size:
            return False
        self._mem = data
        self._mv = memoryview(data)
        self._mem_pos = 0
        try:
            self._file.close()
        except Exception:
            pass
        self._file = None
        return True

    @property
    def in_memory(self):
        return self._mem is not None

    def _read_raw(self, n):
        if self._mem is not None:
            start = self._mem_pos
            end = start + n
            if end > len(self._mem):
                end = len(self._mem)
            if end <= start:
                return b""
            self._mem_pos = end
            return self._mem[start:end]
        return self._file.read(n)

    def _read_raw_into(self, dest, offset, n):
        """Copy up to n source bytes to dest[offset:]; return the count."""
        if self._mem is not None:
            start = self._mem_pos
            end = start + n
            if end > len(self._mem):
                end = len(self._mem)
            if end <= start:
                return 0
            dest[offset:offset + (end - start)] = self._mv[start:end]
            self._mem_pos = end
            return end - start
        raw = self._file.read(n)
        if not raw:
            return 0
        dest[offset:offset + len(raw)] = raw
        return len(raw)

    def _seek_raw(self, offset):
        if self._mem is not None:
            self._mem_pos = offset
            return True
        try:
            self._file.seek(self._data_start + offset)
        except OSError:
            return False
        return True

    # ----- header -------------------------------------------------------

    def _parse(self):
        f = self._file
        f.seek(0)
        head = f.read(12)
        if len(head) < 12 or head[0:4] != b"RIFF" or head[8:12] != b"WAVE":
            raise ValueError("not a WAV file")
        sample_rate = 0
        channels = 0
        bits = 0
        tag = 0
        block_align = 0
        fact_frames = 0
        data_start = -1
        data_size = 0
        pos = 12
        while True:
            f.seek(pos)
            chunk = f.read(8)
            if len(chunk) < 8:
                break
            chunk_id = chunk[0:4]
            chunk_size = _u32(chunk, 4)
            if chunk_id == b"fmt ":
                fmt = f.read(chunk_size)
                if len(fmt) < 16:
                    raise ValueError("short fmt chunk")
                tag = _u16(fmt, 0)
                channels = _u16(fmt, 2)
                sample_rate = _u32(fmt, 4)
                block_align = _u16(fmt, 12)
                bits = _u16(fmt, 14)
                if tag == WAVE_FORMAT_EXTENSIBLE and len(fmt) >= 26:
                    tag = _u16(fmt, 24)
            elif chunk_id == b"fact":
                if chunk_size >= 4:
                    fact_frames = _u32(f.read(4), 0)
            elif chunk_id == b"data":
                data_start = pos + 8
                data_size = chunk_size
            pos += 8 + chunk_size + (chunk_size & 1)
        if data_start < 0:
            raise ValueError("no data chunk")
        if tag not in (WAVE_FORMAT_PCM, WAVE_FORMAT_IMA_ADPCM):
            raise ValueError("unsupported WAV format tag 0x%04x" % tag)
        if channels not in (1, 2):
            raise ValueError("unsupported channel count: %s" % channels)
        if data_size <= 0:
            data_size = self._size() - data_start
        if tag == WAVE_FORMAT_PCM and bits not in (8, 16, 24, 32):
            raise ValueError("unsupported bit depth: %s" % bits)
        if tag == WAVE_FORMAT_IMA_ADPCM:
            if bits not in (4, 16) or block_align <= 0:
                raise ValueError("unsupported IMA ADPCM block")
            self._samples_per_block = 1 + (block_align - 4 * channels) * 2 // channels
            total = (data_size // block_align) * self._samples_per_block
        else:
            frame_bytes = channels * bits // 8
            total = data_size // frame_bytes
        if fact_frames:
            total = fact_frames
        self._format_tag = tag
        self._channels = channels
        self._bits = bits
        self._block_align = block_align
        self._data_start = data_start
        self._data_size = data_size
        self.rate = sample_rate
        self.total_frames = total
        f.seek(data_start)

    def _size(self):
        f = self._file
        position = f.tell()
        end = f.seek(0, 2)
        f.seek(position)
        return end

    # ----- reading ------------------------------------------------------

    @property
    def channels(self):
        return self._channels

    @property
    def format_name(self):
        if self._format_tag == WAVE_FORMAT_IMA_ADPCM:
            return "ima"
        return "pcm%d" % self._bits

    @property
    def remaining_bytes(self):
        return self._data_size - self._consumed

    @property
    def exhausted(self):
        return self.remaining_bytes <= 0

    def read_into(self, dest, offset, max_bytes):
        """Decode up to max_bytes of 16-bit PCM into dest[offset:].

        Returns how many bytes were written; 0 means the stream is over. The
        track feeds this straight into its playback buffer so a refill costs a
        copy rather than a fresh allocation on the PSRAM heap.
        """
        if max_bytes <= 0:
            return 0
        if self._format_tag == WAVE_FORMAT_IMA_ADPCM:
            return self._read_ima_into(dest, offset, max_bytes)
        return self._read_pcm_into(dest, offset, max_bytes)

    def read_pcm(self, max_bytes):
        """Return up to ``max_bytes`` of 16-bit PCM, or None at the end."""
        if max_bytes <= 0:
            return None
        if self._format_tag == WAVE_FORMAT_IMA_ADPCM:
            return self._read_ima(max_bytes)
        frame_bytes = self._channels * self._bits // 8
        want = max_bytes - max_bytes % frame_bytes
        remaining = self.remaining_bytes
        if want > remaining:
            want = remaining - remaining % frame_bytes
        if want <= 0:
            return None
        raw = self._read_raw(want)
        if not raw:
            return None
        self._consumed += len(raw)
        data = _to_s16(raw, self._bits)
        if self.upsample > 1:
            data = _upsample(data, self.upsample)
        return data

    def _read_pcm_into(self, dest, offset, max_bytes):
        frame_bytes = self._channels * self._bits // 8
        want = max_bytes - max_bytes % frame_bytes
        remaining = self.remaining_bytes
        if want > remaining:
            want = remaining - remaining % frame_bytes
        if want <= 0:
            return 0
        if self._bits == 16 and self.upsample == 1:
            n = self._read_raw_into(dest, offset, want)
            self._consumed += n
            return n
        raw = self._read_raw(want)
        if not raw:
            return 0
        self._consumed += len(raw)
        data = _to_s16(raw, self._bits)
        if self.upsample > 1:
            data = _upsample(data, self.upsample)
        n = len(data)
        if n > max_bytes:
            n = max_bytes - max_bytes % (2 * self._channels)
        dest[offset:offset + n] = data[0:n]
        return n

    def _read_ima_into(self, dest, offset, max_bytes):
        from mpos.audio.adpcm_ima import decode_block_into

        block = self._block_align
        per_block = self._samples_per_block * 2 * self._channels
        blocks = max_bytes // per_block
        if blocks <= 0:
            return 0
        remaining = self.remaining_bytes
        if remaining <= 0:
            return 0
        full = remaining // block
        partial = remaining % block
        if blocks > full:
            blocks = full
        written = 0
        if blocks:
            need = blocks * block
            scratch = self._ima_scratch
            if scratch is None or len(scratch) < need:
                scratch = bytearray(need)
                self._ima_scratch = scratch
            got = self._read_raw_into(scratch, 0, need)
            self._consumed += got
            view = memoryview(scratch)
            done = got // block
            for i in range(done):
                decode_block_into(view[i * block:(i + 1) * block], self._channels,
                                  block, dest, offset + i * per_block)
            written = done * per_block
        if partial and blocks >= full:
            # Final short block: pad with zero nibbles (the predictor holds),
            # so the tail is ~90ms of held sample rather than dropped.
            tail = self._read_raw(partial)
            if tail:
                self._consumed += len(tail)
                padded = bytearray(block)
                padded[0:len(tail)] = tail
                decode_block_into(padded, self._channels, block, dest,
                                  offset + written)
                written += per_block
        return written

    def _read_ima(self, max_bytes):
        from mpos.audio.adpcm_ima import decode_block_into

        block = self._block_align
        per_block = self._samples_per_block * 2 * self._channels
        blocks = max_bytes // per_block
        if blocks <= 0:
            blocks = 1
        remaining = self.remaining_bytes
        if remaining <= 0:
            return None
        full = remaining // block
        partial = remaining % block
        if blocks > full:
            blocks = full
        want = blocks + (1 if partial else 0)
        out = bytearray(want * per_block)
        view = memoryview(self._read_raw(blocks * block)) if blocks else b""
        if blocks:
            if not view:
                return None
            self._consumed += len(view)
        for i in range(blocks):
            decode_block_into(view[i * block:(i + 1) * block], self._channels,
                              block, out, i * per_block)
        if partial:
            # Final short block: pad with zero nibbles (the predictor holds),
            # so the tail is ~90ms of held sample rather than dropped.
            tail = self._read_raw(partial)
            if tail:
                self._consumed += len(tail)
                padded = bytearray(block)
                padded[0:len(tail)] = tail
                decode_block_into(padded, self._channels, block, out,
                                  blocks * per_block)
            else:
                out = out[0:blocks * per_block]
        if self.upsample > 1:
            out = _upsample(out, self.upsample)
        return out

    def skip_bytes(self, n):
        """Drop ``n`` bytes of decoded PCM; return how many were dropped."""
        if n <= 0:
            return 0
        if self._format_tag == WAVE_FORMAT_IMA_ADPCM:
            block = self._block_align
            per_block = self._samples_per_block * 2 * self._channels
            blocks = n // per_block
            if blocks <= 0:
                return 0
            target = self._consumed + blocks * block
            if target > self._data_size:
                target = self._data_size
            dropped = ((target - self._consumed) // block) * per_block
            source_bytes = ((target - self._consumed) // block) * block
        else:
            frame_bytes = self._channels * self._bits // 8
            frames = n // (self._channels * 2)
            if frames <= 0:
                return 0
            source_bytes = frames * frame_bytes
            if source_bytes > self.remaining_bytes:
                source_bytes = self.remaining_bytes
                frames = source_bytes // frame_bytes
                source_bytes = frames * frame_bytes
            dropped = frames * self._channels * 2
        if source_bytes <= 0:
            return 0
        if not self._seek_raw(self._consumed + source_bytes):
            return 0
        self._consumed += source_bytes
        return dropped

    def rewind(self):
        if not self._seek_raw(0):
            return False
        self._consumed = 0
        return True

    def close(self):
        if self._file is None:
            self._mem = None
            return
        try:
            self._file.close()
        except Exception:
            pass
        self._mem = None


class AudioClock:
    """Byte budget that keeps the sink a fixed number of ms ahead of the video.

    Treats the audio stream as a queue drained at exactly ``byte_rate`` from
    the moment it started, which is what the I2S peripheral does. Comparing
    that against the bytes handed to the sink tells the player when to refill
    and when the sound has fallen behind the pictures.
    """

    def __init__(self, byte_rate, lead_ms=AUDIO_LEAD_MS, low_ms=AUDIO_LOW_MS,
                 frame_bytes=2):
        self.byte_rate = byte_rate
        self.lead_ms = lead_ms
        self.low_ms = low_ms
        # Every byte count here is rounded down to a whole sample frame. A
        # queue that starts mid-frame plays left and right swapped, and an odd
        # byte count is what once wedged the refill on its last free byte.
        self.frame_bytes = frame_bytes
        self.start_ms = 0
        self.written = 0

    def start(self, now_ms):
        self.start_ms = now_ms
        self.written = 0

    def due_bytes(self, now_ms):
        elapsed = _ticks_diff(now_ms, self.start_ms)
        if elapsed < 0:
            elapsed = 0
        played = elapsed * self.byte_rate // 1000
        return played - played % self.frame_bytes

    def pending_bytes(self, now_ms):
        return self.written - self.due_bytes(now_ms)

    def pending_ms(self, now_ms):
        if self.byte_rate <= 0:
            return 0
        return self.pending_bytes(now_ms) * 1000 // self.byte_rate

    def lead_bytes(self):
        size = self.lead_ms * self.byte_rate // 1000
        return size - size % self.frame_bytes

    def low_bytes(self):
        size = self.low_ms * self.byte_rate // 1000
        return size - size % self.frame_bytes

    def to_write(self, now_ms, max_bytes):
        """How many bytes to hand the sink now (0 while the queue is deep)."""
        pending = self.pending_bytes(now_ms)
        if pending >= self.low_bytes():
            return 0
        want = self.lead_bytes() - pending
        if want > max_bytes:
            want = max_bytes
        return want - want % self.frame_bytes

    def late_bytes(self, now_ms):
        """Bytes the stream is behind the video clock (0 when on time)."""
        behind = self.due_bytes(now_ms) - self.written
        if behind <= 0:
            return 0
        return behind - behind % self.frame_bytes

    def note(self, n):
        self.written += n


class NullSink:
    """Sink for desktop: the clock and the pacing run, nothing is audible."""

    def __init__(self):
        self.written = 0

    def open(self):
        pass

    def wait_ready(self):
        pass

    def write(self, data):
        self.written += len(data)
        return len(data)

    def close(self):
        pass


class I2SSink:
    """I2S TX wired to an ``AudioManager.Output`` descriptor.

    Mirrors what ``mpos.audio.stream_wav.WAVStream`` does before its write
    loop (MCLK PWM -> on_open -> machine.I2S), without the chunking and thread
    that belong to a standalone music player.
    """

    def __init__(self, output, rate, channels, lead_ms=AUDIO_LEAD_MS):
        self.output = output
        self.rate = rate
        self.channels = channels
        self.ibuf = _next_pow2((lead_ms + 50) * rate * channels * 2 // 1000)
        if self.ibuf < 8192:
            self.ibuf = 8192
        self._i2s = None
        self._mck = None
        self.written = 0
        self.opened_ms = 0
        # A new channel queues a full ring of silence, and a write only lands
        # as that silence plays out. Until it has drained, a prime costs its
        # own length in wall time (137ms measured for a 120ms lead) and puts
        # the sound ahead of the picture by exactly that much.
        self.preroll_ms = (self.ibuf * 1000 + rate * channels * 2 - 1) // (rate * channels * 2)

    def open(self):
        import machine

        pins = self.output.i2s_pins
        if pins.get("mck") is not None:
            from machine import PWM, Pin

            self._mck = PWM(Pin(pins["mck"], Pin.OUT))
            self._mck.freq(self.rate * 256)
            self._mck.duty_u16(32768)
        on_open = getattr(self.output, "on_open", None)
        if on_open:
            try:
                on_open()
            except Exception:
                pass
        fmt = machine.I2S.MONO if self.channels == 1 else machine.I2S.STEREO
        kwargs = {"mode": machine.I2S.TX, "bits": 16, "format": fmt,
                  "rate": self.rate, "ibuf": self.ibuf}
        if pins.get("sck") is not None:
            kwargs["sck"] = machine.Pin(pins["sck"], machine.Pin.OUT)
        kwargs["ws"] = machine.Pin(pins["ws"], machine.Pin.OUT)
        kwargs["sd"] = machine.Pin(pins["sd"], machine.Pin.OUT)
        self._i2s = machine.I2S(0, **kwargs)
        self.opened_ms = _ticks_ms()

    def wait_ready(self):
        if self._i2s is None:
            return
        wait = self.preroll_ms - _ticks_diff(_ticks_ms(), self.opened_ms)
        if wait > 0:
            time.sleep_ms(wait)

    def write(self, data):
        written = self._i2s.write(data)
        if written is None:
            written = len(data)
        self.written += written
        return written

    def close(self):
        on_close = getattr(self.output, "on_close", None)
        if on_close:
            try:
                on_close()
            except Exception:
                pass
        try:
            if self._i2s is not None:
                self._i2s.deinit()
        finally:
            self._i2s = None
        try:
            if self._mck is not None:
                self._mck.deinit()
        finally:
            self._mck = None


class AudioTrack:
    """A WAV sidecar played in lockstep with the video clock.

    Decoded PCM goes through a small read-ahead buffer. Preloaded sidecars
    (the common case: 10s of PCM is 441KB) are memcpy only; bigger ones refill
    from the card in one large read, which costs a fraction of what reading a
    few KB per frame did.
    """

    def __init__(self, source, sink, lead_ms=AUDIO_LEAD_MS, low_ms=AUDIO_LOW_MS,
                 queue_bytes=AUDIO_QUEUE_BYTES, queue_low=AUDIO_QUEUE_LOW):
        self.source = source
        self.sink = sink
        self.rate = source.playback_rate
        self.channels = source.channels
        self.preloaded = source.in_memory
        self.clock = AudioClock(source.byte_rate, lead_ms, low_ms, self.channels * 2)
        self.queue_bytes = queue_bytes
        self.queue_low = queue_low
        # One preallocated buffer, consumed from the front and compacted in
        # place. Building a fresh bytearray per refill cost 7ms of PSRAM heap
        # churn per frame and set off GC pauses inside the pump.
        self._buf = bytearray(queue_bytes)
        self._len = 0
        self._pos = 0
        self.started = False
        self.finished = False
        self._source_done = False
        self.start_ms = 0
        self.read_us = 0
        self.write_us = 0
        self.written = 0
        self.skipped = 0
        self.resyncs = 0
        self.underruns = 0
        self.min_pending_ms = 100000

    # ----- read-ahead ---------------------------------------------------

    def buffered_bytes(self):
        return self._len - self._pos

    def _compact(self):
        if self._pos:
            tail = self._len - self._pos
            if tail:
                self._buf[0:tail] = memoryview(self._buf)[self._pos:self._len]
            self._len = tail
            self._pos = 0

    def _drop(self, n):
        """Discard the oldest n bytes of queued PCM; returns how many."""
        available = self.buffered_bytes()
        if available < n:
            n = available
        if n <= 0:
            return 0
        self._pos += n
        if self._pos >= self._len:
            self._pos = 0
            self._len = 0
        return n

    def _take(self, n):
        available = self.buffered_bytes()
        if available <= 0:
            return None
        if n > available:
            n = available
        start = self._pos
        self._pos += n
        if self._pos >= self._len:
            # Drained to the end: reset instead of leaving the cursor level
            # with the write head, which looks like a full ring to _refill.
            self._pos = 0
            self._len = 0
        return memoryview(self._buf)[start:start + n]

    def _refill(self):
        free = self.queue_bytes - self._len
        if free < 16:
            # The ring looks full only because the read cursor moved; compact
            # first. Refusing here turned a single stray byte into a deadlock
            # that never refilled again.
            self._compact()
            free = self.queue_bytes - self._len
            if free < 16:
                return 0
        t = _ticks_us()
        n = self.source.read_into(self._buf, self._len, free)
        if n <= 0 and self._pos and not self.source.exhausted:
            # A decoder with a block granularity cannot use a short tail, and
            # treating that as end of stream silences the rest of the clip.
            self._compact()
            free = self.queue_bytes - self._len
            if free >= 16:
                n = self.source.read_into(self._buf, self._len, free)
        self.read_us += _ticks_diff(_ticks_us(), t)
        if n <= 0:
            self._source_done = self.source.exhausted
            return 0
        self._len += n
        return n

    # ----- playback -----------------------------------------------------

    def ready(self):
        """Wait out the sink's startup silence, with nothing playing yet."""
        if not self.started:
            self.sink.wait_ready()

    def start(self, now_ms):
        # Waiting drained the ring before the first frame was drawn, so the
        # prime below lands in microseconds and sample 0 starts right here.
        self.sink.wait_ready()
        start_ms = _ticks_ms()
        self.clock.start(start_ms)
        self.start_ms = start_ms
        self.started = True
        # Prime the whole lead so the first frames' worth of picture work
        # cannot starve the peripheral.
        self.tick(start_ms, self.clock.lead_bytes())
        return start_ms

    def tick(self, now_ms, max_bytes=AUDIO_READ_BYTES):
        """Keep the sink fed; returns the bytes written this call."""
        if not self.started or self.finished:
            return 0
        if not self._source_done and self.buffered_bytes() < self.queue_low:
            self._refill()
        behind = self.clock.late_bytes(now_ms)
        if behind > 0:
            # The pump stalled longer than the queue: skip the sound forward
            # rather than play the rest of the clip late (dropped frames keep
            # the pictures on time, skipped bytes do the same for audio).
            self.underruns += 1
            dropped = self._drop(behind)
            if dropped < behind:
                dropped += self.source.skip_bytes(behind - dropped)
            if dropped > 0:
                self.resyncs += 1
                self.skipped += dropped
            else:
                dropped = behind
            self.clock.note(dropped)
            if not self._source_done and self.buffered_bytes() < self.queue_low:
                self._refill()
        want = self.clock.to_write(now_ms, max_bytes)
        if want <= 0:
            self._note_queue(now_ms)
            return 0
        data = self._take(want)
        if not data:
            if self._source_done:
                self.finished = True
            return 0
        t = _ticks_us()
        try:
            written = self.sink.write(data)
        except Exception as e:
            self.write_us += _ticks_diff(_ticks_us(), t)
            self.finished = True
            raise e
        self.write_us += _ticks_diff(_ticks_us(), t)
        if written:
            self.clock.note(written)
            self.written += written
        self._note_queue(now_ms)
        return written

    def _note_queue(self, now_ms):
        pending = self.clock.pending_ms(now_ms)
        if pending < self.min_pending_ms:
            self.min_pending_ms = pending

    def stop(self):
        self.finished = True
        try:
            self.sink.close()
        finally:
            self.source.close()
