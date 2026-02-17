# Test ADC Recording Integration
# Tests the new ADCRecordStream with adaptive frequency control
# Run with: ./MicroPythonOS/tests/unittest.sh MicroPythonOS/tests/test_adc_recording.py

import unittest
import time
import os
import sys

# Add lib path for imports
# In MicroPython, os.path doesn't exist, so we construct the path manually
# This assumes the test is run from the project root or via unittest.sh
sys.path.append('MicroPythonOS/internal_filesystem/lib')

from mpos import AudioManager

class TestADCRecording(unittest.TestCase):
    """Test ADC recording functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_file = "test_recording.wav"
        
        # Ensure AudioManager is initialized (mocking pins if needed)
        # On desktop, it will use simulation mode
        if not AudioManager._instance:
            # Initialize with dummy values if needed, but adc_mic_pin is supported
            AudioManager(adc_mic_pin=1)

    def tearDown(self):
        """Clean up test files."""
        try:
            os.remove(self.test_file)
        except:
            pass

    def test_record_wav_adc(self):
        """Test recording a short WAV file using ADC."""
        
        # Record for 200ms
        duration_ms = 200
        sample_rate = 16000
        
        print(f"Starting recording for {duration_ms}ms...")
        
        # Start recording
        # Note: On desktop this will use the simulation mode in ADCRecordStream
        success = AudioManager.record_wav_adc(
            self.test_file, 
            duration_ms=duration_ms, 
            sample_rate=sample_rate
        )
        
        self.assertTrue(success, "AudioManager.record_wav_adc returned False")
        
        # Wait for recording to finish (plus a buffer for thread startup/shutdown)
        # Simulation mode might be slower or faster depending on system load
        time.sleep(duration_ms / 1000.0 + 1.0)
        
        # Verify file exists
        try:
            st = os.stat(self.test_file)
            file_size = st[6]
            file_exists = True
        except OSError:
            file_exists = False
            file_size = 0
            
        self.assertTrue(file_exists, f"Recording file {self.test_file} was not created")
        
        # Verify file size is reasonable
        # Header is 44 bytes
        # 200ms at 16000Hz, 16-bit mono = 0.2 * 16000 * 2 = 6400 bytes
        # Total should be around 6444 bytes
        
        expected_data_size = int(duration_ms / 1000.0 * sample_rate * 2)
        expected_total_size = 44 + expected_data_size
        
        print(f"Created WAV file size: {file_size} bytes (Expected approx: {expected_total_size})")
        
        self.assertTrue(file_size > 44, "File contains only header or is empty")
        
        # Allow some margin of error for timing differences in test environment
        # But it should have recorded *something* significant
        self.assertTrue(file_size > 1000, f"File size {file_size} seems too small (expected ~{expected_total_size})")

if __name__ == '__main__':
    unittest.main()
