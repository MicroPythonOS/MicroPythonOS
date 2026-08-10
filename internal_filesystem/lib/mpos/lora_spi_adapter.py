# lora_spi_adapter: holds SPI.Device.lock() across SX1262 CS-low spans.
#
# The upstream SX1262._cmd() toggles CS, calls write_readinto, then
# optionally write_buf or read_buf.  SPI.Device.lock()/unlock()
# ensures the shared bus (LCD and LoRa on same SPI.Bus) cannot be
# preempted while CS is held low.  _wait_not_busy() runs BEFORE lock
# acquisition so the display can flush during BUSY polling.


def wrap_sx126x_cmd(radio):
    """Hold SPI.Device.lock() for the CS-low span of lora.SX1262._cmd().

    The upstream _cmd() toggles CS, calls write_readinto, then
    optionally write (FIFO write) or readinto (FIFO read).  This
    wrapper holds the C-level bus lock across those calls so the
    shared bus cannot be preempted while CS is held low.

    _wait_not_busy() runs BEFORE acquiring the lock — it only
    polls the BUSY GPIO pin.
    """
    _cmd = radio._cmd

    def locked_cmd(*args, **kwargs):
        radio._wait_not_busy(radio._busy_timeout)
        radio._spi.lock()
        try:
            return _cmd(*args, **kwargs)
        finally:
            radio._spi.unlock()

    radio._cmd = locked_cmd
