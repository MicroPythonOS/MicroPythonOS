import sys
from . import st7701s
from . import _st7701s_init

# Register _st7701s_init in sys.modules so __import__('_st7701s_init') can find it
# This is needed because display_driver_framework.py uses __import__('_st7701s_init')
# expecting a top-level module, but _st7701s_init is in the st7701s package subdirectory
sys.modules['_st7701s_init'] = _st7701s_init

# Explicitly define __all__ and re-export public symbols from st7701s module
__all__ = [
    'ST7701S',
]

# Re-export the public symbols
ST7701S = st7701s.ST7701S
