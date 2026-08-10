# lora_spi_adapter: the SX1262 _cmd() now handles bus arbitration itself.
#
# _cmd() holds SPI.Device.lock()/unlock() across the CS-low span,
# with a split-phase transfer: opcode+params first, then a 50us delay
# to give the SX1262 time to process the command, then the read
# phase.  This prevents display SPI interleaving while CS is low
# and gives the chip time to prepare response bytes.
