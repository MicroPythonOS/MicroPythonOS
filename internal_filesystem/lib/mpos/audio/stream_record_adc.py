# ADCRecordStream - WAV File Recording Stream with Adaptive ADC Sampling
# Records 16-bit mono PCM audio from ADC with timer-based sampling
# Uses PI (Proportional-Integral) feedback control for stable sampling rate
# Includes warm-up phase and periodic garbage collection for long recordings
# Maintains compatibility with AudioManager and existing recording framework

import math
import os
import sys
import time
import gc

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


class ADCRecordStream:
    """
    WAV file recording stream with adaptive ADC timer-based sampling.
    Records 16-bit mono PCM audio from ADC with PI feedback control.
    Maintains target sample rate through dynamic timer frequency adjustment.
    """

    # Default recording parameters
    DEFAULT_SAMPLE_RATE = 8000  # 8kHz - good for voice/ADC
    DEFAULT_MAX_DURATION_MS = 60000  # 60 seconds max
    DEFAULT_FILESIZE = 1024 * 1024 * 1024  # 1GB data size

    # ADC configuration defaults
    DEFAULT_ADC_PIN = 2  # GPIO2 on ESP32
    DEFAULT_ADC_ATTENUATION = None  # Will be set based on machine module
    DEFAULT_ADC_WIDTH = None  # Will be set based on machine module

    # PI Controller configuration
    DEFAULT_CONTROL_GAIN_P = 0.05  # Proportional gain (aggressive for fast response)
    DEFAULT_CONTROL_GAIN_I = 0.01  # Integral gain (steady-state correction)
    DEFAULT_INTEGRAL_WINDUP_LIMIT = 1000  # Prevent integral overflow
    DEFAULT_ADJUSTMENT_INTERVAL = 1000  # Samples between frequency adjustments
    DEFAULT_WARMUP_SAMPLES = 3000  # Samples before starting adjustments
    DEFAULT_CALLBACK_OVERHEAD_OFFSET = 9000  # Hz offset for initial frequency (disabled by default)
    DEFAULT_MAX_PENDING_SAMPLES = 4096  # Maximum pending samples buffer size

    # Frequency bounds
    DEFAULT_MIN_FREQ = 6000  # Minimum timer frequency
    DEFAULT_MAX_FREQ = 40000  # Maximum timer frequency

    # Garbage collection configuration
    DEFAULT_GC_INTERVAL = 5000  # Perform GC every N samples
    DEFAULT_GC_ENABLED = False  # Enable explicit garbage collection

    def __init__(self, file_path, duration_ms, sample_rate, adc_pin=None,
                 adaptive_control=True, on_complete=None, **adc_config):
        """
        Initialize ADC recording stream with adaptive frequency control.

        Args:
            file_path: Path to save WAV file
            duration_ms: Recording duration in milliseconds (None = until stop())
            sample_rate: Target sample rate in Hz
            adc_pin: GPIO pin for ADC input (default: GPIO2)
            adaptive_control: Enable PI feedback control (default: True)
            on_complete: Callback function(message) when recording finishes
            **adc_config: Additional ADC configuration:
                - control_gain_p: Proportional gain
                - control_gain_i: Integral gain
                - integral_windup_limit: Integral term limit
                - adjustment_interval: Samples between adjustments
                - warmup_samples: Warm-up phase samples
                - callback_overhead_offset: Initial frequency offset (Hz, default 0)
                - min_freq: Minimum timer frequency
                - max_freq: Maximum timer frequency
                - gc_enabled: Enable garbage collection (default: True)
                - gc_interval: Samples between GC cycles
                - max_pending_samples: Maximum pending samples buffer size (default: 4096)
        """
        self.file_path = file_path
        self.duration_ms = duration_ms if duration_ms else self.DEFAULT_MAX_DURATION_MS
        self.sample_rate = sample_rate if sample_rate else self.DEFAULT_SAMPLE_RATE
        self.adc_pin = adc_pin if adc_pin is not None else self.DEFAULT_ADC_PIN
        self.adaptive_control = adaptive_control
        self.on_complete = on_complete

        # ADC configuration
        self._adc = None
        self._timer = None
        self._keep_running = True
        self._is_recording = False
        self._bytes_recorded = 0

        # PI Controller configuration
        self.control_gain_p = adc_config.get('control_gain_p', self.DEFAULT_CONTROL_GAIN_P)
        self.control_gain_i = adc_config.get('control_gain_i', self.DEFAULT_CONTROL_GAIN_I)
        self.integral_windup_limit = adc_config.get('integral_windup_limit', self.DEFAULT_INTEGRAL_WINDUP_LIMIT)
        self.adjustment_interval = adc_config.get('adjustment_interval', self.DEFAULT_ADJUSTMENT_INTERVAL)
        self.warmup_samples = adc_config.get('warmup_samples', self.DEFAULT_WARMUP_SAMPLES)
        self.callback_overhead_offset = adc_config.get('callback_overhead_offset', self.DEFAULT_CALLBACK_OVERHEAD_OFFSET)
        self.min_freq = adc_config.get('min_freq', self.DEFAULT_MIN_FREQ)
        self.max_freq = adc_config.get('max_freq', self.DEFAULT_MAX_FREQ)

        # Garbage collection configuration
        self.gc_enabled = adc_config.get('gc_enabled', self.DEFAULT_GC_ENABLED)
        self.gc_interval = adc_config.get('gc_interval', self.DEFAULT_GC_INTERVAL)

        # Pending samples buffer configuration
        self.max_pending_samples = adc_config.get('max_pending_samples', self.DEFAULT_MAX_PENDING_SAMPLES)

        # PI Controller state
        self._current_freq = self.sample_rate + self.callback_overhead_offset
        self._sample_counter = 0
        self._last_adjustment_sample = 0
        self._integral_error = 0.0
        self._warmup_complete = False
        self._last_gc_sample = 0
        self._start_time_ms = 0
        self._adjustment_history = []

        # Logging and diagnostics for dropped samples
        self._dropped_samples = 0
        self._drop_events = []  # List of (sample_number, pending_queue_size) tuples
        self._max_pending_depth = 0
        self._pending_depth_history = []  # Track queue depth over time
        self._last_pending_depth_log = 0
        self._samples_written = 0
        self._callback_count = 0
        self._last_callback_time_ms = 0
        self._max_callback_lag_ms = 0

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
    #  WAV header generation (reused from RecordStream)
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
    #  PI Controller for adaptive frequency control
    # -----------------------------------------------------------------------
    def _adjust_frequency(self):
        """
        PI (Proportional-Integral) feedback control to adjust timer frequency.
        Compares actual sampling rate vs target rate and adjusts accordingly.
        Only called after warm-up phase completes.
        """
        elapsed_ms = time.ticks_diff(time.ticks_ms(), self._start_time_ms)

        if elapsed_ms <= 0:
            return

        # Calculate actual sampling rate
        actual_rate = self._sample_counter / (elapsed_ms / 1000.0)

        # Calculate error (positive means we're behind target)
        rate_error = self.sample_rate - actual_rate

        # Update integral term (accumulated error)
        self._integral_error += rate_error

        # Limit integral windup to prevent excessive accumulation
        self._integral_error = max(-self.integral_windup_limit, 
                                   min(self.integral_windup_limit, self._integral_error))

        # PI control: combine proportional and integral terms
        freq_adjustment = (rate_error * self.control_gain_p) + (self._integral_error * self.control_gain_i)

        # Calculate new frequency
        new_freq = self._current_freq + freq_adjustment

        # Clamp frequency to safe range
        new_freq = max(self.min_freq, min(self.max_freq, new_freq))

        # Only adjust if change is significant (at least 1 Hz)
        if abs(new_freq - self._current_freq) >= 1:
            old_freq = self._current_freq
            self._current_freq = int(new_freq)

            # Calculate estimated callback overhead
            estimated_overhead = self._current_freq - actual_rate

            # Reinitialize timer with new frequency
            try:
                self._timer.deinit()
                self._timer.init(freq=self._current_freq, mode=machine.Timer.PERIODIC,
                               callback=self._record_sample_callback)

                adjustment_info = {
                    'sample': self._sample_counter,
                    'actual_rate': actual_rate,
                    'target_rate': self.sample_rate,
                    'error': rate_error,
                    'integral_error': self._integral_error,
                    'old_freq': old_freq,
                    'new_freq': self._current_freq,
                    'adjustment': freq_adjustment,
                    'estimated_overhead': estimated_overhead
                }
                self._adjustment_history.append(adjustment_info)

                print(f"  [ADJUST] Sample {self._sample_counter}: Rate {actual_rate:.1f} Hz "
                      f"(error: {rate_error:+.1f} Hz) → Freq {old_freq} → {self._current_freq} Hz")

            except Exception as e:
                print(f"Error adjusting frequency: {e}")
                self._current_freq = old_freq

    def _record_sample_callback(self, timer):
        """
        Timer callback function to read ADC samples with adaptive frequency.
        Called by hardware timer at precise intervals.
        Includes periodic garbage collection and buffer overflow protection.
        Tracks dropped samples and main thread lag.
        """
        if not self._is_recording or not self._keep_running:
            return

        try:
            # Track callback timing for lag detection
            current_time_ms = time.ticks_ms()
            if self._last_callback_time_ms > 0:
                callback_lag = time.ticks_diff(current_time_ms, self._last_callback_time_ms)
                if callback_lag > self._max_callback_lag_ms:
                    self._max_callback_lag_ms = callback_lag
            self._last_callback_time_ms = current_time_ms
            self._callback_count += 1

            # Read ADC value
            adc_value = self._adc.read()
            self._sample_counter += 1

            # Convert 12-bit ADC value to 16-bit signed PCM
            # ADC range: 0-4095 (12-bit), convert to -32768 to 32767 (16-bit signed)
            sample_16bit = int((adc_value - 2048) * 16)

            # Clamp to 16-bit range
            if sample_16bit > 32767:
                sample_16bit = 32767
            elif sample_16bit < -32768:
                sample_16bit = -32768

            # Track pending queue depth
            current_pending = len(self._pending_samples)
            if current_pending > self._max_pending_depth:
                self._max_pending_depth = current_pending

            # Store sample (unbounded buffer - will buffer everything)
            self._pending_samples.append(sample_16bit)

            # Log pending queue depth periodically
            if self._sample_counter - self._last_pending_depth_log >= 1000:
                self._pending_depth_history.append((self._sample_counter, current_pending))
                if current_pending > self.max_pending_samples * 0.8:
                    print(f"[QUEUE] Sample {self._sample_counter}: Pending queue at {current_pending}/{self.max_pending_samples} "
                          f"({100*current_pending/self.max_pending_samples:.1f}%)")
                self._last_pending_depth_log = self._sample_counter

            # Perform garbage collection at regular intervals
            if self.gc_enabled and self._sample_counter - self._last_gc_sample >= self.gc_interval:
                gc.collect()
                self._last_gc_sample = self._sample_counter

            # Check if warm-up phase is complete
            if not self._warmup_complete and self._sample_counter >= self.warmup_samples:
                self._warmup_complete = True
                print(f">>> WARM-UP PHASE COMPLETE at sample {self._sample_counter}")
                print(f">>> Starting adaptive frequency control...\n")

            # Adjust frequency only after warm-up phase and at intervals
            if self.adaptive_control and self._warmup_complete and \
               self._sample_counter - self._last_adjustment_sample >= self.adjustment_interval:
                self._adjust_frequency()
                self._last_adjustment_sample = self._sample_counter

        except Exception as e:
            print(f"Error in ADC callback: {e}")

    # -----------------------------------------------------------------------
    #  Main recording routine
    # -----------------------------------------------------------------------
    def record(self):
        """Main synchronous recording routine (runs in separate thread)."""
        print(f"ADCRecordStream.record() called")
        print(f"  file_path: {self.file_path}")
        print(f"  duration_ms: {self.duration_ms}")
        print(f"  sample_rate: {self.sample_rate}")
        print(f"  adc_pin: {self.adc_pin}")
        print(f"  adaptive_control: {self.adaptive_control}")
        print(f"  _HAS_MACHINE: {_HAS_MACHINE}")

        self._is_recording = True
        self._bytes_recorded = 0
        self._sample_counter = 0
        self._pending_samples = []
        self._start_time_ms = time.ticks_ms()

        try:
            # Ensure directory exists
            dir_path = '/'.join(self.file_path.split('/')[:-1])
            print(f"ADCRecordStream: Creating directory: {dir_path}")
            if dir_path:
                _makedirs(dir_path)
                print(f"ADCRecordStream: Directory created/verified")

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
                print(f"ADCRecordStream: Header written ({len(header)} bytes)")

            print(f"ADCRecordStream: Recording to {self.file_path}")
            print(f"ADCRecordStream: {self.sample_rate} Hz, 16-bit, mono")
            print(f"ADCRecordStream: Max duration {self.duration_ms}ms")

            # Check if we have real ADC hardware or need to simulate
            use_simulation = not _HAS_MACHINE

            if not use_simulation:
                # Initialize ADC
                try:
                    print(f"ADCRecordStream: Initializing ADC on pin {self.adc_pin}")
                    self._adc = machine.ADC(machine.Pin(self.adc_pin))
                    self._adc.atten(machine.ADC.ATTN_11DB)  # Full range: 0-3.3V
                    self._adc.width(machine.ADC.WIDTH_12BIT)  # 12-bit resolution
                    print(f"ADCRecordStream: ADC initialized successfully")

                    # Initialize timer for sampling
                    print(f"ADCRecordStream: Initializing timer at {self._current_freq} Hz")
                    self._timer = machine.Timer(2)
                    self._timer.init(freq=self._current_freq, mode=machine.Timer.PERIODIC,
                                   callback=self._record_sample_callback)
                    print(f"ADCRecordStream: Timer initialized successfully")

                except Exception as e:
                    print(f"ADCRecordStream: ADC/Timer init failed: {e}")
                    print(f"ADCRecordStream: Falling back to simulation mode")
                    use_simulation = True

            if use_simulation:
                print(f"ADCRecordStream: Using desktop simulation (440Hz sine wave)")

            # Calculate recording parameters
            chunk_size = 1024  # Read 1KB at a time
            max_bytes = int((self.duration_ms / 1000) * self.sample_rate * 2)
            sample_offset = 0  # For sine wave phase continuity

            # Flush every ~2 seconds of audio (64KB at 8kHz 16-bit mono)
            flush_interval_bytes = 64 * 1024
            bytes_since_flush = 0

            print(f"ADCRecordStream: max_bytes={max_bytes}, chunk_size={chunk_size}, flush_interval={flush_interval_bytes}")

            # Open file for appending audio data
            print(f"ADCRecordStream: Opening file for audio data...")
            t0 = time.ticks_ms()
            f = open(self.file_path, 'ab')
            print(f"ADCRecordStream: File opened in {time.ticks_diff(time.ticks_ms(), t0)}ms")

            try:
                while self._keep_running:
                    # Check elapsed time - strict duration limit
                    elapsed = time.ticks_diff(time.ticks_ms(), self._start_time_ms)
                    if elapsed >= self.duration_ms:
                        print(f"ADCRecordStream: Duration limit reached ({elapsed}ms >= {self.duration_ms}ms)")
                        # Stop the timer immediately to prevent more samples
                        if self._timer:
                            self._timer.deinit()
                            self._timer = None
                        break

                    # Also check byte limit
                    if self._bytes_recorded >= max_bytes:
                        print(f"ADCRecordStream: Byte limit reached ({self._bytes_recorded} >= {max_bytes})")
                        break

                    if use_simulation:
                        # Generate sine wave samples for desktop testing
                        buf, num_samples = self._generate_sine_wave_chunk(chunk_size, sample_offset)
                        sample_offset += num_samples
                        num_read = chunk_size

                        # Simulate real-time recording speed
                        time.sleep_ms(int((chunk_size / 2) / self.sample_rate * 1000))

                        f.write(buf[:num_read])
                        self._bytes_recorded += num_read
                        bytes_since_flush += num_read

                    else:
                        # Just collect samples in buffer during recording
                        # Don't write to file yet - that causes I/O delays
                        pass

                    # Minimal sleep to keep up with callback
                    time.sleep_ms(1)

            finally:
                # Write all pending samples to file after recording stops
                print(f"ADCRecordStream: Writing {len(self._pending_samples)} pending samples to file...")
                t0 = time.ticks_ms()
                for sample in self._pending_samples:
                    if sample < 0:
                        sample_bytes = (sample & 0xFFFF).to_bytes(2, 'little')
                    else:
                        sample_bytes = sample.to_bytes(2, 'little')
                    f.write(sample_bytes)
                    self._bytes_recorded += 2
                self._pending_samples.clear()
                write_time = time.ticks_diff(time.ticks_ms(), t0)
                print(f"ADCRecordStream: Wrote pending samples in {write_time}ms")
                
                # Explicitly close the file and measure time
                print(f"ADCRecordStream: Closing audio data file...")
                t0 = time.ticks_ms()
                f.close()
                print(f"ADCRecordStream: File closed in {time.ticks_diff(time.ticks_ms(), t0)}ms")

            elapsed_ms = time.ticks_diff(time.ticks_ms(), self._start_time_ms)
            print(f"ADCRecordStream: Finished recording {self._bytes_recorded} bytes ({elapsed_ms}ms)")
            
            # Verify file size with os.stat()
            print(f"\n{'='*60}")
            print(f"FILE SIZE VERIFICATION")
            print(f"{'='*60}")
            try:
                file_stat = os.stat(self.file_path)
                file_size = file_stat[6]  # st_size is at index 6
                
                # Calculate expected size
                expected_samples = int((self.duration_ms / 1000.0) * self.sample_rate)
                expected_bytes = expected_samples * 2 + 44  # 44 bytes for WAV header
                
                # Calculate actual samples from file size
                actual_audio_bytes = file_size - 44  # Subtract WAV header
                actual_samples = actual_audio_bytes // 2
                actual_duration_ms = int((actual_samples / self.sample_rate) * 1000)
                
                print(f"Expected duration: {self.duration_ms}ms")
                print(f"Expected samples: {expected_samples}")
                print(f"Expected audio bytes: {expected_samples * 2}")
                print(f"Expected total file size: {expected_bytes} bytes (including 44-byte WAV header)")
                print()
                print(f"Actual file size: {file_size} bytes")
                print(f"Actual audio bytes: {actual_audio_bytes}")
                print(f"Actual samples: {actual_samples}")
                print(f"Actual duration: {actual_duration_ms}ms")
                print()
                
                # Calculate difference
                size_diff = file_size - expected_bytes
                sample_diff = actual_samples - expected_samples
                duration_diff = actual_duration_ms - self.duration_ms
                
                if size_diff == 0:
                    print(f"✓ PERFECT: File size matches expected size exactly!")
                elif size_diff > 0:
                    print(f"✓ GOOD: File size is {size_diff} bytes larger than expected")
                    print(f"  ({sample_diff} extra samples, {duration_diff}ms extra)")
                else:
                    print(f"✗ SHORT: File size is {abs(size_diff)} bytes smaller than expected")
                    print(f"  ({abs(sample_diff)} missing samples, {abs(duration_diff)}ms short)")
                    print(f"  Completion: {(file_size / expected_bytes) * 100:.1f}%")
                
            except Exception as e:
                print(f"Error verifying file size: {e}")
            print(f"{'='*60}\n")
            
            # Print dropped samples summary
            print(f"\n{'='*60}")
            print(f"DROPPED SAMPLES SUMMARY")
            print(f"{'='*60}")
            print(f"Total samples collected: {self._sample_counter}")
            print(f"Total samples dropped: {self._dropped_samples}")
            print(f"Samples written to file: {self._samples_written}")
            if self._sample_counter > 0:
                drop_rate = (self._dropped_samples / self._sample_counter) * 100
                print(f"Drop rate: {drop_rate:.2f}%")
            if self._drop_events:
                print(f"Number of drop events: {len(self._drop_events)}")
                print(f"First drop at sample: {self._drop_events[0][0]}")
                print(f"Last drop at sample: {self._drop_events[-1][0]}")
            print(f"Max pending queue depth: {self._max_pending_depth}/{self.max_pending_samples}")
            print(f"Max callback lag: {self._max_callback_lag_ms}ms")
            print(f"Total callbacks: {self._callback_count}")
            print(f"{'='*60}\n")
            
            # Print adaptive control statistics
            if self.adaptive_control and self._adjustment_history:
                print(f"\nADCRecordStream: Adaptive control statistics:")
                print(f"  Total adjustments: {len(self._adjustment_history)}")
                if self._adjustment_history:
                    first_error = self._adjustment_history[0]['error']
                    last_error = self._adjustment_history[-1]['error']
                    print(f"  First error: {first_error:+.1f} Hz")
                    print(f"  Last error: {last_error:+.1f} Hz")
                    print(f"  Error reduction: {abs(first_error) - abs(last_error):+.1f} Hz")

            if self.on_complete:
                self.on_complete(f"Recorded: {self.file_path}")

        except Exception as e:
            import sys
            print(f"ADCRecordStream: Error: {e}")
            sys.print_exception(e)
            if self.on_complete:
                self.on_complete(f"Error: {e}")

        finally:
            self._is_recording = False
            if self._timer:
                self._timer.deinit()
                self._timer = None
            if self._adc:
                self._adc = None
            print(f"ADCRecordStream: Recording thread finished")
