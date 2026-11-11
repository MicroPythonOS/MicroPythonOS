# BuzzerStream - PCM playback through a passive piezo buzzer.
#
# The buzzer "output" used to be RTTTL-only: AudioManager refused a file on a
# kind="buzzer" output because driving a piezo with a square wave is not
# speaker playback. The ESP32 `buzzer` C module lifts that restriction: it
# keeps a FIFO of int16 samples and rewrites an LEDC duty cycle from a hardware
# timer interrupt at the sample rate, which turns the piezo into a (quiet, low
# fidelity) speaker. See c_mpos/src/buzzer.c for the driver itself.
#
# Everything above the driver is reused from WAVStream: WAV/ADPCM parsing,
# bit-depth conversion, chunking, progress, repeat and volume. WAVStream talks
# to an I2S object with write()/shift()/deinit(); this module supplies the same
# three calls, so the playback loop runs unchanged.
#
# On desktop and web there is no PWM pin, so an emulated sink reproduces the
# driver's conversions in Python (mono downmix, volume) and writes the result
# to a temporary WAV file that the normal desktop player then plays. That keeps
# the decode -> mono -> volume chain testable without hardware.

import logging
import micropython
import os
import sys

from mpos.audio.stream_mp3 import MP3Stream
from mpos.audio.stream_wav import WAVStream

logger = logging.getLogger(__name__)

_DEVICE_BITS = 10
_DEVICE_BUFSIZE = 4096
# Upper bound for the ring when an app streams its own audio (see BuzzerSink).
_DEVICE_MAX_BUFSIZE = 32768

# The sink that owns the native driver right now. A clip that is stopped or
# superseded can finish its deinit() after the next clip already called
# init(), and that late deinit must not tear the new clip down.
_active_sink = None


class _BuzzerSink:
    """Minimal I2S-like sink for the WAVStream playback loop."""

    def write(self, buf):
        raise NotImplementedError

    def shift(self, buf=None, bits=16, shift=0):
        raise NotImplementedError

    def deinit(self):
        raise NotImplementedError


class _DeviceBuzzerSink(_BuzzerSink):
    """Drives the ESP32 `buzzer` C module (LEDC PWM + timer ISR)."""

    def __init__(self, pin, rate, channels, gain=100, bufsize=_DEVICE_BUFSIZE):
        import buzzer as _buzzer

        global _active_sink
        self._buzzer = _buzzer
        self._channels = channels
        self.rate = rate
        # A 4096-sample ring holds ~186 ms at 22 kHz: enough to ride out a GC
        # pause or a slow flash read without an underrun.
        _buzzer.init(pin, rate=rate, bits=_DEVICE_BITS, bufsize=bufsize)
        _buzzer.set_gain(gain)
        _active_sink = self

    def write(self, buf):
        return self._buzzer.write(buf, channels=self._channels)

    def shift(self, buf=None, bits=16, shift=0):
        # Volume is the same arithmetic shift the I2S hardware applies;
        # WAVStream calls this per chunk with a negative value.
        if buf is not None and shift < 0:
            self._buzzer.attenuate(buf, -shift)

    def deinit(self):
        global _active_sink
        if _active_sink is not self:
            return
        _active_sink = None
        try:
            self._buzzer.deinit()
        except Exception as e:
            logger.error("buzzer deinit failed: %s", e)

    def abort(self):
        # Called from another thread: only unblock/discard, never free. The
        # playback thread still owns deinit(). Ignore a late abort from a clip
        # that has already been superseded, or it would silence the new one.
        if _active_sink is not self:
            return
        try:
            self._buzzer.stop()
        except Exception:
            pass


class _EmulatedBuzzerSink(_BuzzerSink):
    """Desktop/web stand-in: applies the driver's conversions to a WAV file."""

    def __init__(self, rate, channels):
        self.rate = rate
        self._channels = channels
        self.path = "/tmp/mpos_buzzer_%d.wav" % id(self)
        self.samples = 0
        self._data_bytes = 0
        self._file = open(self.path, "wb")
        self._write_header()

    def _write_header(self):
        rate = self.rate
        f = self._file
        f.write(b"RIFF\x00\x00\x00\x00WAVEfmt ")
        f.write((16).to_bytes(4, "little"))
        f.write((1).to_bytes(2, "little"))
        f.write((1).to_bytes(2, "little"))
        f.write(rate.to_bytes(4, "little"))
        f.write((rate * 2).to_bytes(4, "little"))
        f.write((2).to_bytes(2, "little"))
        f.write((16).to_bytes(2, "little"))
        f.write(b"data\x00\x00\x00\x00")

    @staticmethod
    @micropython.native
    def _attenuate(buf, shift):
        j = 0
        for i in range(0, len(buf), 2):
            value = buf[i] | (buf[i + 1] << 8)
            if value & 0x8000:
                value -= 0x10000
            value = (value >> shift) & 0xFFFF
            buf[j] = value & 0xFF
            buf[j + 1] = value >> 8
            j += 2

    @staticmethod
    @micropython.native
    def _downmix(buf):
        out = bytearray(len(buf) // 2)
        j = 0
        for i in range(0, len(buf), 4):
            left = buf[i] | (buf[i + 1] << 8)
            right = buf[i + 2] | (buf[i + 3] << 8)
            if left & 0x8000:
                left -= 0x10000
            if right & 0x8000:
                right -= 0x10000
            value = ((left + right) >> 1) & 0xFFFF
            out[j] = value & 0xFF
            out[j + 1] = value >> 8
            j += 2
        return out

    def write(self, buf):
        consumed = len(buf)
        data = self._downmix(buf) if self._channels == 2 else buf
        self._file.write(data)
        self._data_bytes += len(data)
        self.samples += len(data) // 2
        return consumed

    def shift(self, buf=None, bits=16, shift=0):
        if buf is not None and shift < 0:
            self._attenuate(buf, -shift)

    def abort(self):
        pass

    def deinit(self):
        try:
            self._file.flush()
            self._file.seek(4)
            self._file.write((self._data_bytes + 36).to_bytes(4, "little"))
            self._file.seek(40)
            self._file.write(self._data_bytes.to_bytes(4, "little"))
        finally:
            self._file.close()


class _BuzzerOutput:
    """Mixin: WAVStream/MP3Stream with the buzzer as the audio sink."""

    force_pcm = True

    def _init_buzzer(self, buzzer_pin, buzzer_gain=100):
        self.buzzer_pin = buzzer_pin
        self.buzzer_gain = buzzer_gain
        self._sink = None

    def _open_or_reuse_i2s(self, playback_rate, channels, ibuf, keep_warm):
        if sys.platform == "esp32":
            self._sink = _DeviceBuzzerSink(self.buzzer_pin, playback_rate, channels,
                                           getattr(self, "buzzer_gain", 100))
        else:
            self._sink = _EmulatedBuzzerSink(playback_rate, channels)
        self._i2s = self._sink

    def stop(self):
        # Unblock a write() that is waiting for ring space before the base
        # class flag is set: on the device it sits in a C call with the GIL
        # released until the ISR makes room.
        sink = self._sink
        if sink is not None:
            try:
                sink.abort()
            except Exception:
                pass
        # Not super(): MicroPython resolves zero-argument super() from the
        # defining class and did not find WAVStream.stop() through the mixin
        # here ("'super' object has no attribute 'stop'").
        WAVStream.stop(self)

    def _teardown_i2s(self):
        sink = self._sink
        self._sink = None
        self._i2s = None
        if sink is None:
            return
        try:
            sink.deinit()
        except Exception as e:
            logger.error("buzzer sink deinit failed: %s", e)
        if isinstance(sink, _EmulatedBuzzerSink):
            self._play_emulated(sink)

    def _play_emulated(self, sink):
        """Play back what the buzzer driver would have produced."""
        if not self._keep_running or sink.samples <= 0:
            self._remove_emulated(sink)
            return
        if __debug__: logger.debug("Emulated buzzer output: %s samples at %s Hz", sink.samples, sink.rate)
        player = WAVStream(
            file_path=sink.path,
            stream_type=self.stream_type,
            volume=100,
            i2s_pins={},
            on_complete=None,
        )
        player._playback_rate = sink.rate
        player._total_samples = sink.samples
        player._duration_ms = int(sink.samples * 1000 / sink.rate)
        try:
            player._play_desktop()
        finally:
            self._remove_emulated(sink)

    @staticmethod
    def _remove_emulated(sink):
        try:
            os.remove(sink.path)
        except OSError:
            pass


class BuzzerSink:
    """PCM sink for apps that pump their own audio frames.

    Same shape as the I2S sink the video player uses (open(), wait_ready(),
    write(bytes) -> bytes accepted, close(), plus `written`), so an app can
    stream to a buzzer output without going through AudioManager.player().

    The ring is sized for LEAD_MS of audio, which is more than the ~180 ms lead
    a video player keeps queued, so write() lands in free space instead of
    blocking the frame loop while the ring drains.
    """

    LEAD_MS = 250

    def __init__(self, output, rate, channels=2, bufsize=None):
        self.output = output
        self.rate = int(rate)
        self.channels = 1 if int(channels) == 1 else 2
        self.written = 0
        self._sink = None
        if bufsize is None:
            frames = (self.rate * self.LEAD_MS + 999) // 1000
            bufsize = 4096
            while bufsize < frames and bufsize < _DEVICE_MAX_BUFSIZE:
                bufsize <<= 1
        self.bufsize = bufsize
        self.capacity_ms = bufsize * 1000 // self.rate

    def open(self):
        if sys.platform != "esp32":
            raise RuntimeError("the buzzer output only exists on the device")
        self._sink = _DeviceBuzzerSink(
            self.output.buzzer_pin,
            self.rate,
            self.channels,
            getattr(self.output, "buzzer_gain", 800),
            self.bufsize,
        )

    def wait_ready(self):
        # The buzzer has no DMA ring to prime: the ISR starts as soon as the
        # first samples arrive.
        pass

    def write(self, data):
        if self._sink is None:
            return 0
        written = self._sink.write(data)
        self.written += written
        return written

    def close(self):
        sink = self._sink
        self._sink = None
        if sink is not None:
            sink.deinit()


class BuzzerStream(_BuzzerOutput, WAVStream):
    """WAV/ADPCM playback on a piezo buzzer."""

    def __init__(
        self,
        file_path,
        stream_type,
        volume,
        buzzer_pin,
        on_complete,
        requested_sample_rate=None,
        repeat_count=1,
        buzzer_gain=100,
        **kwargs
    ):
        self._init_buzzer(buzzer_pin, buzzer_gain)
        WAVStream.__init__(
            self,
            file_path=file_path,
            stream_type=stream_type,
            volume=volume,
            i2s_pins={},
            on_complete=on_complete,
            requested_sample_rate=requested_sample_rate,
            repeat_count=repeat_count,
            **kwargs
        )


class BuzzerMP3Stream(_BuzzerOutput, MP3Stream):
    """MP3 playback on a piezo buzzer."""

    def __init__(
        self,
        file_path,
        stream_type,
        volume,
        buzzer_pin,
        on_complete,
        repeat_count=1,
        buzzer_gain=100,
        **kwargs
    ):
        self._init_buzzer(buzzer_pin, buzzer_gain)
        MP3Stream.__init__(
            self,
            file_path=file_path,
            stream_type=stream_type,
            volume=volume,
            i2s_pins={},
            on_complete=on_complete,
            repeat_count=repeat_count,
            **kwargs
        )
