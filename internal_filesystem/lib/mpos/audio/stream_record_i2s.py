# RecordStream - WAV File Recording Stream for AudioManager
# Records 16-bit mono PCM audio from I2S microphone to WAV file
# Uses synchronous recording in a separate thread for non-blocking operation
# On desktop (no I2S hardware), generates a 440Hz sine wave for testing

import sys
import time

from mpos.audio.audiomanager import AudioManager

# Try to import machine module (not available on desktop)
try:
    import machine
    _HAS_MACHINE = True
except ImportError:
    _HAS_MACHINE = False


class RecordStream:
    """
    WAV file recording stream with I2S input.
    Records 16-bit mono PCM audio from I2S microphone.
    """

    # Default recording parameters
    DEFAULT_SAMPLE_RATE = 16000  # 16kHz - good for voice
    DEFAULT_MAX_DURATION_MS = 60000  # 60 seconds max
    DEFAULT_FILESIZE = 1024 * 1024 * 1024 # 1GB data size because it can't be quickly set after recording

    def __init__(self, file_path, duration_ms, sample_rate, i2s_pins, on_complete,
                 on_open=None, on_close=None):
        """
        Initialize recording stream.

        Args:
            file_path: Path to save WAV file
            duration_ms: Recording duration in milliseconds (None = until stop())
            sample_rate: Sample rate in Hz
            i2s_pins: Dict with 'sck', 'ws', 'sd_in' pin numbers
            on_complete: Callback function(message) when recording finishes
            on_open: Optional callable invoked after MCLK starts, before I2S init
            on_close: Optional callable invoked before I2S deinit
        """
        self.file_path = file_path
        self.duration_ms = duration_ms if duration_ms else self.DEFAULT_MAX_DURATION_MS
        self.sample_rate = sample_rate if sample_rate else self.DEFAULT_SAMPLE_RATE
        self.i2s_pins = i2s_pins
        self.on_complete = on_complete
        self.on_open = on_open
        self.on_close = on_close
        self._keep_running = True
        self._is_recording = False
        self._i2s = None
        self._mck_pwm = None
        self._bytes_recorded = 0
        self._start_time_ms = 0

    def is_recording(self):
        """Check if stream is currently recording."""
        return self._is_recording

    def stop(self):
        """Stop recording."""
        self._keep_running = False

    def get_elapsed_ms(self):
        """Get elapsed recording time in milliseconds."""
        # Calculate from bytes recorded: bytes / (sample_rate * 2 bytes per sample) * 1000
        if self.sample_rate > 0:
            return int((self._bytes_recorded / (self.sample_rate * 2)) * 1000)
        return 0

    # ----------------------------------------------------------------------
    #  WAV header generation
    # ----------------------------------------------------------------------
    @staticmethod
    def _create_wav_header(sample_rate, num_channels, bits_per_sample, data_size):
        return AudioManager._record_create_wav_header(
            sample_rate,
            num_channels,
            bits_per_sample,
            data_size,
        )

    @staticmethod
    def _update_wav_header(file_path, data_size):
        return AudioManager._record_update_wav_header(file_path, data_size)


    # ----------------------------------------------------------------------
    #  Desktop simulation - generate 440Hz sine wave
    # ----------------------------------------------------------------------
    def _generate_sine_wave_chunk(self, chunk_size, sample_offset):
        return AudioManager._record_generate_sine_wave_chunk(
            self.sample_rate,
            chunk_size,
            sample_offset,
        )

    # ----------------------------------------------------------------------
    #  Main recording routine
    # ----------------------------------------------------------------------
    def record(self):
        """Main synchronous recording routine (runs in separate thread)."""
        print(f"RecordStream.record() called")
        print(f"  file_path: {self.file_path}")
        print(f"  duration_ms: {self.duration_ms}")
        print(f"  sample_rate: {self.sample_rate}")
        print(f"  i2s_pins: {self.i2s_pins}")
        print(f"  _HAS_MACHINE: {_HAS_MACHINE}")

        self._is_recording = True
        self._bytes_recorded = 0
        self._start_time_ms = time.ticks_ms()

        try:
            # Ensure directory exists
            dir_path = '/'.join(self.file_path.split('/')[:-1])
            print(f"RecordStream: Creating directory: {dir_path}")
            if dir_path:
                AudioManager._record_makedirs(dir_path)
                print(f"RecordStream: Directory created/verified")

            # Create file with placeholder header
            print(f"RecordStream: Creating WAV file with header")
            with open(self.file_path, 'wb') as f:
                # Write placeholder header (will be updated at end)
                header = self._create_wav_header(
                    self.sample_rate,
                    num_channels=1,
                    bits_per_sample=16,
                    data_size=self.DEFAULT_FILESIZE,
                )
                f.write(header)
                print(f"RecordStream: Header written ({len(header)} bytes)")

            print(f"RecordStream: Recording to {self.file_path}")
            print(f"RecordStream: {self.sample_rate} Hz, 16-bit, mono")
            print(f"RecordStream: Max duration {self.duration_ms}ms")

            # Check if we have real I2S hardware or need to simulate
            use_simulation = not _HAS_MACHINE

            if not use_simulation:
                # Initialize I2S in RX mode with correct pins for microphone
                try:
                    # Start MCLK on mck pin if provided (required for I2S codecs such as ES8311)
                    if 'mck' in self.i2s_pins:
                        try:
                            from machine import Pin, PWM
                            mck_pin = Pin(self.i2s_pins['mck'], Pin.OUT)
                            self._mck_pwm = PWM(mck_pin)
                            mck_freq = self.sample_rate * 256
                            self._mck_pwm.freq(mck_freq)
                            self._mck_pwm.duty_u16(32768)  # 50% duty cycle
                            print(f"RecordStream: MCLK PWM started at {mck_freq} Hz")
                        except Exception as e:
                            print(f"RecordStream: MCLK PWM init failed: {e}")

                    # Notify codec to prepare for recording (e.g. mute DAC, configure ADC)
                    if self.on_open:
                        try:
                            self.on_open()
                        except Exception as e:
                            print(f"RecordStream: on_open failed: {e}")

                    # Use sck_in if available (separate clock for mic), otherwise fall back to sck
                    sck_pin = self.i2s_pins.get('sck_in', self.i2s_pins.get('sck'))
                    print(f"RecordStream: Initializing I2S RX with sck={sck_pin}, ws={self.i2s_pins['ws']}, sd={self.i2s_pins['sd_in']}")

                    self._i2s = machine.I2S(
                        0,
                        sck=machine.Pin(sck_pin, machine.Pin.OUT),
                        ws=machine.Pin(self.i2s_pins['ws'], machine.Pin.OUT),
                        sd=machine.Pin(self.i2s_pins['sd_in'], machine.Pin.IN),
                        mode=machine.I2S.RX,
                        bits=16,
                        format=machine.I2S.MONO,
                        rate=self.sample_rate,
                        ibuf=8000  # 8KB input buffer
                    )
                    print(f"RecordStream: I2S initialized successfully")
                except Exception as e:
                    print(f"RecordStream: I2S init failed: {e}")
                    print(f"RecordStream: Falling back to simulation mode")
                    use_simulation = True

            if use_simulation:
                print(f"RecordStream: Using desktop simulation (440Hz sine wave)")

            # Calculate recording parameters
            chunk_size = 1024  # Read 1KB at a time
            max_bytes = int((self.duration_ms / 1000) * self.sample_rate * 2)
            start_time = time.ticks_ms()
            sample_offset = 0  # For sine wave phase continuity

            # Flush every ~2 seconds of audio (64KB at 16kHz 16-bit mono)
            # This spreads out the filesystem write overhead
            flush_interval_bytes = 64 * 1024
            bytes_since_flush = 0
            last_flush_time = start_time

            print(f"RecordStream: max_bytes={max_bytes}, chunk_size={chunk_size}, flush_interval={flush_interval_bytes}")

            # Open file for appending audio data (append mode to avoid seek issues)
            print(f"RecordStream: Opening file for audio data...")
            t0 = time.ticks_ms()
            f = open(self.file_path, 'ab')
            print(f"RecordStream: File opened in {time.ticks_diff(time.ticks_ms(), t0)}ms")

            buf = bytearray(chunk_size)

            try:
                while self._keep_running and self._bytes_recorded < max_bytes:
                    # Check elapsed time
                    elapsed = time.ticks_diff(time.ticks_ms(), start_time)
                    if elapsed >= self.duration_ms:
                        print(f"RecordStream: Duration limit reached ({elapsed}ms)")
                        break

                    if use_simulation:
                        # Generate sine wave samples for desktop testing
                        buf, num_samples = self._generate_sine_wave_chunk(chunk_size, sample_offset)
                        sample_offset += num_samples
                        num_read = chunk_size

                        # Simulate real-time recording speed
                        time.sleep_ms(int((chunk_size / 2) / self.sample_rate * 1000))
                    else:
                        # Read from I2S
                        try:
                            num_read = self._i2s.readinto(buf)
                        except Exception as e:
                            print(f"RecordStream: Read error: {e}")
                            break

                    if num_read > 0:
                        f.write(buf[:num_read])
                        self._bytes_recorded += num_read
                        bytes_since_flush += num_read

                        # Periodic flush to spread out filesystem overhead
                        if bytes_since_flush >= flush_interval_bytes:
                            t0 = time.ticks_ms()
                            f.flush()
                            flush_time = time.ticks_diff(time.ticks_ms(), t0)
                            print(f"RecordStream: Flushed {bytes_since_flush} bytes in {flush_time}ms")
                            bytes_since_flush = 0
                            last_flush_time = time.ticks_ms()
            finally:
                # Explicitly close the file and measure time
                print(f"RecordStream: Closing audio data file (remaining {bytes_since_flush} bytes)...")
                t0 = time.ticks_ms()
                f.close()
                print(f"RecordStream: File closed in {time.ticks_diff(time.ticks_ms(), t0)}ms")

            # Disabled because seeking takes too long on LittleFS2:
            #self._update_wav_header(self.file_path, self._bytes_recorded)

            elapsed_ms = time.ticks_diff(time.ticks_ms(), start_time)
            print(f"RecordStream: Finished recording {self._bytes_recorded} bytes ({elapsed_ms}ms)")

            if self.on_complete:
                self.on_complete(f"Recorded: {self.file_path}")

        except Exception as e:
            import sys
            print(f"RecordStream: Error: {e}")
            sys.print_exception(e)
            if self.on_complete:
                self.on_complete(f"Error: {e}")

        finally:
            self._is_recording = False
            if self.on_close:
                try:
                    self.on_close()
                except Exception as e:
                    print(f"RecordStream: on_close failed: {e}")
            if self._i2s:
                self._i2s.deinit()
                self._i2s = None
            if self._mck_pwm:
                try:
                    self._mck_pwm.deinit()
                except Exception:
                    pass
                self._mck_pwm = None
            print(f"RecordStream: Recording thread finished")

    def get_duration_ms(self):
        if self._start_time_ms <= 0:
            return 0
        return time.ticks_diff(time.ticks_ms(), self._start_time_ms)