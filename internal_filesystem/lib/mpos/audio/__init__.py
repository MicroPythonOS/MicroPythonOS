# AudioFlinger - Centralized Audio Management Service for MicroPythonOS
# Android-inspired audio routing with priority-based audio focus
# Simple routing: play_wav() -> I2S, play_rtttl() -> buzzer, record_wav() -> I2S mic

from .audioflinger import AudioFlinger
