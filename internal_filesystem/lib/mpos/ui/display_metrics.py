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

    DENSITY_MDPI = "mdpi"
    DENSITY_HDPI = "hdpi"

    # Density class boundaries for authored bitmaps, by the smaller screen
    # dimension so portrait and landscape variants of a panel resolve
    # identically. Add further buckets (e.g. xhdpi) here without changing the
    # mechanism.
    _DENSITY_BUCKETS = (
        (300, DENSITY_HDPI, 1.5),
    )

    @classmethod
    def density_bucket(cls):
        """Get the density class of the current screen ("mdpi" or "hdpi").

        Apps pick a matching bitmap variant with this. The mdpi art is the
        universal baseline; hdpi is for screens whose small dimension is at
        least 300 pixels.
        """
        if cls._width is None or cls._height is None:
            return cls.DENSITY_MDPI
        small_side = min(cls._width, cls._height)
        for min_side, bucket, _factor in cls._DENSITY_BUCKETS:
            if small_side >= min_side:
                return bucket
        return cls.DENSITY_MDPI

    @classmethod
    def density_factor(cls):
        """Get the scale factor for the current density class (1.0 or 1.5).

        Used to scale mdpi art on an hdpi screen when the app ships no native
        hdpi variant.
        """
        if cls._width is None or cls._height is None:
            return 1.0
        small_side = min(cls._width, cls._height)
        for min_side, _bucket, factor in cls._DENSITY_BUCKETS:
            if small_side >= min_side:
                return factor
        return 1.0
    
