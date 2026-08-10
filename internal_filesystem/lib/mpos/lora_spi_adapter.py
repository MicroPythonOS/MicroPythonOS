print("lora_spi_adapter: loaded (filesystem copy)")

class SPIAdapter:

    def __init__(self, spi_device):
        self._dev = spi_device

    def write(self, buf):
        for i in range(len(buf)):
            try:
                self._dev.read(1, buf[i])
            except Exception:
                self._dev.read(1, write=buf[i])

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
