# AudioManager - Core Audio Management Service
# Centralized audio routing with priority-based audio focus (Android-inspired)
# Supports I2S (digital audio) and PWM buzzer (tones/ringtones)
#
# Simple routing: play_wav() -> I2S, play_rtttl() -> buzzer, record_wav() -> I2S mic
# Uses _thread for non-blocking background playback/recording (separate thread from UI)

import _thread
from ..task_manager import TaskManager


class AudioManager:
    """
    Centralized audio management service with priority-based audio focus.
    Implements singleton pattern for single audio service instance.
    
    Usage:
        from mpos import AudioManager
        
        # Direct class method calls (no .get() needed)
        AudioManager.init(i2s_pins=pins, buzzer_instance=buzzer)
        AudioManager.play_wav("music.wav", stream_type=AudioManager.STREAM_MUSIC)
        AudioManager.set_volume(80)
        volume = AudioManager.get_volume()
        AudioManager.stop()
    """
    
    # Stream type constants (priority order: higher number = higher priority)
    STREAM_MUSIC = 0         # Background music (lowest priority)
    STREAM_NOTIFICATION = 1  # Notification sounds (medium priority)
    STREAM_ALARM = 2         # Alarms/alerts (highest priority)
    
    _instance = None  # Singleton instance
    
    def __init__(self, i2s_pins=None, buzzer_instance=None, adc_mic_pin=None):
        """
        Initialize AudioManager instance with optional hardware configuration.

        Args:
            i2s_pins: Dict with 'sck', 'ws', 'sd' pin numbers (for I2S/WAV playback)
            buzzer_instance: PWM instance for buzzer (for RTTTL playback)
            adc_mic_pin: GPIO pin number for ADC microphone (for ADC recording)
        """
        if AudioManager._instance:
            return
        AudioManager._instance = self

        self._i2s_pins = i2s_pins              # I2S pin configuration dict (created per-stream)
        self._buzzer_instance = buzzer_instance # PWM buzzer instance
        self._adc_mic_pin = adc_mic_pin         # ADC microphone pin
        self._current_stream = None             # Currently playing stream
        self._current_recording = None          # Currently recording stream
        self._volume = 50                       # System volume (0-100)

        # Build status message
        capabilities = []
        if i2s_pins:
            capabilities.append("I2S (WAV)")
        if buzzer_instance:
            capabilities.append("Buzzer (RTTTL)")
        if adc_mic_pin:
            capabilities.append(f"ADC Mic (Pin {adc_mic_pin})")
        
        if capabilities:
            print(f"AudioManager initialized: {', '.join(capabilities)}")
        else:
            print("AudioManager initialized: No audio hardware")

    @classmethod
    def get(cls):
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def has_i2s(self):
        """Check if I2S audio is available for WAV playback."""
        return self._i2s_pins is not None

    def has_buzzer(self):
        """Check if buzzer is available for RTTTL playback."""
        return self._buzzer_instance is not None

    def has_microphone(self):
        """Check if microphone (I2S or ADC) is available for recording."""
        has_i2s_mic = self._i2s_pins is not None and 'sd_in' in self._i2s_pins
        has_adc_mic = self._adc_mic_pin is not None
        return has_i2s_mic or has_adc_mic

    def _check_audio_focus(self, stream_type):
        """
        Check if a stream with the given type can start playback.
        Implements priority-based audio focus (Android-inspired).

        Args:
            stream_type: Stream type (STREAM_MUSIC, STREAM_NOTIFICATION, STREAM_ALARM)

        Returns:
            bool: True if stream can start, False if rejected
        """
        if not self._current_stream:
            return True  # No stream playing, OK to start

        if not self._current_stream.is_playing():
            return True  # Current stream finished, OK to start

        # Check priority
        if stream_type <= self._current_stream.stream_type:
            print(f"AudioManager: Stream rejected (priority {stream_type} <= current {self._current_stream.stream_type})")
            return False

        # Higher priority stream - interrupt current
        print(f"AudioManager: Interrupting stream (priority {stream_type} > current {self._current_stream.stream_type})")
        self._current_stream.stop()
        return True

    def _playback_thread(self, stream):
        """
        Thread function for audio playback.
        Runs in a separate thread to avoid blocking the UI.

        Args:
            stream: Stream instance (WAVStream or RTTTLStream)
        """
        self._current_stream = stream

        try:
            # Run synchronous playback in this thread
            stream.play()
        except Exception as e:
            print(f"AudioManager: Playback error: {e}")
        finally:
            # Clear current stream
            if self._current_stream == stream:
                self._current_stream = None

    def play_wav(self, file_path, stream_type=None, volume=None, on_complete=None):
        """
        Play WAV file via I2S.

        Args:
            file_path: Path to WAV file (e.g., "M:/sdcard/music/song.wav")
            stream_type: Stream type (STREAM_MUSIC, STREAM_NOTIFICATION, STREAM_ALARM)
            volume: Override volume (0-100), or None to use system volume
            on_complete: Callback function(message) called when playback finishes

        Returns:
            bool: True if playback started, False if rejected or unavailable
        """
        if stream_type is None:
            stream_type = self.STREAM_MUSIC
            
        if not self._i2s_pins:
            print("AudioManager: play_wav() failed - I2S not configured")
            return False

        # Check audio focus
        if not self._check_audio_focus(stream_type):
            return False

        # Create stream and start playback in separate thread
        try:
            from mpos.audio.stream_wav import WAVStream

            stream = WAVStream(
                file_path=file_path,
                stream_type=stream_type,
                volume=volume if volume is not None else self._volume,
                i2s_pins=self._i2s_pins,
                on_complete=on_complete
            )

            _thread.stack_size(TaskManager.good_stack_size())
            _thread.start_new_thread(self._playback_thread, (stream,))
            return True

        except Exception as e:
            print(f"AudioManager: play_wav() failed: {e}")
            return False

    def play_rtttl(self, rtttl_string, stream_type=None, volume=None, on_complete=None):
        """
        Play RTTTL ringtone via buzzer.

        Args:
            rtttl_string: RTTTL format string (e.g., "Nokia:d=4,o=5,b=225:8e6,8d6...")
            stream_type: Stream type (STREAM_MUSIC, STREAM_NOTIFICATION, STREAM_ALARM)
            volume: Override volume (0-100), or None to use system volume
            on_complete: Callback function(message) called when playback finishes

        Returns:
            bool: True if playback started, False if rejected or unavailable
        """
        if stream_type is None:
            stream_type = self.STREAM_NOTIFICATION
            
        if not self._buzzer_instance:
            print("AudioManager: play_rtttl() failed - buzzer not configured")
            return False

        # Check audio focus
        if not self._check_audio_focus(stream_type):
            return False

        # Create stream and start playback in separate thread
        try:
            from mpos.audio.stream_rtttl import RTTTLStream

            stream = RTTTLStream(
                rtttl_string=rtttl_string,
                stream_type=stream_type,
                volume=volume if volume is not None else self._volume,
                buzzer_instance=self._buzzer_instance,
                on_complete=on_complete
            )

            _thread.stack_size(TaskManager.good_stack_size())
            _thread.start_new_thread(self._playback_thread, (stream,))
            return True

        except Exception as e:
            print(f"AudioManager: play_rtttl() failed: {e}")
            return False

    def _recording_thread(self, stream):
        """
        Thread function for audio recording.
        Runs in a separate thread to avoid blocking the UI.

        Args:
            stream: RecordStream instance
        """
        self._current_recording = stream

        try:
            # Run synchronous recording in this thread
            stream.record()
        except Exception as e:
            print(f"AudioManager: Recording error: {e}")
        finally:
            # Clear current recording
            if self._current_recording == stream:
                self._current_recording = None

    def record_wav(self, file_path, duration_ms=None, on_complete=None, sample_rate=16000):
        """
        Record audio from I2S microphone to WAV file.

        Args:
            file_path: Path to save WAV file (e.g., "data/recording.wav")
            duration_ms: Recording duration in milliseconds (None = 60 seconds default)
            on_complete: Callback function(message) when recording finishes
            sample_rate: Sample rate in Hz (default 16000 for voice)

        Returns:
            bool: True if recording started, False if rejected or unavailable
        """
        print(f"AudioManager.record_wav() called")
        print(f"  file_path: {file_path}")
        print(f"  duration_ms: {duration_ms}")
        print(f"  sample_rate: {sample_rate}")
        print(f"  _i2s_pins: {self._i2s_pins}")
        print(f"  has_microphone(): {self.has_microphone()}")

        if not self.has_microphone():
            print("AudioManager: record_wav() failed - microphone not configured")
            return False

        # Cannot record while playing (I2S can only be TX or RX, not both)
        if self.is_playing():
            print("AudioManager: Cannot record while playing")
            return False

        # Cannot start new recording while already recording
        if self.is_recording():
            print("AudioManager: Already recording")
            return False

        # Create stream and start recording in separate thread
        try:
            print("AudioManager: Importing RecordStream...")
            from mpos.audio.stream_record import RecordStream

            print("AudioManager: Creating RecordStream instance...")
            stream = RecordStream(
                file_path=file_path,
                duration_ms=duration_ms,
                sample_rate=sample_rate,
                i2s_pins=self._i2s_pins,
                on_complete=on_complete
            )

            print("AudioManager: Starting recording thread...")
            _thread.stack_size(TaskManager.good_stack_size())
            _thread.start_new_thread(self._recording_thread, (stream,))
            print("AudioManager: Recording thread started successfully")
            return True

        except Exception as e:
            import sys
            print(f"AudioManager: record_wav() failed: {e}")
            sys.print_exception(e)
            return False

    def record_wav_adc(self, file_path, duration_ms=None, adc_pin=None, sample_rate=16000,
                       on_complete=None, **adc_config):
        """
        Record audio from ADC using optimized C module to WAV file.

        Args:
            file_path: Path to save WAV file (e.g., "data/recording.wav")
            duration_ms: Recording duration in milliseconds (None = 60 seconds default)
            adc_pin: GPIO pin for ADC input (default: configured pin or 1)
            sample_rate: Target sample rate in Hz (default 16000 for voice)
            on_complete: Callback function(message) when recording finishes
            **adc_config: Additional ADC configuration

        Returns:
            bool: True if recording started, False if rejected or unavailable
        """
        # Use configured pin if not specified
        if adc_pin is None:
            adc_pin = self._adc_mic_pin
            
        # Fallback to default if still None
        if adc_pin is None:
            adc_pin = 1 # Default to GPIO1 (Fri3d 2026)
            
        print(f"AudioManager.record_wav_adc() called")
        print(f"  file_path: {file_path}")
        print(f"  duration_ms: {duration_ms}")
        print(f"  adc_pin: {adc_pin}")
        print(f"  sample_rate: {sample_rate}")

        # Cannot record while playing (I2S can only be TX or RX, not both)
        if self.is_playing():
            print("AudioManager: Cannot record while playing")
            return False

        # Cannot start new recording while already recording
        if self.is_recording():
            print("AudioManager: Already recording")
            return False

        # Create stream and start recording in separate thread
        try:
            print("AudioManager: Importing ADCRecordStream...")
            from mpos.audio.stream_record_adc import ADCRecordStream

            print("AudioManager: Creating ADCRecordStream instance...")
            stream = ADCRecordStream(
                file_path=file_path,
                duration_ms=duration_ms,
                sample_rate=sample_rate,
                adc_pin=adc_pin,
                on_complete=on_complete,
                **adc_config
            )

            print("AudioManager: Starting ADC recording thread...")
            _thread.stack_size(TaskManager.good_stack_size())
            _thread.start_new_thread(self._recording_thread, (stream,))
            print("AudioManager: ADC recording thread started successfully")
            return True

        except Exception as e:
            import sys
            print(f"AudioManager: record_wav_adc() failed: {e}")
            sys.print_exception(e)
            return False

    def stop(self):
        """Stop current audio playback or recording."""
        stopped = False

        if self._current_stream:
            self._current_stream.stop()
            print("AudioManager: Playback stopped")
            stopped = True

        if self._current_recording:
            self._current_recording.stop()
            print("AudioManager: Recording stopped")
            stopped = True

        if not stopped:
            print("AudioManager: No playback or recording to stop")

    def pause(self):
        """
        Pause current audio playback (if supported by stream).
        Note: Most streams don't support pause, only stop.
        """
        if self._current_stream and hasattr(self._current_stream, 'pause'):
            self._current_stream.pause()
            print("AudioManager: Playback paused")
        else:
            print("AudioManager: Pause not supported or no playback active")

    def resume(self):
        """
        Resume paused audio playback (if supported by stream).
        Note: Most streams don't support resume, only play.
        """
        if self._current_stream and hasattr(self._current_stream, 'resume'):
            self._current_stream.resume()
            print("AudioManager: Playback resumed")
        else:
            print("AudioManager: Resume not supported or no playback active")

    def set_volume(self, volume):
        """
        Set system volume (affects new streams, not current playback).

        Args:
            volume: Volume level (0-100)
        """
        self._volume = max(0, min(100, volume))
        if self._current_stream:
            self._current_stream.set_volume(self._volume)

    def get_volume(self):
        """
        Get system volume.

        Returns:
            int: Current system volume (0-100)
        """
        return self._volume

    def is_playing(self):
        """
        Check if audio is currently playing.

        Returns:
            bool: True if playback active, False otherwise
        """
        return self._current_stream is not None and self._current_stream.is_playing()

    def is_recording(self):
        """
        Check if audio is currently being recorded.

        Returns:
            bool: True if recording active, False otherwise
        """
        return self._current_recording is not None and self._current_recording.is_recording()
 
# ============================================================================
# Class method forwarding to singleton instance
#
# Instead of writing each function like this:
#     @classmethod
#    def has_microphone(cls):
#        instance = cls.get()
#        return instance._i2s_pins is not None and 'sd_in' in instance._i2s_pins
#
# They can be written like this:
#    def has_microphone(self):
#        return self._i2s_pins is not None and 'sd_in' in self._i2s_pins
#
# ============================================================================
# Store original instance methods before replacing them
_original_methods = {}
_methods_to_delegate = [
    'play_wav', 'play_rtttl', 'record_wav', 'record_wav_adc', 'stop', 'pause', 'resume',
    'set_volume', 'get_volume', 'is_playing', 'is_recording',
    'has_i2s', 'has_buzzer', 'has_microphone'
]

for method_name in _methods_to_delegate:
    _original_methods[method_name] = getattr(AudioManager, method_name)

# Helper to create delegating class methods
def _make_class_method(method_name):
    """Create a class method that delegates to the singleton instance."""
    original_method = _original_methods[method_name]

    @classmethod
    def class_method(cls, *args, **kwargs):
        instance = cls.get()
        return original_method(instance, *args, **kwargs)
    
    return class_method

# Attach class methods to AudioManager
for method_name in _methods_to_delegate:
    setattr(AudioManager, method_name, _make_class_method(method_name))
