# AudioFlinger - Centralized Audio Management Service for MicroPythonOS
# Android-inspired audio routing with priority-based audio focus

from . import audioflinger

# Re-export main API
from .audioflinger import (
    # Device types
    DEVICE_NULL,
    DEVICE_I2S,
    DEVICE_BUZZER,
    DEVICE_BOTH,

    # Stream types
    STREAM_MUSIC,
    STREAM_NOTIFICATION,
    STREAM_ALARM,

    # Core functions
    init,
    play_wav,
    play_rtttl,
    stop,
    pause,
    resume,
    set_volume,
    get_volume,
    get_device_type,
    is_playing,
)

__all__ = [
    # Device types
    'DEVICE_NULL',
    'DEVICE_I2S',
    'DEVICE_BUZZER',
    'DEVICE_BOTH',

    # Stream types
    'STREAM_MUSIC',
    'STREAM_NOTIFICATION',
    'STREAM_ALARM',

    # Functions
    'init',
    'play_wav',
    'play_rtttl',
    'stop',
    'pause',
    'resume',
    'set_volume',
    'get_volume',
    'get_device_type',
    'is_playing',
]
