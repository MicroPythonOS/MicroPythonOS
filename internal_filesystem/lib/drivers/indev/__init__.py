"""Input device drivers package helpers."""

try:
    import sys
    from . import focaltech_touch as _focaltech_touch

    if "focaltech_touch" not in sys.modules:
        sys.modules["focaltech_touch"] = _focaltech_touch
except Exception:
    pass
