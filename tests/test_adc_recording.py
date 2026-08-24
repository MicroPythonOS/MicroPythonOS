# Test ADC Recording Integration
# Tests the new ADCRecordStream with adaptive frequency control

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
        
        sample_rate = 16000
        expected_data_size = int(0.2 * sample_rate * 2)
        expected_total_size = 44 + expected_data_size
        
        for attempt in range(3):
            if attempt > 0:
                print(f"Retry attempt {attempt + 1}...")
                try:
                    os.remove(self.test_file)
                except OSError:
                    pass

            duration_ms = 200 + attempt * 100
            print(f"Starting recording for {duration_ms}ms...")
            
            success = AudioManager.record_wav_adc(
                self.test_file, 
                duration_ms=duration_ms, 
                sample_rate=sample_rate
            )
            
            self.assertTrue(success, "AudioManager.record_wav_adc returned False")

            self.assertTrue(
                AudioManager.get()._active_sessions,
                "No active sessions — recording thread likely failed to start or crashed",
            )

            time.sleep(2 + attempt)

            try:
                st = os.stat(self.test_file)
                file_size = st[6]
            except OSError:
                file_size = 0

            if file_size > 44:
                break
        
        self.assertTrue(file_size > 0, f"Recording file {self.test_file} was not created")
        
        print(f"Created WAV file size: {file_size} bytes (Expected approx: {expected_total_size})")
        
        self.assertTrue(file_size > 44, "File contains only header or is empty")
        self.assertTrue(file_size > 1000, f"File size {file_size} seems too small (expected ~{expected_total_size})")

if __name__ == '__main__':
    unittest.main()
