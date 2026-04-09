# ADCRecordStream - WAV File Recording Stream with C-based ADC Sampling
# Records 16-bit mono PCM audio from ADC using the optimized adc_mic C module
# Uses timer-based sampling with double buffering in C for high performance
# Maintains compatibility with AudioManager and existing recording framework

import sys
import time
import gc
import array

from mpos.audio.audiomanager import AudioManager

# Try to import machine module (not available on desktop)
try:
    import machine
    import adc_mic
    _HAS_HARDWARE = True
except ImportError:
    _HAS_HARDWARE = False


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
    #DEFAULT_ATTEN = 2 # ADC_ATTEN_DB_6
    DEFAULT_ATTEN = 3 # ADC_ATTEN_DB_12 == ADC_ATTEN_DB_11

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
        return AudioManager._record_create_wav_header(
            sample_rate,
            num_channels,
            bits_per_sample,
            data_size,
        )

    @staticmethod
    def _update_wav_header(file_path, data_size):
        return AudioManager._record_update_wav_header(file_path, data_size)

    # -----------------------------------------------------------------------
    #  Desktop simulation - generate 440Hz sine wave
    # -----------------------------------------------------------------------
    def _generate_sine_wave_chunk(self, chunk_size, sample_offset):
        return AudioManager._record_generate_sine_wave_chunk(
            self.sample_rate,
            chunk_size,
            sample_offset,
        )

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
                AudioManager._record_makedirs(dir_path)

            # Create file with placeholder header
            print(f"ADCRecordStream: Creating WAV file with header")
            with open(self.file_path, 'wb') as f:
                # Write placeholder header (will be updated at end)
                header = self._create_wav_header(
                    self.sample_rate,
                    num_channels=1,
                    bits_per_sample=16,
                    data_size=self.DEFAULT_FILESIZE,
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

    def get_duration_ms(self):
        if self._start_time_ms <= 0:
            return 0
        return time.ticks_diff(time.ticks_ms(), self._start_time_ms)
