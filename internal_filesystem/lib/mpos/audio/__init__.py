# AudioFlinger - Centralized Audio Management Service for MicroPythonOS
# Android-inspired audio routing with priority-based audio focus
# Simple routing: play_wav() -> I2S, play_rtttl() -> buzzer, record_wav() -> I2S mic

from .audioflinger import AudioFlinger

# Create singleton instance
_instance = AudioFlinger.get()

# Re-export stream type constants for convenience
STREAM_MUSIC = AudioFlinger.STREAM_MUSIC
STREAM_NOTIFICATION = AudioFlinger.STREAM_NOTIFICATION
STREAM_ALARM = AudioFlinger.STREAM_ALARM

# Re-export main API from singleton instance for backward compatibility
init = _instance.init
play_wav = _instance.play_wav
play_rtttl = _instance.play_rtttl
stop = _instance.stop
pause = _instance.pause
resume = _instance.resume
set_volume = _instance.set_volume
get_volume = _instance.get_volume
is_playing = _instance.is_playing
record_wav = _instance.record_wav
is_recording = _instance.is_recording
has_i2s = _instance.has_i2s
has_buzzer = _instance.has_buzzer
has_microphone = _instance.has_microphone

__all__ = [
    # Class
    'AudioFlinger',
    
    # Stream types
    'STREAM_MUSIC',
    'STREAM_NOTIFICATION',
    'STREAM_ALARM',

    # Playback functions
    'init',
    'play_wav',
    'play_rtttl',
    'stop',
    'pause',
    'resume',
    'set_volume',
    'get_volume',
    'is_playing',

    # Recording functions
    'record_wav',
    'is_recording',

    # Hardware checks
    'has_i2s',
    'has_buzzer',
    'has_microphone',
]
