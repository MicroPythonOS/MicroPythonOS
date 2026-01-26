# Fri3d Camp 2024 Badge Hardware Drivers
# These are simple wrappers that can be used by services like AudioManager

from .buzzer import BuzzerConfig
from .leds import LEDConfig
from .rtttl_data import RTTTL_SONGS

__all__ = ['BuzzerConfig', 'LEDConfig', 'RTTTL_SONGS']
