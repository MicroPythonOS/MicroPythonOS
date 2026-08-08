# ponytail: wraps SPI.Device so the upstream lora driver (which expects
# standard machine.SPI: write_readinto/write/readinto) can talk through
# lvgl_micropython's split SPI.Bus/SPI.Device API.
#
# write_readinto() and readinto() hold SPI.Device.lock() for the byte-loop
# span, so the shared bus can't be preempted mid-frame (closes PR #222 gap).
# Lock/unlock are thin wrappers around ESP-IDF spi_device_acquire_bus /
# spi_device_release_bus, exposed via machine.SPI.Device.lock()/unlock().


class SPIAdapter:

    def __init__(self, spi_device):
        self._dev = spi_device

    def write(self, buf):
        self._dev.write(buf)

    def write_readinto(self, wr_buf, rd_buf):
        self._dev.lock()
        try:
            mv = memoryview(rd_buf)
            for i in range(len(wr_buf)):
                try:
                    b = self._dev.read(1, wr_buf[i])
                except Exception:
                    b = self._dev.read(1, write=wr_buf[i])
                mv[i] = b[0]
        finally:
            self._dev.unlock()

    def readinto(self, buf, fill=0x00):
        self._dev.lock()
        try:
            mv = memoryview(buf)
            for i in range(len(buf)):
                try:
                    b = self._dev.read(1, fill)
                except Exception:
                    b = self._dev.read(1, write=fill)
                mv[i] = b[0]
        finally:
            self._dev.unlock()

    def lock(self):
        self._dev.lock()

    def unlock(self):
        self._dev.unlock()
