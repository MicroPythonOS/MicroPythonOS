# Test ADC Recording Integration
# Tests the new ADCRecordStream with adaptive frequency control
# Run with: ./MicroPythonOS/tests/unittest.sh MicroPythonOS/tests/test_adc_recording.py

import unittest
import time
import os
import sys

# Add lib path for imports
# In MicroPython, os.path doesn't exist, so we construct the path manually
test_dir = __file__.rsplit('/', 1)[0] if '/' in __file__ else '.'
lib_path = test_dir + '/../internal_filesystem/lib'
sys.path.insert(0, lib_path)

from mpos.audio.stream_record_adc import ADCRecordStream


class TestADCRecordStream(unittest.TestCase):
    """Test ADCRecordStream with adaptive frequency control."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = "data/test_adc"
        self.test_file = f"{self.test_dir}/test_recording.wav"
        
        # Create test directory
        try:
            os.makedirs(self.test_dir, exist_ok=True)
        except:
            pass

    def tearDown(self):
        """Clean up test files."""
        try:
            if os.path.exists(self.test_file):
                os.remove(self.test_file)
        except:
            pass

    def test_adc_stream_initialization(self):
        """Test ADCRecordStream initialization."""
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=1000,
            sample_rate=8000,
            adc_pin=2
        )
        
        self.assertEqual(stream.file_path, self.test_file)
        self.assertEqual(stream.duration_ms, 1000)
        self.assertEqual(stream.sample_rate, 8000)
        self.assertEqual(stream.adc_pin, 2)
        self.assertFalse(stream.is_recording())

    def test_adc_stream_defaults(self):
        """Test ADCRecordStream default parameters."""
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=None,
            sample_rate=None
        )
        
        self.assertEqual(stream.duration_ms, ADCRecordStream.DEFAULT_MAX_DURATION_MS)
        self.assertEqual(stream.sample_rate, ADCRecordStream.DEFAULT_SAMPLE_RATE)
        self.assertEqual(stream.adc_pin, ADCRecordStream.DEFAULT_ADC_PIN)

    def test_pi_controller_defaults(self):
        """Test PI controller default parameters."""
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=1000,
            sample_rate=8000
        )
        
        self.assertEqual(stream.control_gain_p, ADCRecordStream.DEFAULT_CONTROL_GAIN_P)
        self.assertEqual(stream.control_gain_i, ADCRecordStream.DEFAULT_CONTROL_GAIN_I)
        self.assertEqual(stream.integral_windup_limit, ADCRecordStream.DEFAULT_INTEGRAL_WINDUP_LIMIT)
        self.assertEqual(stream.adjustment_interval, ADCRecordStream.DEFAULT_ADJUSTMENT_INTERVAL)
        self.assertEqual(stream.warmup_samples, ADCRecordStream.DEFAULT_WARMUP_SAMPLES)

    def test_custom_pi_parameters(self):
        """Test custom PI controller parameters."""
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=1000,
            sample_rate=8000,
            control_gain_p=0.1,
            control_gain_i=0.02,
            integral_windup_limit=500,
            adjustment_interval=500,
            warmup_samples=1000
        )
        
        self.assertEqual(stream.control_gain_p, 0.1)
        self.assertEqual(stream.control_gain_i, 0.02)
        self.assertEqual(stream.integral_windup_limit, 500)
        self.assertEqual(stream.adjustment_interval, 500)
        self.assertEqual(stream.warmup_samples, 1000)

    def test_wav_header_creation(self):
        """Test WAV header generation."""
        header = ADCRecordStream._create_wav_header(
            sample_rate=8000,
            num_channels=1,
            bits_per_sample=16,
            data_size=16000
        )
        
        # Check header size
        self.assertEqual(len(header), 44)
        
        # Check RIFF signature
        self.assertEqual(header[0:4], b'RIFF')
        
        # Check WAVE signature
        self.assertEqual(header[8:12], b'WAVE')
        
        # Check fmt signature
        self.assertEqual(header[12:16], b'fmt ')
        
        # Check data signature
        self.assertEqual(header[36:40], b'data')

    def test_wav_header_sample_rate(self):
        """Test WAV header contains correct sample rate."""
        sample_rate = 16000
        header = ADCRecordStream._create_wav_header(
            sample_rate=sample_rate,
            num_channels=1,
            bits_per_sample=16,
            data_size=32000
        )
        
        # Sample rate is at offset 24-28 (little-endian)
        header_sample_rate = int.from_bytes(header[24:28], 'little')
        self.assertEqual(header_sample_rate, sample_rate)

    def test_wav_header_data_size(self):
        """Test WAV header contains correct data size."""
        data_size = 32000
        header = ADCRecordStream._create_wav_header(
            sample_rate=8000,
            num_channels=1,
            bits_per_sample=16,
            data_size=data_size
        )
        
        # Data size is at offset 40-44 (little-endian)
        header_data_size = int.from_bytes(header[40:44], 'little')
        self.assertEqual(header_data_size, data_size)

    def test_sine_wave_generation(self):
        """Test sine wave generation for desktop simulation."""
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=1000,
            sample_rate=8000
        )
        
        # Generate 1KB of sine wave
        buf, num_samples = stream._generate_sine_wave_chunk(1024, 0)
        
        self.assertEqual(len(buf), 1024)
        self.assertEqual(num_samples, 512)  # 1024 bytes / 2 bytes per sample

    def test_sine_wave_phase_continuity(self):
        """Test sine wave phase continuity across chunks."""
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=1000,
            sample_rate=8000
        )
        
        # Generate two chunks
        buf1, num_samples1 = stream._generate_sine_wave_chunk(1024, 0)
        buf2, num_samples2 = stream._generate_sine_wave_chunk(1024, num_samples1)
        
        # Both should have same number of samples
        self.assertEqual(num_samples1, num_samples2)
        
        # Buffers should be different (different phase)
        self.assertNotEqual(buf1, buf2)

    def test_stop_recording(self):
        """Test stop() method."""
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=10000,
            sample_rate=8000
        )
        
        self.assertTrue(stream._keep_running)
        stream.stop()
        self.assertFalse(stream._keep_running)

    def test_elapsed_time_calculation(self):
        """Test elapsed time calculation."""
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=1000,
            sample_rate=8000
        )
        
        # Simulate recording 1 second of audio
        # 8000 samples * 2 bytes per sample = 16000 bytes
        stream._bytes_recorded = 16000
        
        elapsed_ms = stream.get_elapsed_ms()
        self.assertEqual(elapsed_ms, 1000)

    def test_adaptive_control_disabled(self):
        """Test creating stream with adaptive control disabled."""
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=1000,
            sample_rate=8000,
            adaptive_control=False
        )
        
        self.assertFalse(stream.adaptive_control)

    def test_gc_configuration(self):
        """Test garbage collection configuration."""
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=1000,
            sample_rate=8000,
            gc_enabled=True,
            gc_interval=3000
        )
        
        self.assertTrue(stream.gc_enabled)
        self.assertEqual(stream.gc_interval, 3000)

    def test_max_pending_samples(self):
        """Test max pending samples buffer configuration."""
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=1000,
            sample_rate=8000,
            max_pending_samples=8192
        )
        
        self.assertEqual(stream.max_pending_samples, 8192)

    def test_frequency_bounds(self):
        """Test frequency bounds configuration."""
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=1000,
            sample_rate=8000,
            min_freq=5000,
            max_freq=50000
        )
        
        self.assertEqual(stream.min_freq, 5000)
        self.assertEqual(stream.max_freq, 50000)

    def test_callback_overhead_offset(self):
        """Test callback overhead offset configuration."""
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=1000,
            sample_rate=8000,
            callback_overhead_offset=3000
        )
        
        self.assertEqual(stream.callback_overhead_offset, 3000)
        # Initial frequency should be target sample rate (offset is only used if needed)
        self.assertEqual(stream._current_freq, 8000)

    def test_on_complete_callback(self):
        """Test on_complete callback is stored."""
        def callback(msg):
            pass
        
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=1000,
            sample_rate=8000,
            on_complete=callback
        )
        
        self.assertEqual(stream.on_complete, callback)

    def test_multiple_streams_independent(self):
        """Test multiple ADCRecordStream instances are independent."""
        stream1 = ADCRecordStream(
            file_path=f"{self.test_dir}/test1.wav",
            duration_ms=1000,
            sample_rate=8000
        )
        
        stream2 = ADCRecordStream(
            file_path=f"{self.test_dir}/test2.wav",
            duration_ms=2000,
            sample_rate=16000
        )
        
        self.assertNotEqual(stream1.file_path, stream2.file_path)
        self.assertNotEqual(stream1.duration_ms, stream2.duration_ms)
        self.assertNotEqual(stream1.sample_rate, stream2.sample_rate)

    def test_pi_controller_state_initialization(self):
        """Test PI controller state is properly initialized."""
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=1000,
            sample_rate=8000
        )
        
        self.assertEqual(stream._sample_counter, 0)
        self.assertEqual(stream._integral_error, 0.0)
        self.assertFalse(stream._warmup_complete)
        self.assertEqual(len(stream._adjustment_history), 0)

    def test_desktop_simulation_mode(self):
        """Test desktop simulation mode (no machine module)."""
        # This test verifies the stream can be created even without machine module
        stream = ADCRecordStream(
            file_path=self.test_file,
            duration_ms=1000,
            sample_rate=8000
        )
        
        # Should not raise exception
        self.assertIsNotNone(stream)


class TestADCIntegrationWithAudioManager(unittest.TestCase):
    """Test ADC recording integration with AudioManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = "data/test_adc_manager"
        self.test_file = f"{self.test_dir}/test_recording.wav"
        
        try:
            os.makedirs(self.test_dir, exist_ok=True)
        except:
            pass

    def tearDown(self):
        """Clean up test files."""
        try:
            if os.path.exists(self.test_file):
                os.remove(self.test_file)
        except:
            pass

    def test_adc_stream_import(self):
        """Test ADCRecordStream can be imported."""
        try:
            from mpos.audio.stream_record_adc import ADCRecordStream
            self.assertIsNotNone(ADCRecordStream)
        except ImportError as e:
            self.fail(f"Failed to import ADCRecordStream: {e}")

    def test_audio_manager_has_adc_method(self):
        """Test AudioManager has record_wav_adc method."""
        try:
            from mpos import AudioManager
            self.assertTrue(hasattr(AudioManager, 'record_wav_adc'))
        except ImportError:
            self.skipTest("AudioManager not available in test environment")


if __name__ == '__main__':
    unittest.main()
