import sys
from . import st7789
from . import _st7789_init
from . import _st7789_init_type1
from . import _st7789_init_type2

# Init-profile numbers. display_driver_framework picks _st7789_init_type<N>
# from these, so the numbers are fixed by those filenames; boards should use
# the names below instead of bare integers.
PROFILE_GENERIC = None  # upstream default sequence (_st7789_init.py)
PROFILE_LEGACY = 1      # sequence shipped before the split (_st7789_init_type1.py)
PROFILE_ST7789V = 2     # B4-based inversion control (_st7789_init_type2.py)

# Register the init modules in sys.modules so __import__() can find them.
# This is needed because display_driver_framework.py uses
# __import__('_st7789_init_type1') and __import__('_st7789_init_type2')
# expecting top-level modules, but they are in the st7789 package subdirectory.
sys.modules['_st7789_init'] = _st7789_init
sys.modules['_st7789_init_type1'] = _st7789_init_type1
sys.modules['_st7789_init_type2'] = _st7789_init_type2

# Explicitly define __all__ and re-export public symbols from st7789 module
__all__ = [
    'ST7789',
    'PROFILE_GENERIC',
    'PROFILE_LEGACY',
    'PROFILE_ST7789V',
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
