# SPI-polling wrapper for upstream lora.SX126x (SX1261, SX1262).
#
# The upstream driver's non-blocking send/recv depends on the DIO1 ISR,
# which is unreliable on ESP32 under LVGL load. This wrapper replaces
# ISR-dependent I/O with SPI polling, leaving the upstream driver
# untouched for everything else (configure, standby, sleep, etc.).
#
# Callers access the underlying radio via the .radio property.
import logging
import time

logger = logging.getLogger(__name__)

from lora import SX1262 as _UpstreamSX1262  # noqa: F401 — re-exported for type info
# IRQ flags are defined here rather than imported from lora.sx126x
# because MicroPython const() values in compiled .mpy modules are
# compile-time inlined and not importable across modules. These are
# hardware register masks from the SX126x datasheet — the upstream
# driver defines identical private copies.
from micropython import const

_TX_DONE = const(1 << 0)
_RX_DONE = const(1 << 1)
_CRC_ERR = const(1 << 6)

_STATUS = {
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


class PolledSX126x:
    TX_DONE = _TX_DONE
    RX_DONE = _RX_DONE
    CRC_ERR = _CRC_ERR
    STATUS = _STATUS

    def __init__(self, radio):
        self._radio = radio
        self._last_events = 0
        self._user_callback = None
        self._cfg = None
        self._suspended = False  # SPI bus race workaround
        self._in_op = False  # ponytail: guard watchdog during send/recv
        # ponytail: intercept radio.configure so _cfg is always tracked,
        # even when apps call self.lora_device.radio.configure() directly.
        _orig_configure = radio.configure

        def _wrapped_configure(cfg):
            self._cfg = cfg
            _orig_configure(cfg)

        radio.configure = _wrapped_configure
        radio.set_irq_callback(self._irq_handler)

    @property
    def radio(self):
        return self._radio

    # SPI bus race workaround: call suspend() before any multi-step
    # SPI operation that runs in a separate thread (configure,
    # calibrate_image). The watchdog thread and the main-thread DIO1
    # ISR both access SPI concurrently without hardware-level locking.
    def suspend(self):
        self._suspended = True

    def resume(self):
        self._suspended = False

    def disable_irq(self):
        # ponytail: teardown DIO1 ISR so the watchdog can safely
        # hardware-reset and reconstruct the chip without spurious
        # ISR calls into freed/outdated state.
        dio1 = getattr(self._radio, "_dio1", None)
        if dio1:
            try:
                dio1.irq(None)
            except Exception:
                pass

    def _irq_handler(self):
        # SPI bus race workaround: the DIO1 ISR fires in the main
        # MicroPython thread.  We MUST NOT call poll_send() here
        # because send() already handles TX completion in its own
        # poll loop — calling poll_send() from both paths races
        # (ISR sets _tx=False before send()'s poll_send() runs,
        # making it believe send is still in progress).
        #
        # The ISR's only job is to forward flags to the app callback.
        if self._suspended:
            if __debug__:
                logger.warning("DIO1 IRQ fired while suspended (SPI bus race workaround)")
            return
        owner = getattr(self._radio, "_lock_owner", None)
        if owner is not None:
            for _ in range(10):
                time.sleep_ms(5)
                if getattr(self._radio, "_lock_owner", None) is None:
                    break
            else:
                return  # gave up after 50ms
        # ponytail: if the chip is stuck BUSY (e.g. shared SPI bus
        # contention), _get_irq() times out.  Catch it so the ISR
        # doesn't crash — the data path already polls _get_irq() in
        # recv() so a missed ISR cycle is harmless.
        try:
            flags = self._radio._get_irq()
            self._last_events = flags
            if self._user_callback:
                self._user_callback(flags)
        except Exception:
            if __debug__:
                logger.warning("DIO1 ISR: SPI read failed (chip busy)")

    def configure(self, cfg):
        self._radio.configure(cfg)
        self._cfg = cfg

    def set_callback(self, callback):
        self._user_callback = callback
        self._radio.start_recv(continuous=True)

    def clear_callback(self):
        self._user_callback = None

    def try_get_status(self):
        try:
            import _thread
            owner = getattr(self._radio, "_lock_owner", None)
            if owner is not None and owner != _thread.get_ident():
                return None
        except (ImportError, AttributeError):
            pass
        return self.get_status()

    def send(self, data):
        if not isinstance(data, (bytes, bytearray)):
            return 0, -804
        self._in_op = True
        try:
            return self._send_impl(data)
        finally:
            self._in_op = False

    def _send_impl(self, data):
        # ponytail: drain any pending RX before clear_errors/clear_irq.
        # prepare_send() → _standby() → _clear_irq() clears ALL IRQ flags
        # including RX_DONE. If a packet arrived but the DIO1 ISR hasn't
        # fired yet (MicroPython IRQs can lag under LVGL load), this loses
        # the packet. Reading _get_irq() first unlatches RX_DONE from
        # hardware; _read_data drains the buffer so the chip can re-arm.
        if self._radio._get_irq() & _RX_DONE:
            self._read_data(0)
        self._radio._clear_errors()
        self._radio.prepare_send(data)
        self._radio.start_send()
        ms = max(100, (self._radio.get_time_on_air_us(len(data)) // 1000) + 120)
        time.sleep_ms(ms)
        flags = self._radio._get_irq()
        if flags & _TX_DONE:
            self._radio.poll_send()
            return len(data), 0
        t0 = time.ticks_ms()
        deadline = time.ticks_add(t0, 2000)
        while time.ticks_diff(time.ticks_ms(), deadline) < 0:
            flags = self._radio._get_irq()
            if flags & _TX_DONE:
                self._radio.poll_send()
                return len(data), 0
            time.sleep_ms(20)
        ''' this is NOT the cause for the busy error:
        # ponytail: after TX timeout, try to restore RX so the chip
        # doesn't sit wedged in STDBY_RC.  If BUSY is stuck, let the
        # watchdog hard-reset.
        try:
            self._radio.start_recv(continuous=True)
        except Exception:
            pass
        '''
        return 0, -5

    def recv(self, len_=0):
        self._in_op = True
        try:
            return self._recv_impl(len_)
        finally:
            self._in_op = False

    def _recv_impl(self, len_):
        # Acknowledge pending IRQ events via SPI. The SX1262 gates the RX
        # buffer behind the IRQ flag: GET_RX_BUFFER_STATUS returns rx_len=0
        # until GET_IRQ_STATUS has been read and shows RX_DONE. Since the
        # DIO1 ISR is unreliable on ESP32, this SPI poll ensures the buffer
        # is unlocked before _read_data() accesses it.
        try:
            flags = self._radio._get_irq()
            if flags:
                self._last_events = flags
        except Exception:
            pass
        return self._read_data(len_)

    def _read_data(self, len_):
        try:
            res = self._radio._cmd("B", 0x13, n_read=3)
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
        crc_error = (flags & _CRC_ERR) != 0

        self._radio._clear_irq()
        try:
            self._radio.start_recv(continuous=True)
        except Exception:
            pass

        status = -7 if crc_error else 0
        return bytes(data), status

    def get_irq_status(self):
        flags = self._last_events
        if not flags:
            try:
                flags = self._radio._get_irq()
            except Exception:
                pass
        return flags

    def clear_irq_status(self):
        self._last_events = 0
        try:
            self._radio._clear_irq()
        except Exception:
            pass

    def start_recv(self):
        try:
            self._radio._standby()
            self._radio._clear_irq()
            self._radio.start_recv(continuous=True)
        except Exception:
            pass

    def get_status(self):
        try:
            res = self._radio._cmd("B", 0x12, n_read=3)
            status = res[0]
            if __debug__ and status == 0x00:
                logger.warning("get_status raw=%s status=0x00 (rx_mode=%s irq=%02x%02x)",
                    bytes(res), (status & 0x70) >> 4, res[1], res[2])
            return status
        except Exception as e:
            if __debug__:
                logger.warning("get_status exception: %s", e)
            return 0x00

    def get_packet_status(self):
        try:
            res = self._radio._cmd("B", 0x14, n_read=4)
            return (res[1] << 16) | (res[2] << 8) | res[3]
        except Exception:
            return 0

    @property
    def rssi(self):
        return getattr(self._radio, "_last_rssi", 0.0)

    @property
    def snr(self):
        return getattr(self._radio, "_last_snr", 0.0)
