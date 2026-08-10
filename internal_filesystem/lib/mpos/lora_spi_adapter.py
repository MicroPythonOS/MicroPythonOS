print("lora_spi_adapter: loaded (filesystem copy)")

# ponytail: wraps SPI.Device so the upstream lora driver (which expects
# standard machine.SPI: write_readinto/write/readinto) can talk through
# lvgl_micropython's split SPI.Bus/SPI.Device API.
#
# SPIAdapter uses a reentrant Python-level lock (count + owner tid).
# Each individual byte transfer via the C-level transfer() function
# handles bus arbitration atomically (spi_device_acquire_bus/release
# per transaction).  We never call C-level device.lock()/unlock()
# because holding the bus across FreeRTOS task boundaries with the
# MicroPython GIL held deadlocks against the display driver's SPI flush
# (which runs in a separate FreeRTOS task without the GIL).
#
# wrap_sx126x_cmd() monkey-patches lora.SX1262._cmd() to hold the
# Python-level lock across the CS-low span — including optional
# write_buf/read_buf (FIFO read/write) which follow the main
# write_readinto in the upstream driver while CS is still held low.
# _wait_not_busy() runs BEFORE lock acquisition so the display can
# flush while the LoRa chip is processing the previous command.


class SPIAdapter:

    def __init__(self, spi_device):
        self._dev = spi_device
        self._lock_count = 0
        self._lock_owner = None
        try:
            import _thread
            self._get_tid = _thread.get_ident
        except (ImportError, AttributeError):
            self._get_tid = lambda: 0

    def write(self, buf):
        self._dev.write(buf)

    def write_readinto(self, wr_buf, rd_buf):
        self.lock()
        try:
            tmp_wr = bytearray(len(wr_buf))
            tmp_wr[:] = wr_buf
            tmp_rd = bytearray(len(rd_buf))
            self._dev.write_readinto(tmp_wr, tmp_rd)
            mv = memoryview(rd_buf)
            mv[:] = tmp_rd
        finally:
            self.unlock()

    def readinto(self, buf, fill=0x00):
        self.lock()
        try:
            tmp_wr = bytearray(len(buf))
            for i in range(len(buf)):
                tmp_wr[i] = fill
            self._dev.write_readinto(tmp_wr, buf)
        finally:
            self.unlock()

    def lock(self):
        tid = self._get_tid()
        if self._lock_count == 0 or self._lock_owner != tid:
            self._lock_owner = tid
        self._lock_count += 1
        return self._lock_count

    def unlock(self):
        self._lock_count -= 1
        if self._lock_count == 0:
            self._lock_owner = None
        return self._lock_count


def wrap_sx126x_cmd(radio):
    """Hold SPI bus lock for the CS-low span of lora.SX1262._cmd().

    The upstream _cmd() toggles CS, calls write_readinto, then optionally
    write (FIFO write) or readinto (FIFO read).  This wrapper holds the
    bus lock across those calls so the shared bus cannot be preempted
    while CS is held low.

    _wait_not_busy() runs BEFORE acquiring the lock — it only polls the
    BUSY GPIO pin and holding the bus during that poll blocks the display
    driver's SPI flush (separate FreeRTOS task, shared bus).
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
