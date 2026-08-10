# lora_spi_adapter: the SX1262 _cmd() now handles bus arbitration itself.
#
# _cmd() holds SPI.Device.lock()/unlock() across the CS-low span
# and uses byte-at-a-time SPI transfers for SX1262 timing compliance.
# This prevents display SPI interleaving while CS is low and gives
# the chip inter-byte gaps to process commands.
