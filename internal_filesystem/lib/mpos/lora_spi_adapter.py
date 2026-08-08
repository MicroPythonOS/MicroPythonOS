# ponytail: wraps SPI.Device so the upstream lora driver (which expects
# standard machine.SPI: write_readinto/write/readinto) can talk through
# lvgl_micropython's split SPI.Bus/SPI.Device API.
#
# The upstream driver issues a single write_readinto() per command frame,
# which is already better than the old multi-call pattern because it
# minimises the shared-bus collision window. The "complete fix" for shared
# SPI bus locking (PR #222) still needs C-level changes in
# lvgl_micropython — that's orthogonal.


class SPIAdapter:

    def __init__(self, spi_device):
        self._dev = spi_device

    def write(self, buf):
        self._dev.write(buf)

    def write_readinto(self, wr_buf, rd_buf):
        mv = memoryview(rd_buf)
        for i in range(len(wr_buf)):
            try:
                b = self._dev.read(1, wr_buf[i])
            except Exception:
                b = self._dev.read(1, write=wr_buf[i])
            mv[i] = b[0]

    def readinto(self, buf, fill=0x00):
        mv = memoryview(buf)
        for i in range(len(buf)):
            try:
                b = self._dev.read(1, fill)
            except Exception:
                b = self._dev.read(1, write=fill)
            mv[i] = b[0]
