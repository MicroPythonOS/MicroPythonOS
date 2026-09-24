import logging

logger = logging.getLogger(__name__)

# Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3 — bring-up stage 1 (#307):
# ESP32-P4 + ESP32-C6 Wi-Fi co-processor over SDIO (handled by MicroPython's
# C6_WIFI board variant), 4.3" 480x800 MIPI-DSI panel (ST7701, 2 lanes),
# GT911 touch on I2C (SDA=7, SCL=8), ES8311/ES7210 audio, SD card, camera.
#
# The MIPI-DSI display needs a DSI bus in lvgl_micropython that is not
# wired up yet, so this stage registers no display: MicroPythonOS stops at
# init_rootscreen() and leaves the REPL usable for the Wi-Fi/boot work.
# Display, touch, audio follow in later stages.

logger.warning("Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3: stage-1 board file, no display driver yet")
