# MPOS adapter: wraps upstream lora.SX1262 to provide the API that
# existing callers (fri3d_2026, lora_chat, meshcore) already use.
#
# ponytail: one adapter file (~200 lines) instead of the old 2426-line
# driver fork. Upstream lora files in lib/lora/ are never touched.
# Board-specific quirks (SPI adapter, CH32 reset, dio2_rf_sw=False,
# TCXO voltage) live here only.

from micropython import const

try:
    from machine import Pin
except ImportError:
    pass  # ponytail: unix desktop port has no machine.Pin

from lora import SX1262 as _UpstreamSX1262
from mpos.lora_spi_adapter import SPIAdapter

_IRQ_TX_DONE = const(1 << 0)
_IRQ_RX_DONE = const(1 << 1)
_IRQ_CRC_ERR = const(1 << 6)
_IRQ_TIMEOUT = const(1 << 9)
_IRQ_HEADER_ERR = const(1 << 5)

_ERROR_NAMES = {
    0: "ERR_NONE",
    -1: "ERR_UNKNOWN",
    -2: "ERR_CHIP_NOT_FOUND",
    -5: "ERR_TX_TIMEOUT",
    -6: "ERR_RX_TIMEOUT",
    -7: "ERR_CRC_MISMATCH",
    -12: "ERR_INVALID_FREQUENCY",
    -13: "ERR_INVALID_OUTPUT_POWER",
    -705: "ERR_SPI_CMD_TIMEOUT",
    -706: "ERR_SPI_CMD_INVALID",
    -707: "ERR_SPI_CMD_FAILED",
}


class MPOSLoRa:
    TX_DONE = _IRQ_TX_DONE
    RX_DONE = _IRQ_RX_DONE
    STATUS = _ERROR_NAMES
    ADDR_FILT_OFF = 0
    ADDR_FILT_NODE = 1
    ADDR_FILT_NODE_BROAD = 2
    PREAMBLE_DETECT_OFF = 0x04
    PREAMBLE_DETECT_8 = 0x04
    PREAMBLE_DETECT_16 = 0x05
    PREAMBLE_DETECT_24 = 0x06
    PREAMBLE_DETECT_32 = 0x07

    def __init__(self, spi_device, irq, rst, gpio, cs_pin):
        cs = Pin(cs_pin, Pin.OUT, value=1)
        busy = Pin(gpio, Pin.IN)
        dio1 = Pin(irq, Pin.IN)

        self._radio = _UpstreamSX1262(
            spi=SPIAdapter(spi_device),
            cs=cs,
            busy=busy,
            dio1=dio1,
            dio2_rf_sw=False,
            dio3_tcxo_millivolts=3000,
            dio3_tcxo_start_time_us=1000,  # ponytail: upstream default, test if still works post-reset-fix
            reset=None,
        )

        self._blocking = True
        self._user_callback = None
        self._begin_kwargs = {}
        self._last_events = 0

        self._radio.set_irq_callback(self._irq_handler)

    def _irq_handler(self):
        flags = self._radio._get_irq()
        self._last_events = flags
        if flags & _IRQ_TX_DONE:
            try:
                self._radio.poll_send()
            except Exception as e:
                import sys
                sys.print_exception(e)
        if self._user_callback:
            self._user_callback(flags)

    def begin(
        self,
        freq=434.0,
        bw=125.0,
        sf=9,
        cr=7,
        syncWord=0x12,
        power=14,
        currentLimit=60.0,
        preambleLength=8,
        implicit=False,
        implicitLen=0xFF,
        crcOn=True,
        txIq=False,
        rxIq=False,
        tcxoVoltage=3.0,
        useRegulatorLDO=False,
        blocking=True,
    ):
        if implicit:
            self._radio._implicit_header = True

        cfg = {
            "freq_khz": int(freq * 1000),
            "bw": bw,
            "sf": sf,
            "coding_rate": cr,
            "syncword": syncWord,
            "preamble_len": preambleLength,
            "output_power": power,
        }
        if txIq or rxIq:
            cfg["invert_iq_tx"] = txIq
            cfg["invert_iq_rx"] = rxIq

        self._radio.configure(cfg)
        self._radio.calibrate_image()

        self._blocking = blocking
        self._begin_kwargs = {
            "freq": freq,
            "bw": bw,
            "sf": sf,
            "cr": cr,
            "syncWord": syncWord,
            "power": power,
            "currentLimit": currentLimit,
            "preambleLength": preambleLength,
            "implicit": implicit,
            "implicitLen": implicitLen,
            "crcOn": crcOn,
            "txIq": txIq,
            "rxIq": rxIq,
            "tcxoVoltage": tcxoVoltage,
            "useRegulatorLDO": useRegulatorLDO,
            "blocking": blocking,
        }
        return 0

    def setBlockingCallback(self, blocking, callback=None):
        self._blocking = blocking
        if blocking:
            self._radio.standby()
            self._user_callback = None
        else:
            self._user_callback = callback
            self._radio.start_recv(continuous=True)
        return 0

    def send(self, data):
        if not isinstance(data, (bytes, bytearray)):
            return 0, -804
        if self._blocking:
            try:
                self._radio._clear_errors()  # _standby() sets XOSC_START_ERR; SX1262 HW needs it cleared to transmit
                self._radio.send(data)
                return len(data), 0
            except Exception as e:
                import sys
                sys.print_exception(e)
                return 0, -1
        else:
            try:
                self._radio._clear_errors()  # _standby() sets XOSC_START_ERR; SX1262 HW needs it cleared to transmit
                self._radio.prepare_send(data)
                self._radio.start_send()
                return len(data), 0
            except Exception as e:
                import sys
                sys.print_exception(e)
                return 0, -1

    def recv(self, len_=0, timeout_en=False, timeout_ms=0):
        if self._blocking:
            timeout = timeout_ms if timeout_en else None
            rx_len = len_ if len_ else 0xFF
            try:
                pkt = self._radio.recv(timeout_ms=timeout, rx_length=rx_len)
            except Exception:
                return b"", -1
            if pkt is None:
                return b"", -6
            status = -7 if pkt.crc_error else 0
            return bytes(pkt), status
        else:
            return self._read_data(len_)

    def _read_data(self, len_):
        try:
            res = self._radio._cmd("B", 0x13, n_read=3)  # GET_RX_BUFFER_STATUS
        except Exception:
            return b"", -1

        rx_len = res[1]
        rx_ptr = res[2]

        if len_ > 0 and len_ < rx_len:
            rx_len = len_

        if rx_len == 0:
            return b"", -6

        data = bytearray(rx_len)
        try:
            self._radio._cmd("BB", 0x1E, rx_ptr, n_read=1, read_buf=data)
        except Exception:
            return b"", -1

        pkt_status = self._radio._cmd("B", 0x14, n_read=4)
        import struct
        rssi, snr = struct.unpack("xBbx", pkt_status)

        flags = self._last_events
        crc_error = (flags & _IRQ_CRC_ERR) != 0

        self._radio._clear_irq()
        try:
            self._radio.start_recv(continuous=True)
        except Exception:
            pass

        status = -7 if crc_error else 0
        return bytes(data), status

    def sleep(self, retainConfig=True):
        self._radio.sleep(warm_start=retainConfig)

    def standby(self):
        self._radio.standby()

    def setDio2AsRfSwitch(self, enable):
        pass

    def setRxIq(self, rxIq):
        self._radio._invert_iq[0] = rxIq

    def setTxIq(self, txIq):
        self._radio._invert_iq[1] = txIq

    def getRSSI(self):
        return self._radio._last_rssi if hasattr(self._radio, "_last_rssi") else 0.0

    def getSNR(self):
        return self._radio._last_snr if hasattr(self._radio, "_last_snr") else 0.0

    def getStatus(self):
        try:
            res = self._radio._cmd("B", 0x12, n_read=3)  # GET_IRQ_STATUS workaround
            return res[0]
        except Exception:
            return 0x00

    def getPacketStatus(self):
        try:
            res = self._radio._cmd("B", 0x14, n_read=4)
            return (res[1] << 16) | (res[2] << 8) | res[3]
        except Exception:
            return 0

    def getPacketLength(self):
        try:
            res = self._radio._cmd("B", 0x13, n_read=3)
            return res[1]
        except Exception:
            return 0

    def getIrqStatus(self):
        flags = self._last_events
        if not flags:
            try:
                flags = self._radio._get_irq()
            except Exception:
                pass
        return flags

    def clearIrqStatus(self):
        self._last_events = 0
        try:
            self._radio._clear_irq()
        except Exception:
            pass

    def startReceive(self):
        try:
            self._radio._standby()
            self._radio._clear_irq()
            self._radio.start_recv(continuous=True)
        except Exception:
            pass
