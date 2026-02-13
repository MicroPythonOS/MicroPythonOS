import sys
from .st7789 import *
from . import _st7789_init

# Register _st7789_init in sys.modules so __import__('_st7789_init') can find it
# This is needed because display_driver_framework.py uses __import__('_st7789_init')
# expecting a top-level module, but _st7789_init is in the st7789 package subdirectory
sys.modules['_st7789_init'] = _st7789_init
