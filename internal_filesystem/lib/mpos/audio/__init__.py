# AudioFlinger - Centralized Audio Management Service for MicroPythonOS
# Android-inspired audio routing with priority-based audio focus
# Simple routing: play_wav() -> I2S, play_rtttl() -> buzzer, record_wav() -> I2S mic

from . import audioflinger

# Re-export main API
from .audioflinger import (
    # Stream types (for priority-based audio focus)
    STREAM_MUSIC,
    STREAM_NOTIFICATION,
    STREAM_ALARM,

    # Core playback functions
    init,
    play_wav,
    play_rtttl,
    stop,
    pause,
    resume,
    set_volume,
    get_volume,
    is_playing,

    # Recording functions
    record_wav,
    is_recording,

    # Hardware availability checks
    has_i2s,
    has_buzzer,
    has_microphone,
)

__all__ = [
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
