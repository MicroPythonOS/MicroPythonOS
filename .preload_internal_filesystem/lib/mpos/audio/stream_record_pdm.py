# PDMRecordStream - WAV File Recording Stream for PDM microphones
# Records 16-bit mono PCM audio from PDM microphone to WAV file

import logging
import sys
import time

from mpos.audio.audiomanager import AudioManager

logger = logging.getLogger(__name__)

# Try to import PDM mic module (not available on desktop)
try:
    from pdm_mic import PDM_Mic

    _HAS_PDM = True
except ImportError:
    _HAS_PDM = False


class PDMRecordStream:
    """
    WAV file recording stream with PDM input.
    Records 16-bit mono PCM audio from PDM microphone.
    """

    DEFAULT_SAMPLE_RATE = 16000
    DEFAULT_MAX_DURATION_MS = 60000
    DEFAULT_FILESIZE = 1024 * 1024 * 1024
    DEFAULT_BUFSIZE = 4096

    def __init__(self, file_path, duration_ms, sample_rate, pdm_pins, on_complete):
        self.file_path = file_path
        self.duration_ms = duration_ms if duration_ms else self.DEFAULT_MAX_DURATION_MS
        self.sample_rate = sample_rate if sample_rate else self.DEFAULT_SAMPLE_RATE
        self.pdm_pins = pdm_pins
        self.on_complete = on_complete
        self._keep_running = True
        self._is_recording = False
        self._mic = None
        self._bytes_recorded = 0
        self._start_time_ms = 0

    def is_recording(self):
        return self._is_recording

    def stop(self):
        self._keep_running = False

    def get_elapsed_ms(self):
        if self.sample_rate > 0:
            return int((self._bytes_recorded / (self.sample_rate * 2)) * 1000)
        return 0

    def _generate_sine_wave_chunk(self, chunk_size, sample_offset):
        return AudioManager._record_generate_sine_wave_chunk(
            self.sample_rate,
            chunk_size,
            sample_offset,
        )

    def record(self):
        if __debug__: logger.debug("record() called")
        if __debug__: logger.debug("  file_path: %s", self.file_path)
        if __debug__: logger.debug("  duration_ms: %s", self.duration_ms)
        if __debug__: logger.debug("  sample_rate: %s", self.sample_rate)
        if __debug__: logger.debug("  pdm_pins: %s", self.pdm_pins)
        if __debug__: logger.debug("  _HAS_PDM: %s", _HAS_PDM)

        self._is_recording = True
        self._bytes_recorded = 0
        self._start_time_ms = time.ticks_ms()

        try:
            dir_path = "/".join(self.file_path.split("/")[:-1])
            if dir_path:
                AudioManager._record_makedirs(dir_path)

            if __debug__: logger.debug("Creating WAV file with header")
            with open(self.file_path, "wb") as f:
                header = AudioManager._record_create_wav_header(
                    self.sample_rate,
                    num_channels=1,
                    bits_per_sample=16,
                    data_size=self.DEFAULT_FILESIZE,
                )
                f.write(header)

            if __debug__: logger.debug("Recording to %s", self.file_path)

            use_simulation = not _HAS_PDM

            if not use_simulation:
                try:
                    sck_pin = self.pdm_pins.get("sck_in", self.pdm_pins.get("sck"))
                    self._mic = PDM_Mic(
                        clk=sck_pin,
                        data=self.pdm_pins["sd_in"],
                        rate=self.sample_rate,
                        bufsize=self.DEFAULT_BUFSIZE,
                    )
                    self._mic.start()
                    if __debug__: logger.debug("PDM mic initialized")
                except Exception as e:
                    logger.error("PDM init failed: %s", e)
                    use_simulation = True

            if use_simulation:
                if __debug__: logger.debug("Using desktop simulation (sine wave)")

            max_bytes = int((self.duration_ms / 1000) * self.sample_rate * 2)
            chunk_size = self.DEFAULT_BUFSIZE
            sample_offset = 0

            f = open(self.file_path, "ab")
            try:
                while self._keep_running and self._bytes_recorded < max_bytes:
                    elapsed = time.ticks_diff(time.ticks_ms(), self._start_time_ms)
                    if elapsed >= self.duration_ms:
                        if __debug__: logger.debug("Duration limit reached")
                        break

                    if use_simulation:
                        buf, num_samples = self._generate_sine_wave_chunk(
                            chunk_size,
                            sample_offset,
                        )
                        sample_offset += num_samples
                        num_read = chunk_size
                        time.sleep_ms(int((chunk_size / 2) / self.sample_rate * 1000))
                    else:
                        buf = bytearray(chunk_size)
                        try:
                            num_read = self._mic.readinto(buf)
                        except Exception as e:
                            logger.error("Read error: %s", e)
                            break

                    if num_read > 0:
                        f.write(buf[:num_read])
                        self._bytes_recorded += num_read
            finally:
                f.close()
                if self._mic:
                    try:
                        self._mic.stop()
                        self._mic.deinit()
                    except Exception:
                        pass
                    self._mic = None

            elapsed_ms = time.ticks_diff(time.ticks_ms(), self._start_time_ms)
            if __debug__: logger.debug("Finished recording %s bytes (%sms)", self._bytes_recorded, elapsed_ms)

            if self.on_complete:
                self.on_complete(f"Recorded: {self.file_path}")

        except Exception as e:
            sys.print_exception(e)
            if self.on_complete:
                self.on_complete(f"Error: {e}")

        finally:
            self._is_recording = False
            if __debug__: logger.debug("Recording thread finished")
