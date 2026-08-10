# lora_spi_adapter: the SX1262 _cmd() now holds SPI.Device.lock()/unlock()
# across the CS-low span internally — no external wrapper needed.
#
# SPI.Device.lock()/unlock() provides C-level bus arbitration
# (spi_device_acquire_bus/release_bus) that properly coordinates
# with the LCD display driver sharing the same SPI bus.
