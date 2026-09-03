import sys
from . import st7796
from . import _st7796_init

# Register _st7796_init in sys.modules so __import__('_st7796_init') can find it
# This is needed because display_driver_framework.py uses __import__('_st7796_init')
# expecting a top-level module, but _st7796_init is in the st7796 package subdirectory
sys.modules['_st7796_init'] = _st7796_init

# Explicitly define __all__ and re-export public symbols from st7796 module
__all__ = [
    'ST7796',
    'STATE_HIGH',
    'STATE_LOW',
    'STATE_PWM',
    'BYTE_ORDER_RGB',
    'BYTE_ORDER_BGR',
]

# Re-export the public symbols
ST7796 = st7796.ST7796
STATE_HIGH = st7796.STATE_HIGH
STATE_LOW = st7796.STATE_LOW
STATE_PWM = st7796.STATE_PWM
BYTE_ORDER_RGB = st7796.BYTE_ORDER_RGB
BYTE_ORDER_BGR = st7796.BYTE_ORDER_BGR
