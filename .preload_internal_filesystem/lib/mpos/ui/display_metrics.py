# lib/mpos/ui/display_metrics.py
"""
DisplayMetrics - Android-inspired display metrics singleton.

Provides a clean, unified API for accessing display properties like width, height, and DPI.
All methods are class methods, so no instance creation is needed.
"""


class DisplayMetrics:
    """
    Display metrics singleton (Android-inspired).
    
    Provides static/class methods for accessing display properties.
    Initialized by display.init_rootscreen() which calls set_resolution() and set_dpi().
    """
    
    _width = None
    _height = None
    _dpi = None
    
    @classmethod
    def set_resolution(cls, width, height):
        """Set the display resolution (called by init_rootscreen)."""
        cls._width = width
        cls._height = height
    
    @classmethod
    def set_dpi(cls, dpi):
        """Set the display DPI (called by init_rootscreen)."""
        cls._dpi = dpi
    
    @classmethod
    def width(cls):
        """Get display width in pixels."""
        return cls._width
    
    @classmethod
    def height(cls):
        """Get display height in pixels."""
        return cls._height
    
    @classmethod
    def dpi(cls):
        """Get display DPI (dots per inch)."""
        return cls._dpi
    
    @classmethod
    def pct_of_width(cls, pct):
        """Get percentage of display width."""
        if pct == 100:
            return cls._width
        return round(cls._width * pct / 100)
    
    @classmethod
    def pct_of_height(cls, pct):
        """Get percentage of display height."""
        if pct == 100:
            return cls._height
        return round(cls._height * pct / 100)
    
    @classmethod
    def min_dimension(cls):
        """Get minimum dimension (width or height)."""
        return min(cls._width, cls._height)
    
    @classmethod
    def max_dimension(cls):
        """Get maximum dimension (width or height)."""
        return max(cls._width, cls._height)
    
