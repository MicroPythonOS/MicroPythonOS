# ADCRecordStream - WAV File Recording Stream with C-based ADC Sampling
# Records 16-bit mono PCM audio from ADC using the optimized adc_mic C module
# Uses timer-based sampling with double buffering in C for high performance
# Maintains compatibility with AudioManager and existing recording framework

import os
import sys
import time
import gc
import array

# Try to import machine module (not available on desktop)
try:
    import machine
    import adc_mic
    _HAS_HARDWARE = True
except ImportError:
    _HAS_HARDWARE = False


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


class ADCRecordStream:
    """
    WAV file recording stream with C-optimized ADC sampling.
    Records 16-bit mono PCM audio from ADC using the adc_mic module.
    """

    # Default recording parameters
    DEFAULT_SAMPLE_RATE = 16000  # 16kHz - good for voice/ADC
    DEFAULT_MAX_DURATION_MS = 60000  # 60 seconds max
    DEFAULT_FILESIZE = 1024 * 1024 * 1024  # 1GB data size
    
    # ADC configuration defaults
    DEFAULT_ADC_PIN = 1  # GPIO1 on Fri3d 2026
    DEFAULT_ADC_UNIT = 0 # ADC_UNIT_1 = 0
    DEFAULT_ADC_CHANNEL = 0 # ADC_CHANNEL_0 = 0 (GPIO1)
    DEFAULT_ATTEN = 2 # ADC_ATTEN_DB_6 = 2

    def __init__(self, file_path, duration_ms, sample_rate, adc_pin=None,
                 on_complete=None, **adc_config):
        """
        Initialize ADC recording stream.

        Args:
            file_path: Path to save WAV file
            duration_ms: Recording duration in milliseconds (None = until stop())
            sample_rate: Target sample rate in Hz
            adc_pin: GPIO pin for ADC input (default: GPIO1)
            on_complete: Callback function(message) when recording finishes
            **adc_config: Additional ADC configuration
        """
        self.file_path = file_path
        self.duration_ms = duration_ms if duration_ms else self.DEFAULT_MAX_DURATION_MS
        self.sample_rate = sample_rate if sample_rate else self.DEFAULT_SAMPLE_RATE
        self.adc_pin = adc_pin if adc_pin is not None else self.DEFAULT_ADC_PIN
        self.on_complete = on_complete
        
        # Determine ADC unit and channel from pin
        # This is a simple mapping for ESP32-S3
        # TODO: Make this more robust or pass in unit/channel directly
        self.adc_unit = self.DEFAULT_ADC_UNIT
        self.adc_channel = self.DEFAULT_ADC_CHANNEL
        
        # Simple mapping for Fri3d 2026 (GPIO1 -> ADC1_CH0)
        if self.adc_pin == 1:
            self.adc_unit = 0 # ADC_UNIT_1
            self.adc_channel = 0 # ADC_CHANNEL_0
        elif self.adc_pin == 2:
            self.adc_unit = 0
            self.adc_channel = 1
        # Add more mappings as needed
            
        self._keep_running = True
        self._is_recording = False
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
        if self.sample_rate > 0:
            return int((self._bytes_recorded / (self.sample_rate * 2)) * 1000)
        return 0

    # -----------------------------------------------------------------------
    #  WAV header generation
    # -----------------------------------------------------------------------
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
            file_path: Path to WAV file
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

    # -----------------------------------------------------------------------
    #  Desktop simulation - generate 440Hz sine wave
    # -----------------------------------------------------------------------
    def _generate_sine_wave_chunk(self, chunk_size, sample_offset):
        """
        Generate a chunk of 440Hz sine wave samples for desktop testing.

        Args:
            chunk_size: Number of bytes to generate (must be even for 16-bit samples)
            sample_offset: Current sample offset for phase continuity

        Returns:
            tuple: (bytearray of samples, number of samples generated)
        """
        import math
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

    # -----------------------------------------------------------------------
    #  Main recording routine
    # -----------------------------------------------------------------------
    def record(self):
        """Main synchronous recording routine (runs in separate thread)."""
        print(f"ADCRecordStream.record() called")
        print(f"  file_path: {self.file_path}")
        print(f"  duration_ms: {self.duration_ms}")
        print(f"  sample_rate: {self.sample_rate}")
        print(f"  adc_pin: {self.adc_pin} (Unit {self.adc_unit}, Channel {self.adc_channel})")
        print(f"  _HAS_HARDWARE: {_HAS_HARDWARE}")

        self._is_recording = True
        self._bytes_recorded = 0
        self._start_time_ms = time.ticks_ms()

        try:
            # Ensure directory exists
            dir_path = '/'.join(self.file_path.split('/')[:-1])
            if dir_path:
                _makedirs(dir_path)

            # Create file with placeholder header
            print(f"ADCRecordStream: Creating WAV file with header")
            with open(self.file_path, 'wb') as f:
                # Write placeholder header (will be updated at end)
                header = self._create_wav_header(
                    self.sample_rate,
                    num_channels=1,
                    bits_per_sample=16,
                    data_size=self.DEFAULT_FILESIZE
                )
                f.write(header)

            print(f"ADCRecordStream: Recording to {self.file_path}")
            
            # Check if we have real hardware or need to simulate
            use_simulation = not _HAS_HARDWARE

            if not use_simulation:
                print(f"ADCRecordStream: Using hardware ADC")
                # No explicit init needed for adc_mic.read() as it handles it internally per call
                # But we might want to do some setup if the C module required it.
                # The current C module implementation does setup/teardown inside read()
                # which is inefficient for streaming.
                # However, the C module read() reads a LARGE chunk (e.g. 10000 samples).
                pass

            if use_simulation:
                print(f"ADCRecordStream: Using desktop simulation (sine wave)")

            # Calculate recording parameters
            max_bytes = int((self.duration_ms / 1000) * self.sample_rate * 2)
            
            # Open file for appending audio data
            f = open(self.file_path, 'ab')
            
            # Chunk size for reading
            # For ADC, we want a reasonable chunk size to minimize overhead
            # 4096 samples = 8192 bytes = ~0.25s at 16kHz
            chunk_samples = 4096
            
            sample_offset = 0

            try:
                while self._keep_running:
                    # Check elapsed time
                    elapsed = time.ticks_diff(time.ticks_ms(), self._start_time_ms)
                    if elapsed >= self.duration_ms:
                        print(f"ADCRecordStream: Duration limit reached")
                        break

                    # Check byte limit
                    if self._bytes_recorded >= max_bytes:
                        print(f"ADCRecordStream: Byte limit reached")
                        break

                    if use_simulation:
                        # Generate sine wave samples for desktop testing
                        buf, num_samples = self._generate_sine_wave_chunk(chunk_samples * 2, sample_offset)
                        sample_offset += num_samples
                        
                        f.write(buf)
                        self._bytes_recorded += len(buf)
                        
                        # Simulate real-time recording speed
                        time.sleep_ms(int((chunk_samples) / self.sample_rate * 1000))
                        
                    else:
                        # Read from C module
                        # adc_mic.read(chunk_samples, unit_id, adc_channel_list, adc_channel_num, sample_rate_hz, atten)
                        # Returns bytes object
                        
                        # unit_id: 0 (ADC_UNIT_1)
                        # adc_channel_list: [self.adc_channel]
                        # adc_channel_num: 1
                        # sample_rate_hz: self.sample_rate
                        # atten: 2 (ADC_ATTEN_DB_6)
                        
                        data = adc_mic.read(
                            chunk_samples, 
                            self.adc_unit, 
                            [self.adc_channel], 
                            1, 
                            self.sample_rate, 
                            self.DEFAULT_ATTEN
                        )
                        
                        if data:
                            f.write(data)
                            self._bytes_recorded += len(data)
                        else:
                            # No data available yet, short sleep
                            time.sleep_ms(10)

            finally:
                f.close()
                
                # Update WAV header with actual size
                try:
                    # Only update if we actually recorded something
                    if self._bytes_recorded > 0:
                        self._update_wav_header(self.file_path, self._bytes_recorded)
                except Exception as e:
                    print(f"ADCRecordStream: Error updating header: {e}")

            elapsed_ms = time.ticks_diff(time.ticks_ms(), self._start_time_ms)
            print(f"ADCRecordStream: Finished recording {self._bytes_recorded} bytes ({elapsed_ms}ms)")
            
            if self.on_complete:
                self.on_complete(f"Recorded: {self.file_path}")

        except Exception as e:
            sys.print_exception(e)
            if self.on_complete:
                self.on_complete(f"Error: {e}")

        finally:
            self._is_recording = False
            print(f"ADCRecordStream: Recording thread finished")
