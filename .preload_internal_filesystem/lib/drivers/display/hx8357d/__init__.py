import sys
from . import hx8357d
from . import _hx8357d_init

# Register _hx8357d_init in sys.modules so __import__('_hx8357d_init') can find it
# This is needed because display_driver_framework.py uses __import__('_hx8357d_init')
# expecting a top-level module, but _hx8357d_init is in the hx8357d package subdirectory
sys.modules['_hx8357d_init'] = _hx8357d_init

# Explicitly define __all__ and re-export public symbols from hx8357d module
__all__ = [
    'HX8357D',
    'STATE_HIGH',
    'STATE_LOW',
    'STATE_PWM',
    'BYTE_ORDER_RGB',
    'BYTE_ORDER_BGR',
]

# Re-export the public symbols
HX8357D = hx8357d.HX8357D
STATE_HIGH = hx8357d.STATE_HIGH
STATE_LOW = hx8357d.STATE_LOW
STATE_PWM = hx8357d.STATE_PWM
BYTE_ORDER_RGB = hx8357d.BYTE_ORDER_RGB
BYTE_ORDER_BGR = hx8357d.BYTE_ORDER_BGR
