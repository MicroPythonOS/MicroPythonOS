# Shared access point for the configured LoRa radio chip.
#
# ponytail: lock + reset + watchdog in one file. Apps use acquire()/release()
# to claim the single physical radio; the watchdog auto-recovers from SPI
# bus contention wedges (PR #222). Meshcore's recovery pattern is now a
# framework service.
import logging

logger = logging.getLogger(__name__)


class LoRaManager:
    radioChip = None
    _holder = None
    _watchdog_active = False
    _last_status = None
    _bad_count = 0
    _last_reinit_ms = 0
    _unresponsive_ms = 0
    _last_check_ms = 0

    @staticmethod
    def acquire(app_name):
        if LoRaManager._holder is None:
            LoRaManager._holder = app_name
            #LoRaManager.start_watchdog()
            if __debug__:
                logger.debug("LoRa lock acquired by %s", app_name)
            return True
        if LoRaManager._holder == app_name:
            return True
        if __debug__:
            logger.debug("LoRa lock denied for %s (held by %s)", app_name, LoRaManager._holder)
        return False

    @staticmethod
    def release(app_name):
        if LoRaManager._holder != app_name:
            return
        LoRaManager.stop_watchdog()
        if LoRaManager.radioChip:
            LoRaManager.radioChip.clear_callback()
            try:
                LoRaManager.radioChip._radio.standby()
            except Exception as e:
                if __debug__:
                    logger.warning("standby on release failed: %s", e)
        LoRaManager._holder = None
        if __debug__:
            logger.debug("LoRa lock released by %s", app_name)

    @property
    def holder(self):
        return LoRaManager._holder

    @staticmethod
    def reset_chip():
        # Toggle CH32 expander config to hardware-reset the LoRa chip.
        # 0x03 = aux + LCD + LoRa OFF (assert reset)
        # 0x13 = aux + LCD + LoRa ON  (release reset)
        # expander config setter handles readback + retry + LVGL safe.
        try:
            import mpos
            exp = getattr(mpos, "io_expander", None)
            if exp is None:
                return False
            import time
            chip = LoRaManager.radioChip
            if chip:
                st_pre = chip.radio._cmd("B", 0xC0, n_read=1)[0]
                print("reset_chip: pre-reset status=0x%02x" % st_pre)
            exp.config = 0x03
            time.sleep_ms(200)
            exp.config = 0x13
            time.sleep_ms(200)
            if not exp.config[0]:
                if __debug__:
                    logger.debug("CH32 LoRa reset: readback check failed")
                return False
            chip = LoRaManager.radioChip
            if not chip:
                if __debug__:
                    logger.debug("LoRa chip reset via CH32 expander")
                return True
            r = chip.radio
            print("reset_chip: expander confirms lora_reset=%s" % exp.config[0])
            for retry in range(3):
                r._sleep = True
                r._configured = False
                r._rx = False
                tcxo_mv = getattr(LoRaManager, "_tcxo_mv", None)
                if tcxo_mv:
                    tcxo_start_us = LoRaManager._tcxo_start_us
                    timeout = (tcxo_start_us * 1000 + 15624) // 15625
                    dv = tcxo_mv // 100
                    tcxo_trim_lookup = (16, 17, 18, 22, 24, 27, 30, 33)
                    while dv not in tcxo_trim_lookup:
                        dv -= 1
                    reg_trim = tcxo_trim_lookup.index(dv)
                    r._cmd(">BI", 0x97, (reg_trim << 24) + timeout)
                    time.sleep_ms(15)
                    r._clear_errors()
                    try:
                        r._check_error()
                    except Exception as e:
                        print("reset_chip: TCXO error check FAILED: %s" % e)
                r._cmd("BB", 0x8A, 1)  # SET_PACKET_TYPE → LoRa
                r._clear_irq()
                st = r._cmd("B", 0xC0, n_read=1)[0]
                print("reset_chip: status=0x%02x (mode=%d) [retry %d]" %
                  (st, (st >> 4) & 7, retry))
                if st != 0x00:
                    break
                print("reset_chip: chip unresponsive, re-resetting")
                exp.config = 0x03
                time.sleep_ms(200)
                exp.config = 0x13
                time.sleep_ms(200)
            else:
                print("reset_chip: FAILED after 3 tries")
                return False
            if __debug__:
                logger.debug("LoRa chip reset via CH32 expander")
            return True
        except Exception as e:
            if __debug__:
                logger.debug("CH32 LoRa reset failed: %s", e)
            return False

    @staticmethod
    def is_healthy():
        st = LoRaManager._last_status
        if st is None:
            return False
        return (st & 0x70) not in (0x00, 0x10)

    @staticmethod
    def start_watchdog(interval_ms=2000):
        if LoRaManager._watchdog_active:
            return
        LoRaManager._watchdog_active = True
        LoRaManager._bad_count = 0
        LoRaManager._last_reinit_ms = 0
        LoRaManager._unresponsive_ms = 0
        LoRaManager._last_check_ms = 0
        try:
            from mpos import TaskManager
            TaskManager.create_task(LoRaManager._watchdog_loop(interval_ms))
        except Exception as e:
            LoRaManager._watchdog_active = False
            if __debug__:
                logger.debug("Watchdog task creation failed: %s", e)

    @staticmethod
    def stop_watchdog():
        LoRaManager._watchdog_active = False

    @staticmethod
    async def _watchdog_loop(interval_ms):
        from mpos import TaskManager
        try:
            while LoRaManager._watchdog_active:
                await TaskManager.sleep_ms(interval_ms)
                if not LoRaManager._watchdog_active:
                    break
                if LoRaManager._holder is None:
                    LoRaManager._watchdog_active = False
                    break
                LoRaManager._check_once()
        finally:
            LoRaManager._watchdog_active = False

    @staticmethod
    def _check_once():
        import time
        chip = LoRaManager.radioChip
        if chip is None:
            return

        try:
            st = chip.try_get_status()
        except Exception:
            st = 0x00

        if st is None:
            return  # bus busy (other thread mid-SPI), skip this iteration

        LoRaManager._last_status = st
        mode = st & 0x70

        # FS (0x30) = PLL locking, normal transient between TX and RX.
        # RX (0x50) = actively receiving.
        # TX (0x60) = transmitting.
        if mode in (0x30, 0x50, 0x60):
            LoRaManager._bad_count = 0
            LoRaManager._unresponsive_ms = 0
            return

        LoRaManager._bad_count += 1
        if st == 0x00:
            LoRaManager._unresponsive_ms += 2000
            if __debug__ and LoRaManager._bad_count == 1:
                logger.debug("Watchdog: status 0x00 (count=1), monitoring")
        else:
            LoRaManager._unresponsive_ms = 0
            if __debug__:
                logger.warning("Watchdog: unexpected status 0x%02x mode=0x%02x (count=%d)", st, mode, LoRaManager._bad_count)

        if LoRaManager._unresponsive_ms > 30000:
            if __debug__:
                logger.debug("Watchdog: chip unresponsive for 30s, force-releasing lock")
            LoRaManager.release(LoRaManager._holder)
            return

        now = time.ticks_ms()
        # Rate-limit recovery to once per 5s to avoid reset storms
        # (a single 0x00 may be transient SPI bus contention, PR #222).
        if LoRaManager._last_reinit_ms and time.ticks_diff(now, LoRaManager._last_reinit_ms) < 5000:
            if __debug__:
                logger.debug("Watchdog: rate-limited, skipping recovery (last=%dms ago)",
                    time.ticks_diff(now, LoRaManager._last_reinit_ms))
            return

        # Two-tier recovery:
        #   Soft: non-0x00 but wrong mode -> start_recv() to re-enter RX
        #   Hard: 3+ consecutive 0x00 -> HW reset + full reconstruction
        if st == 0x00:
            if LoRaManager._bad_count < 3:
                return
            bad = LoRaManager._bad_count
            LoRaManager._last_reinit_ms = now
            LoRaManager._bad_count = 0

            if __debug__:
                logger.debug("Watchdog: hardware reset (status 0x00, bad=%d)", bad)

            if LoRaManager._lora_spi_device is not None and LoRaManager.reset_chip():
                try:
                    from machine import Pin
                    from lora import SX1262
                    from mpos.lora_spi_adapter import SPIAdapter, wrap_sx126x_cmd
                    from mpos.polled_sx126x import PolledSX126x
                    irq, rst, gpio, cs = LoRaManager._lora_pins
                    radio = SX1262(
                        spi=SPIAdapter(LoRaManager._lora_spi_device),
                        cs=Pin(cs, Pin.OUT, value=1),
                        busy=Pin(gpio, Pin.IN),
                        dio1=Pin(irq, Pin.IN),
                        dio2_rf_sw=False,
                        dio3_tcxo_millivolts=3000,
                        dio3_tcxo_start_time_us=1000,
                        reset=None,  # CH32 expander drives reset
                    )
                    wrap_sx126x_cmd(radio)
                    new_chip = PolledSX126x(radio)
                    cfg = chip._cfg
                    if cfg:
                        radio.configure(cfg)
                        radio.calibrate_image()
                    if chip._user_callback:
                        new_chip.set_callback(chip._user_callback)
                    LoRaManager.radioChip = new_chip
                    if __debug__:
                        logger.debug("Watchdog: hardware reset + full reconstruction OK")
                except Exception as e:
                    if __debug__:
                        logger.debug("Watchdog: reconstruction failed: %s", e)
        else:
            # Non-zero status but wrong mode: try soft recovery (re-enter RX).
            if __debug__:
                logger.debug("Watchdog: soft recovery (status 0x%02x, mode=0x%02x)", st, mode)
            LoRaManager._last_reinit_ms = now
            LoRaManager._bad_count = 0
            try:
                chip._radio._clear_irq()
                chip._radio.start_recv(continuous=True)
            except Exception as e:
                if __debug__:
                    logger.debug("Watchdog: soft recovery failed: %s", e)
