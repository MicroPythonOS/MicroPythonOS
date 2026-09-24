# ST7701 panel driven over MIPI-DSI (video mode) through lvgl_micropython's
# lcd_bus.DSIBus. Used by the Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3.
from .st7701_dsi import ST7701_DSI

__all__ = [
    'ST7701_DSI',
]
