# MP3Stream - MP3 playback stream for AudioManager.
#
# Shares the I2S/warm-output plumbing with WAVStream; decoding goes through the
# native mp3dec module (minimp3), which releases the GIL while it works so the
# UI keeps rendering on ESP32.

import logging
import os
import sys
import time

from mpos.audio.mp3 import decode_to_wav, get_info
from mpos.audio.stream_wav import WAVStream

logger = logging.getLogger(__name__)


class MP3Stream(WAVStream):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._desktop_temp = None

    def _desktop_player(self):
        if sys.platform == "darwin":
            return "afplay"
        for candidate in ("ffplay", "mpg123"):
            if os.system("command -v %s >/dev/null 2>&1" % candidate) == 0:
                return candidate
        # aplay/paplay cannot decode MP3; _desktop_audio_path() will hand them
        # a decoded WAV instead.
        return WAVStream._desktop_player(self)

    def _desktop_audio_path(self):
        player = self._desktop_player()
        if player in ("aplay", "paplay"):
            temp_path = "/tmp/mpos_mp3_%d.wav" % id(self)
            if __debug__: logger.debug("Decoding %s for %s", self.file_path, player)
            decode_to_wav(self.file_path, temp_path, self.volume)
            self._desktop_temp = temp_path
            return temp_path
        return self.file_path

    def play(self):
        """Main synchronous playback routine (runs in a separate thread)."""
        self._is_playing = True
        self._desktop_temp = None

        try:
            info = get_info(self.file_path)
            self._original_rate = info["sample_rate"]
            self._channels = info["channels"]
            self._total_samples = info["total_samples"]
            self._duration_ms = info["duration_ms"]
            self._playback_rate = self._original_rate

            if sys.platform != "esp32":
                self._play_desktop()
                return

            import mp3dec

            if self._original_rate <= 0 or self._channels <= 0:
                raise ValueError("Invalid MP3 stream parameters")

            ibuf = 8192 * 4
            try:
                self._open_or_reuse_i2s(
                    self._playback_rate, self._channels, ibuf, self.warm_ms > 0)
            except Exception as e:
                logger.error("I2S init failed: %s", e)
                return

            decoder = mp3dec.Decoder()
            out = bytearray(16384)
            chunk_size = 4096
            try:
                with open(self.file_path, "rb") as f:
                    play_start_ms = time.ticks_ms()
                    played_samples = 0
                    self._repeat_played = 0
                    while self._keep_running and self._repeat_played < self.repeat_count:
                        self._repeat_played += 1
                        self._progress_samples = 0
                        decoder.reset()
                        eof = False
                        while self._keep_running and not eof:
                            data = f.read(chunk_size)
                            if not data:
                                eof = True
                                decoder.finish()
                            while self._keep_running:
                                shift = WAVStream._volume_percent_to_shift(self.volume)
                                written = decoder.decode_into(data, out, shift)
                                data = b""
                                if not written:
                                    break
                                remaining = memoryview(out)[:written]
                                while remaining:
                                    sent = self._i2s.write(remaining)
                                    if sent is None:
                                        sent = len(remaining)
                                    if sent <= 0:
                                        time.sleep_ms(1)
                                        continue
                                    remaining = remaining[sent:]
                                samples = written // (2 * self._channels)
                                self._progress_samples += samples
                                if self._progress_samples > self._total_samples:
                                    self._progress_samples = self._total_samples
                                played_samples += samples
                            if self._keep_running:
                                time.sleep_ms(1)
                        if self._repeat_played < self.repeat_count and self._keep_running:
                            f.seek(0)
            finally:
                decoder.close()

            if self._i2s and self._keep_running:
                elapsed_ms = time.ticks_diff(time.ticks_ms(), play_start_ms)
                played_ms = played_samples * 1000 // self._playback_rate
                drain_ms = WAVStream.compute_drain_ms(played_ms, elapsed_ms)
                if drain_ms > 0:
                    time.sleep_ms(drain_ms)

            if __debug__: logger.debug("Finished playing %s", self.file_path)
            if self.on_complete:
                self.on_complete("Finished: %s" % self.file_path)

        except Exception as e:
            logger.error("Error: %s", e)
            if self.on_complete:
                self.on_complete("Error: %s" % e)

        finally:
            if self._desktop_temp:
                try:
                    os.remove(self._desktop_temp)
                except OSError:
                    pass
                self._desktop_temp = None
            if not self.runs_async:
                self._is_playing = False
                self._teardown_i2s()
