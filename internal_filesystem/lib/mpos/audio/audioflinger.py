# AudioFlinger - Core Audio Management Service
# Centralized audio routing with priority-based audio focus (Android-inspired)
# Supports I2S (digital audio) and PWM buzzer (tones/ringtones)
#
# Simple routing: play_wav() -> I2S, play_rtttl() -> buzzer, record_wav() -> I2S mic
# Uses _thread for non-blocking background playback/recording (separate thread from UI)

import _thread
import mpos.apps


class AudioFlinger:
    """
    Centralized audio management service with priority-based audio focus.
    Implements singleton pattern for single audio service instance.
    
    Usage:
        from mpos import AudioFlinger
        
        # Direct class method calls (no .get() needed)
        AudioFlinger.init(i2s_pins=pins, buzzer_instance=buzzer)
        AudioFlinger.play_wav("music.wav", stream_type=AudioFlinger.STREAM_MUSIC)
        AudioFlinger.set_volume(80)
        volume = AudioFlinger.get_volume()
        AudioFlinger.stop()
    """
    
    # Stream type constants (priority order: higher number = higher priority)
    STREAM_MUSIC = 0         # Background music (lowest priority)
    STREAM_NOTIFICATION = 1  # Notification sounds (medium priority)
    STREAM_ALARM = 2         # Alarms/alerts (highest priority)
    
    _instance = None  # Singleton instance
    
    def __init__(self):
        """Initialize AudioFlinger instance."""
        if AudioFlinger._instance:
            return
        AudioFlinger._instance = self
        
        self._i2s_pins = None          # I2S pin configuration dict (created per-stream)
        self._buzzer_instance = None   # PWM buzzer instance
        self._current_stream = None    # Currently playing stream
        self._current_recording = None # Currently recording stream
        self._volume = 50              # System volume (0-100)
    
    @classmethod
    def get(cls):
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def init(self, i2s_pins=None, buzzer_instance=None):
        """
        Initialize AudioFlinger with hardware configuration.

        Args:
            i2s_pins: Dict with 'sck', 'ws', 'sd' pin numbers (for I2S/WAV playback)
            buzzer_instance: PWM instance for buzzer (for RTTTL playback)
        """
        self._i2s_pins = i2s_pins
        self._buzzer_instance = buzzer_instance

        # Build status message
        capabilities = []
        if i2s_pins:
            capabilities.append("I2S (WAV)")
        if buzzer_instance:
            capabilities.append("Buzzer (RTTTL)")
        
        if capabilities:
            print(f"AudioFlinger initialized: {', '.join(capabilities)}")
        else:
            print("AudioFlinger initialized: No audio hardware")

    def has_i2s(self):
        """Check if I2S audio is available for WAV playback."""
        return self._i2s_pins is not None

    def has_buzzer(self):
        """Check if buzzer is available for RTTTL playback."""
        return self._buzzer_instance is not None

    def has_microphone(self):
        """Check if I2S microphone is available for recording."""
        return self._i2s_pins is not None and 'sd_in' in self._i2s_pins

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
            print(f"AudioFlinger: Stream rejected (priority {stream_type} <= current {self._current_stream.stream_type})")
            return False

        # Higher priority stream - interrupt current
        print(f"AudioFlinger: Interrupting stream (priority {stream_type} > current {self._current_stream.stream_type})")
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
            print(f"AudioFlinger: Playback error: {e}")
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
            print("AudioFlinger: play_wav() failed - I2S not configured")
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

            _thread.stack_size(mpos.apps.good_stack_size())
            _thread.start_new_thread(self._playback_thread, (stream,))
            return True

        except Exception as e:
            print(f"AudioFlinger: play_wav() failed: {e}")
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
            print("AudioFlinger: play_rtttl() failed - buzzer not configured")
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

            _thread.stack_size(mpos.apps.good_stack_size())
            _thread.start_new_thread(self._playback_thread, (stream,))
            return True

        except Exception as e:
            print(f"AudioFlinger: play_rtttl() failed: {e}")
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
            print(f"AudioFlinger: Recording error: {e}")
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
        print(f"AudioFlinger.record_wav() called")
        print(f"  file_path: {file_path}")
        print(f"  duration_ms: {duration_ms}")
        print(f"  sample_rate: {sample_rate}")
        print(f"  _i2s_pins: {self._i2s_pins}")
        print(f"  has_microphone(): {self.has_microphone()}")

        if not self.has_microphone():
            print("AudioFlinger: record_wav() failed - microphone not configured")
            return False

        # Cannot record while playing (I2S can only be TX or RX, not both)
        if self.is_playing():
            print("AudioFlinger: Cannot record while playing")
            return False

        # Cannot start new recording while already recording
        if self.is_recording():
            print("AudioFlinger: Already recording")
            return False

        # Create stream and start recording in separate thread
        try:
            print("AudioFlinger: Importing RecordStream...")
            from mpos.audio.stream_record import RecordStream

            print("AudioFlinger: Creating RecordStream instance...")
            stream = RecordStream(
                file_path=file_path,
                duration_ms=duration_ms,
                sample_rate=sample_rate,
                i2s_pins=self._i2s_pins,
                on_complete=on_complete
            )

            print("AudioFlinger: Starting recording thread...")
            _thread.stack_size(mpos.apps.good_stack_size())
            _thread.start_new_thread(self._recording_thread, (stream,))
            print("AudioFlinger: Recording thread started successfully")
            return True

        except Exception as e:
            import sys
            print(f"AudioFlinger: record_wav() failed: {e}")
            sys.print_exception(e)
            return False

    def stop(self):
        """Stop current audio playback or recording."""
        stopped = False

        if self._current_stream:
            self._current_stream.stop()
            print("AudioFlinger: Playback stopped")
            stopped = True

        if self._current_recording:
            self._current_recording.stop()
            print("AudioFlinger: Recording stopped")
            stopped = True

        if not stopped:
            print("AudioFlinger: No playback or recording to stop")

    def pause(self):
        """
        Pause current audio playback (if supported by stream).
        Note: Most streams don't support pause, only stop.
        """
        if self._current_stream and hasattr(self._current_stream, 'pause'):
            self._current_stream.pause()
            print("AudioFlinger: Playback paused")
        else:
            print("AudioFlinger: Pause not supported or no playback active")

    def resume(self):
        """
        Resume paused audio playback (if supported by stream).
        Note: Most streams don't support resume, only play.
        """
        if self._current_stream and hasattr(self._current_stream, 'resume'):
            self._current_stream.resume()
            print("AudioFlinger: Playback resumed")
        else:
            print("AudioFlinger: Resume not supported or no playback active")

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
# Class methods that delegate to singleton instance (like DownloadManager)
# ============================================================================

# Store original instance methods before creating class methods
_init_impl = AudioFlinger.init
_play_wav_impl = AudioFlinger.play_wav
_play_rtttl_impl = AudioFlinger.play_rtttl
_record_wav_impl = AudioFlinger.record_wav
_stop_impl = AudioFlinger.stop
_pause_impl = AudioFlinger.pause
_resume_impl = AudioFlinger.resume
_set_volume_impl = AudioFlinger.set_volume
_get_volume_impl = AudioFlinger.get_volume
_is_playing_impl = AudioFlinger.is_playing
_is_recording_impl = AudioFlinger.is_recording
_has_i2s_impl = AudioFlinger.has_i2s
_has_buzzer_impl = AudioFlinger.has_buzzer
_has_microphone_impl = AudioFlinger.has_microphone


# Create class methods that delegate to singleton
@classmethod
def init(cls, i2s_pins=None, buzzer_instance=None):
    """Initialize AudioFlinger with hardware configuration."""
    return cls.get()._init_impl(i2s_pins=i2s_pins, buzzer_instance=buzzer_instance)

@classmethod
def play_wav(cls, file_path, stream_type=None, volume=None, on_complete=None):
    """Play WAV file via I2S."""
    return cls.get()._play_wav_impl(file_path=file_path, stream_type=stream_type, 
                                    volume=volume, on_complete=on_complete)

@classmethod
def play_rtttl(cls, rtttl_string, stream_type=None, volume=None, on_complete=None):
    """Play RTTTL ringtone via buzzer."""
    return cls.get()._play_rtttl_impl(rtttl_string=rtttl_string, stream_type=stream_type,
                                      volume=volume, on_complete=on_complete)

@classmethod
def record_wav(cls, file_path, duration_ms=None, on_complete=None, sample_rate=16000):
    """Record audio from I2S microphone to WAV file."""
    return cls.get()._record_wav_impl(file_path=file_path, duration_ms=duration_ms,
                                      on_complete=on_complete, sample_rate=sample_rate)

@classmethod
def stop(cls):
    """Stop current audio playback or recording."""
    return cls.get()._stop_impl()

@classmethod
def pause(cls):
    """Pause current audio playback."""
    return cls.get()._pause_impl()

@classmethod
def resume(cls):
    """Resume paused audio playback."""
    return cls.get()._resume_impl()

@classmethod
def set_volume(cls, volume):
    """Set system volume."""
    return cls.get()._set_volume_impl(volume)

@classmethod
def get_volume(cls):
    """Get system volume."""
    return cls.get()._get_volume_impl()

@classmethod
def is_playing(cls):
    """Check if audio is currently playing."""
    return cls.get()._is_playing_impl()

@classmethod
def is_recording(cls):
    """Check if audio is currently being recorded."""
    return cls.get()._is_recording_impl()

@classmethod
def has_i2s(cls):
    """Check if I2S audio is available."""
    return cls.get()._has_i2s_impl()

@classmethod
def has_buzzer(cls):
    """Check if buzzer is available."""
    return cls.get()._has_buzzer_impl()

@classmethod
def has_microphone(cls):
    """Check if I2S microphone is available."""
    return cls.get()._has_microphone_impl()

# Attach class methods to AudioFlinger class
AudioFlinger.init = init
AudioFlinger.play_wav = play_wav
AudioFlinger.play_rtttl = play_rtttl
AudioFlinger.record_wav = record_wav
AudioFlinger.stop = stop
AudioFlinger.pause = pause
AudioFlinger.resume = resume
AudioFlinger.set_volume = set_volume
AudioFlinger.get_volume = get_volume
AudioFlinger.is_playing = is_playing
AudioFlinger.is_recording = is_recording
AudioFlinger.has_i2s = has_i2s
AudioFlinger.has_buzzer = has_buzzer
AudioFlinger.has_microphone = has_microphone

# Rename instance methods to avoid conflicts
AudioFlinger._init_impl = _init_impl
AudioFlinger._play_wav_impl = _play_wav_impl
AudioFlinger._play_rtttl_impl = _play_rtttl_impl
AudioFlinger._record_wav_impl = _record_wav_impl
AudioFlinger._stop_impl = _stop_impl
AudioFlinger._pause_impl = _pause_impl
AudioFlinger._resume_impl = _resume_impl
AudioFlinger._set_volume_impl = _set_volume_impl
AudioFlinger._get_volume_impl = _get_volume_impl
AudioFlinger._is_playing_impl = _is_playing_impl
AudioFlinger._is_recording_impl = _is_recording_impl
AudioFlinger._has_i2s_impl = _has_i2s_impl
AudioFlinger._has_buzzer_impl = _has_buzzer_impl
AudioFlinger._has_microphone_impl = _has_microphone_impl
