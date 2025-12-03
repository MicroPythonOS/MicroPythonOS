# AudioFlinger - Core Audio Management Service
# Centralized audio routing with priority-based audio focus (Android-inspired)
# Supports I2S (digital audio) and PWM buzzer (tones/ringtones)

# Device type constants
DEVICE_NULL = 0      # No audio hardware (desktop fallback)
DEVICE_I2S = 1       # Digital audio output (WAV playback)
DEVICE_BUZZER = 2    # PWM buzzer (tones/RTTTL)
DEVICE_BOTH = 3      # Both I2S and buzzer available

# Stream type constants (priority order: higher number = higher priority)
STREAM_MUSIC = 0         # Background music (lowest priority)
STREAM_NOTIFICATION = 1  # Notification sounds (medium priority)
STREAM_ALARM = 2         # Alarms/alerts (highest priority)

# Module-level state (singleton pattern, follows battery_voltage.py)
_device_type = DEVICE_NULL
_i2s_pins = None          # I2S pin configuration dict (created per-stream)
_buzzer_instance = None   # PWM buzzer instance
_current_stream = None    # Currently playing stream
_volume = 70              # System volume (0-100)
_stream_lock = None       # Thread lock for stream management


def init(device_type, i2s_pins=None, buzzer_instance=None):
    """
    Initialize AudioFlinger with hardware configuration.

    Args:
        device_type: One of DEVICE_NULL, DEVICE_I2S, DEVICE_BUZZER, DEVICE_BOTH
        i2s_pins: Dict with 'sck', 'ws', 'sd' pin numbers (for I2S devices)
        buzzer_instance: PWM instance for buzzer (for buzzer devices)
    """
    global _device_type, _i2s_pins, _buzzer_instance, _stream_lock

    _device_type = device_type
    _i2s_pins = i2s_pins
    _buzzer_instance = buzzer_instance

    # Initialize thread lock for stream management
    try:
        import _thread
        _stream_lock = _thread.allocate_lock()
    except ImportError:
        # Desktop mode - no threading support
        _stream_lock = None

    device_names = {
        DEVICE_NULL: "NULL (no audio)",
        DEVICE_I2S: "I2S (digital audio)",
        DEVICE_BUZZER: "Buzzer (PWM tones)",
        DEVICE_BOTH: "Both (I2S + Buzzer)"
    }

    print(f"AudioFlinger initialized: {device_names.get(device_type, 'Unknown')}")


def _check_audio_focus(stream_type):
    """
    Check if a stream with the given type can start playback.
    Implements priority-based audio focus (Android-inspired).

    Args:
        stream_type: Stream type (STREAM_MUSIC, STREAM_NOTIFICATION, STREAM_ALARM)

    Returns:
        bool: True if stream can start, False if rejected
    """
    global _current_stream

    if not _current_stream:
        return True  # No stream playing, OK to start

    if not _current_stream.is_playing():
        return True  # Current stream finished, OK to start

    # Check priority
    if stream_type <= _current_stream.stream_type:
        print(f"AudioFlinger: Stream rejected (priority {stream_type} <= current {_current_stream.stream_type})")
        return False

    # Higher priority stream - interrupt current
    print(f"AudioFlinger: Interrupting stream (priority {stream_type} > current {_current_stream.stream_type})")
    _current_stream.stop()
    return True


def _playback_thread(stream):
    """
    Background thread function for audio playback.

    Args:
        stream: Stream instance (WAVStream or RTTTLStream)
    """
    global _current_stream

    # Acquire lock and set as current stream
    if _stream_lock:
        _stream_lock.acquire()
    _current_stream = stream
    if _stream_lock:
        _stream_lock.release()

    try:
        # Run playback (blocks until complete or stopped)
        stream.play()
    except Exception as e:
        print(f"AudioFlinger: Playback error: {e}")
    finally:
        # Clear current stream
        if _stream_lock:
            _stream_lock.acquire()
        if _current_stream == stream:
            _current_stream = None
        if _stream_lock:
            _stream_lock.release()


def play_wav(file_path, stream_type=STREAM_MUSIC, volume=None, on_complete=None):
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
    if _device_type not in (DEVICE_I2S, DEVICE_BOTH):
        print("AudioFlinger: play_wav() failed - no I2S device available")
        return False

    if not _i2s_pins:
        print("AudioFlinger: play_wav() failed - I2S pins not configured")
        return False

    # Check audio focus
    if _stream_lock:
        _stream_lock.acquire()
    can_start = _check_audio_focus(stream_type)
    if _stream_lock:
        _stream_lock.release()

    if not can_start:
        return False

    # Create stream and start playback in background thread
    try:
        from mpos.audio.stream_wav import WAVStream
        import _thread
        import mpos.apps

        stream = WAVStream(
            file_path=file_path,
            stream_type=stream_type,
            volume=volume if volume is not None else _volume,
            i2s_pins=_i2s_pins,
            on_complete=on_complete
        )

        _thread.stack_size(mpos.apps.good_stack_size())
        _thread.start_new_thread(_playback_thread, (stream,))
        return True

    except Exception as e:
        print(f"AudioFlinger: play_wav() failed: {e}")
        return False


def play_rtttl(rtttl_string, stream_type=STREAM_NOTIFICATION, volume=None, on_complete=None):
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
    if _device_type not in (DEVICE_BUZZER, DEVICE_BOTH):
        print("AudioFlinger: play_rtttl() failed - no buzzer device available")
        return False

    if not _buzzer_instance:
        print("AudioFlinger: play_rtttl() failed - buzzer not initialized")
        return False

    # Check audio focus
    if _stream_lock:
        _stream_lock.acquire()
    can_start = _check_audio_focus(stream_type)
    if _stream_lock:
        _stream_lock.release()

    if not can_start:
        return False

    # Create stream and start playback in background thread
    try:
        from mpos.audio.stream_rtttl import RTTTLStream
        import _thread
        import mpos.apps

        stream = RTTTLStream(
            rtttl_string=rtttl_string,
            stream_type=stream_type,
            volume=volume if volume is not None else _volume,
            buzzer_instance=_buzzer_instance,
            on_complete=on_complete
        )

        _thread.stack_size(mpos.apps.good_stack_size())
        _thread.start_new_thread(_playback_thread, (stream,))
        return True

    except Exception as e:
        print(f"AudioFlinger: play_rtttl() failed: {e}")
        return False


def stop():
    """Stop current audio playback."""
    global _current_stream

    if _stream_lock:
        _stream_lock.acquire()

    if _current_stream:
        _current_stream.stop()
        print("AudioFlinger: Playback stopped")
    else:
        print("AudioFlinger: No playback to stop")

    if _stream_lock:
        _stream_lock.release()


def pause():
    """
    Pause current audio playback (if supported by stream).
    Note: Most streams don't support pause, only stop.
    """
    global _current_stream

    if _stream_lock:
        _stream_lock.acquire()

    if _current_stream and hasattr(_current_stream, 'pause'):
        _current_stream.pause()
        print("AudioFlinger: Playback paused")
    else:
        print("AudioFlinger: Pause not supported or no playback active")

    if _stream_lock:
        _stream_lock.release()


def resume():
    """
    Resume paused audio playback (if supported by stream).
    Note: Most streams don't support resume, only play.
    """
    global _current_stream

    if _stream_lock:
        _stream_lock.acquire()

    if _current_stream and hasattr(_current_stream, 'resume'):
        _current_stream.resume()
        print("AudioFlinger: Playback resumed")
    else:
        print("AudioFlinger: Resume not supported or no playback active")

    if _stream_lock:
        _stream_lock.release()


def set_volume(volume):
    """
    Set system volume (affects new streams, not current playback).

    Args:
        volume: Volume level (0-100)
    """
    global _volume
    _volume = max(0, min(100, volume))


def get_volume():
    """
    Get system volume.

    Returns:
        int: Current system volume (0-100)
    """
    return _volume


def get_device_type():
    """
    Get configured audio device type.

    Returns:
        int: Device type (DEVICE_NULL, DEVICE_I2S, DEVICE_BUZZER, DEVICE_BOTH)
    """
    return _device_type


def is_playing():
    """
    Check if audio is currently playing.

    Returns:
        bool: True if playback active, False otherwise
    """
    if _stream_lock:
        _stream_lock.acquire()

    result = _current_stream is not None and _current_stream.is_playing()

    if _stream_lock:
        _stream_lock.release()

    return result
