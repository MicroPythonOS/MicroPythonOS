"""A sink for audio an app synthesises itself.

The player (``Player``/``WAVStream``/``BuzzerStream``) is for *files*: it
decodes, resamples, streams and reports progress. A game engine already has its
own mixer and only needs somewhere to put int16 samples, so this module exposes
the same devices as a plain ``write(buf)`` sink:

* an i2s DAC, with the MCLK carrier some codecs need, or
* the piezo buzzer driver, which rewrites an LEDC duty from a timer interrupt.

Which device is used is not the app's business: with no argument it is the one
the user selected in Settings -> Audio (``AudioManager.set_default_output``), so
"play this audio" means "play it where the user wants audio". An app that has a
reason to override that can name an output (``output=AudioManager
.find_output_by_kind("buzzer")``) or its name.

    sink = AudioManager.open_pcm(rate=11025)
    sink.write(samples)      # int16, mono unless channels=2
    sink.close()
"""

import logging

import machine

from mpos.audio.stream_buzzer import open_sink as open_buzzer_sink

logger = logging.getLogger(__name__)


class PcmSink:
    """Write int16 samples to whichever output the user (or the app) chose."""

    def __init__(self, rate, channels=1, output=None, ibuf=8192):
        self.rate = rate
        self.channels = channels
        self.ibuf = ibuf
        self.output = output
        self._i2s = None
        self._mck = None
        self._buzzer = None
        self._hosted = None
        self._open()

    # -- opening ----------------------------------------------------------

    def _open_i2s(self, output):
        if not hasattr(machine, "I2S"):
            # A desktop or a browser declares an i2s output for the settings UI
            # but has no machine.I2S: its speakers are the host's.
            return self._open_hosted()
        pins = output.i2s_pins
        if not pins:
            return False
        if "mck" in pins:
            # A codec's master clock, as the WAV stream drives it: a 256x
            # carrier at 50% duty.
            self._mck = machine.PWM(machine.Pin(pins["mck"], machine.Pin.OUT))
            self._mck.freq(self.rate * 256)
            self._mck.duty_u16(32768)
        self._i2s = machine.I2S(
            0,
            sck=machine.Pin(pins["sck"], machine.Pin.OUT),
            ws=machine.Pin(pins["ws"], machine.Pin.OUT),
            sd=machine.Pin(pins["sd"], machine.Pin.OUT),
            mode=machine.I2S.TX,
            bits=16,
            format=(machine.I2S.MONO if self.channels == 1
                    else machine.I2S.STEREO),
            rate=self.rate,
            ibuf=self.ibuf,
        )
        # Silence for the I2S DMA ring, so the codec starts on a valid clock.
        self._i2s.write(bytearray(1024))
        return True

    def _open_hosted(self):
        """The host's own speakers: c_mpos/hosted_audio (ALSA, or WebAudio)."""
        try:
            import hosted_audio
            hosted_audio.open(rate=self.rate, channels=self.channels)
        except Exception as error:
            logger.warning("pcm: no hosted audio: %s", error)
            return False
        self._hosted = hosted_audio
        return True

    def _open_output(self, output):
        if output is None:
            return False
        try:
            if output.kind == "i2s":
                return self._open_i2s(output)
            if output.kind == "buzzer":
                self._buzzer = open_buzzer_sink(output, self.rate, self.channels)
                return self._buzzer is not None
        except Exception as error:
            logger.warning("pcm: cannot use %s: %s", output.name, error)
            self.close()
        return False

    def _open(self):
        if self._open_output(self.output):
            return
        # The chosen device could not be opened (no pins, a driver missing from
        # the firmware): a quiet piezo is better than silence, so try it before
        # giving up.
        from mpos import AudioManager

        fallback = AudioManager.find_output_by_kind("buzzer")
        if fallback is not None and fallback is not self.output:
            logger.warning("pcm: falling back to %s", fallback.name)
            self._open_output(fallback)

    # -- using ------------------------------------------------------------

    @property
    def active(self):
        return (self._i2s is not None or self._buzzer is not None
                or self._hosted is not None)

    def write(self, buffer):
        """Queue int16 samples; returns the number of bytes accepted."""
        if self._i2s is not None:
            return self._i2s.write(buffer)
        if self._hosted is not None:
            return self._hosted.write(buffer)
        if self._buzzer is not None:
            return self._buzzer.write(buffer)
        return 0

    def close(self):
        if self._hosted is not None:
            try:
                self._hosted.close()
            except Exception:
                pass
            self._hosted = None
        for name in ("_i2s", "_mck", "_buzzer"):
            device = getattr(self, name, None)
            if device is not None:
                try:
                    device.deinit()
                except Exception:
                    pass
                setattr(self, name, None)
