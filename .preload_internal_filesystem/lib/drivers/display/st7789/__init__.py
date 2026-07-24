import sys
from . import st7789
from . import _st7789_init

# Register _st7789_init in sys.modules so __import__('_st7789_init') can find it
# This is needed because display_driver_framework.py uses __import__('_st7789_init')
# expecting a top-level module, but _st7789_init is in the st7789 package subdirectory
sys.modules['_st7789_init'] = _st7789_init

# Explicitly define __all__ and re-export public symbols from st7789 module
__all__ = [
    'ST7789',
    'STATE_HIGH',
    'STATE_LOW',
    'STATE_PWM',
    'BYTE_ORDER_RGB',
    'BYTE_ORDER_BGR',
]

# Re-export the public symbols
ST7789 = st7789.ST7789
STATE_HIGH = st7789.STATE_HIGH
STATE_LOW = st7789.STATE_LOW
STATE_PWM = st7789.STATE_PWM
BYTE_ORDER_RGB = st7789.BYTE_ORDER_RGB
BYTE_ORDER_BGR = st7789.BYTE_ORDER_BGR
