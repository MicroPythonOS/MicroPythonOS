import sys
from . import ili9341
from . import _ili9341_init_type1
from . import _ili9341_init_type2

# Register _ili9341_init_type1 and _ili9341_init_type2 in sys.modules so __import__() can find them
# This is needed because display_driver_framework.py uses __import__('_ili9341_init_type1') and __import__('_ili9341_init_type2')
# expecting top-level modules, but they are in the ili9341 package subdirectory
sys.modules['_ili9341_init_type1'] = _ili9341_init_type1
sys.modules['_ili9341_init_type2'] = _ili9341_init_type2

# Explicitly define __all__ and re-export public symbols from ili9341 module
__all__ = [
    'ILI9341',
    'STATE_HIGH',
    'STATE_LOW',
    'STATE_PWM',
    'BYTE_ORDER_RGB',
    'BYTE_ORDER_BGR',
]

# Re-export the public symbols
ILI9341 = ili9341.ILI9341
STATE_HIGH = ili9341.STATE_HIGH
STATE_LOW = ili9341.STATE_LOW
STATE_PWM = ili9341.STATE_PWM
BYTE_ORDER_RGB = ili9341.BYTE_ORDER_RGB
BYTE_ORDER_BGR = ili9341.BYTE_ORDER_BGR
