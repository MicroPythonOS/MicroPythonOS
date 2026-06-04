import sys
from . import st7701s
from . import _st7701s_init

# st7701s.py's _spi_3wire_init() loads the panel sequence via __import__('_st7701s_init'),
# which resolves a top-level module name (the framework's _<driver>_init convention).
# This file lives in the st7701s package, so register it under that top-level name for
# the import to resolve.
sys.modules['_st7701s_init'] = _st7701s_init

# Re-export the public driver class.
__all__ = [
    'ST7701S',
]
ST7701S = st7701s.ST7701S
