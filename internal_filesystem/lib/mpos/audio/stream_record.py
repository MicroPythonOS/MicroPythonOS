# RecordStream - WAV File Recording Stream for AudioManager
# Records 16-bit mono PCM audio from I2S microphone to WAV file
# Uses synchronous recording in a separate thread for non-blocking operation
# On desktop (no I2S hardware), generates a 440Hz sine wave for testing

import math
import os
import sys
import time

# Try to import machine module (not available on desktop)
try:
    import machine
    _HAS_MACHINE = True
except ImportError:
    _HAS_MACHINE = False


def _makedirs(path):
    """
    Create directory and all parent directories (like os.makedirs).
    MicroPython doesn't have os.makedirs, so we implement it manually.
    """
    if not path:
        return

    parts = path.split('/')
    current = ''

    for part in parts:
        if not part:
            continue
        current = current + '/' + part if current else part
        try:
            os.mkdir(current)
        except OSError:
            pass  # Directory may already exist


class RecordStream:
    """
    WAV file recording stream with I2S input.
    Records 16-bit mono PCM audio from I2S microphone.
    """

    # Default recording parameters
    DEFAULT_SAMPLE_RATE = 16000  # 16kHz - good for voice
    DEFAULT_MAX_DURATION_MS = 60000  # 60 seconds max
    DEFAULT_FILESIZE = 1024 * 1024 * 1024 # 1GB data size because it can't be quickly set after recording

    def __init__(self, file_path, duration_ms, sample_rate, i2s_pins, on_complete):
        """
        Initialize recording stream.

        Args:
            file_path: Path to save WAV file
            duration_ms: Recording duration in milliseconds (None = until stop())
            sample_rate: Sample rate in Hz
            i2s_pins: Dict with 'sck', 'ws', 'sd_in' pin numbers
            on_complete: Callback function(message) when recording finishes
        """
        self.file_path = file_path
        self.duration_ms = duration_ms if duration_ms else self.DEFAULT_MAX_DURATION_MS
        self.sample_rate = sample_rate if sample_rate else self.DEFAULT_SAMPLE_RATE
        self.i2s_pins = i2s_pins
        self.on_complete = on_complete
        self._keep_running = True
        self._is_recording = False
        self._i2s = None
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
        """
        Create WAV file header.

        Args:
            sample_rate: Sample rate in Hz
            num_channels: Number of channels (1 for mono)
            bits_per_sample: Bits per sample (16)
            data_size: Size of audio data in bytes

        Returns:
            bytes: 44-byte WAV header
        """
        byte_rate = sample_rate * num_channels * (bits_per_sample // 8)
        block_align = num_channels * (bits_per_sample // 8)
        file_size = data_size + 36  # Total file size minus 8 bytes for RIFF header

        header = bytearray(44)

        # RIFF header
        header[0:4] = b'RIFF'
        header[4:8] = file_size.to_bytes(4, 'little')
        header[8:12] = b'WAVE'

        # fmt chunk
        header[12:16] = b'fmt '
        header[16:20] = (16).to_bytes(4, 'little')  # fmt chunk size
        header[20:22] = (1).to_bytes(2, 'little')   # PCM format
        header[22:24] = num_channels.to_bytes(2, 'little')
        header[24:28] = sample_rate.to_bytes(4, 'little')
        header[28:32] = byte_rate.to_bytes(4, 'little')
        header[32:34] = block_align.to_bytes(2, 'little')
        header[34:36] = bits_per_sample.to_bytes(2, 'little')

        # data chunk
        header[36:40] = b'data'
        header[40:44] = data_size.to_bytes(4, 'little')

        return bytes(header)

    @staticmethod
    def _update_wav_header(file_path, data_size):
        """
        Update WAV header with final data size.

        Args:
            f: File object (must be opened in r+b mode)
            data_size: Final size of audio data in bytes
        """
        file_size = data_size + 36

        f = open(file_path, 'r+b')

        # Update file size at offset 4
        f.seek(4)
        f.write(file_size.to_bytes(4, 'little'))

        # Update data size at offset 40
        f.seek(40)
        f.write(data_size.to_bytes(4, 'little'))

        f.close()


    # ----------------------------------------------------------------------
    #  Desktop simulation - generate 440Hz sine wave
    # ----------------------------------------------------------------------
    def _generate_sine_wave_chunk(self, chunk_size, sample_offset):
        """
        Generate a chunk of 440Hz sine wave samples for desktop testing.

        Args:
            chunk_size: Number of bytes to generate (must be even for 16-bit samples)
            sample_offset: Current sample offset for phase continuity

        Returns:
            tuple: (bytearray of samples, number of samples generated)
        """
        frequency = 440  # A4 note
        amplitude = 16000  # ~50% of max 16-bit amplitude

        num_samples = chunk_size // 2
        buf = bytearray(chunk_size)

        for i in range(num_samples):
            # Calculate sine wave sample
            t = (sample_offset + i) / self.sample_rate
            sample = int(amplitude * math.sin(2 * math.pi * frequency * t))

            # Clamp to 16-bit range
            if sample > 32767:
                sample = 32767
            elif sample < -32768:
                sample = -32768

            # Write as little-endian 16-bit
            buf[i * 2] = sample & 0xFF
            buf[i * 2 + 1] = (sample >> 8) & 0xFF

        return buf, num_samples

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
                _makedirs(dir_path)
                print(f"RecordStream: Directory created/verified")

            # Create file with placeholder header
            print(f"RecordStream: Creating WAV file with header")
            with open(self.file_path, 'wb') as f:
                # Write placeholder header (will be updated at end)
                header = self._create_wav_header(
                    self.sample_rate,
                    num_channels=1,
                    bits_per_sample=16,
                    data_size=self.DEFAULT_FILESIZE
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
            if self._i2s:
                self._i2s.deinit()
                self._i2s = None
            print(f"RecordStream: Recording thread finished")

    def get_duration_ms(self):
        if self._start_time_ms <= 0:
            return 0
        return time.ticks_diff(time.ticks_ms(), self._start_time_ms)