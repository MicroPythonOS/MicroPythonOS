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
            # LoRaManager.start_watchdog() # this causes a complete hang/deadlock fairly quickly
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
            if chip and __debug__:
                try:
                    st_pre = chip.radio._cmd("B", 0xC0, n_read=1)[0]
                    logger.debug("reset_chip: pre-reset status=0x%02x", st_pre)
                except Exception:
                    logger.debug("reset_chip: pre-reset status read failed (chip non-responsive)")
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
            if __debug__:
                logger.debug("reset_chip: expander confirms lora_reset=%s", exp.config[0])
            for retry in range(3):
                try:
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
                            logger.warning("reset_chip: TCXO error check FAILED: %s", e)
                    r._cmd("BB", 0x8A, 1)  # SET_PACKET_TYPE → LoRa
                    r._cmd(">BHHHH", 0x08,
                        579,    # IrqMask: TX(1)|RX(2)|CRC_ERR(64)|TIMEOUT(512)
                        515,    # DIO1Mask: TX(1)|RX(2)|TIMEOUT(512)
                        0, 0)   # DIO2Mask, DIO3Mask
                    r._clear_irq()
                    st = r._cmd("B", 0xC0, n_read=1)[0]
                except Exception as e:
                    if __debug__:
                        logger.debug("reset_chip: SPI failed (retry %d): %s",
                                     retry, e)
                    st = 0x00
                if __debug__:
                    logger.debug("reset_chip: status=0x%02x (mode=%d) [retry %d]",
                        st, (st >> 4) & 7, retry)
                if st != 0x00:
                    break
                if retry < 2:
                    logger.warning("reset_chip: chip unresponsive, re-resetting")
                    exp.config = 0x03
                    time.sleep_ms(200)
                    exp.config = 0x13
                    time.sleep_ms(200)
            else:
                logger.warning("reset_chip: FAILED after 3 tries")
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
    def start_watchdog(interval_ms=4321):
        if LoRaManager._watchdog_active:
            logger.info("not enabling watchdog because already enabled")
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
                logger.info("watchdog loop")
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
            logger.info("watchdog _check_once exits because no radioChip")
            return

        # ponytail: don't interfere with an active send/recv.
        if chip._in_op:
            logger.info("watchdog _check_once exits because _in_op (active operation)")
            return

        try:
            st = chip.try_get_status()
            logger.info(f"watchdog got status {st}")
        except Exception:
            st = 0x00

        if st is None:
            return  # bus busy (other thread mid-SPI), skip this iteration

        LoRaManager._last_status = st
        mode = st & 0x70

        # Only continuous RX (0x50) is healthy — the chip should always be
        # listening. Transient modes (FS 0x40, TX 0x60, STANDBY 0x20/0x30)
        # are brief during tx/rx transitions; a stuck non-RX mode means the
        # chip fell out of receive and needs recovery.
        if mode == 0x50:
            if LoRaManager._bad_count:
                if __debug__:
                    logger.debug("Watchdog: RX recovered after %d bad reads",
                                 LoRaManager._bad_count)
            LoRaManager._bad_count = 0
            LoRaManager._unresponsive_ms = 0
            return

        LoRaManager._bad_count += 1
        if st in (0x00, 0xff) or (st & 0x70) not in (0x20, 0x30, 0x40, 0x50, 0x60):
            LoRaManager._unresponsive_ms += 2000
            if __debug__ and LoRaManager._bad_count == 1:
                logger.debug("Watchdog: status 0x%02x (count=1), monitoring", st)
        else:
            LoRaManager._unresponsive_ms = 0
            if __debug__:
                logger.warning("Watchdog: not in RX, status 0x%02x mode=0x%02x (count=%d)", st, mode, LoRaManager._bad_count)

        if LoRaManager._unresponsive_ms > 30000:
            if __debug__:
                logger.debug("Watchdog: chip unresponsive for 30s, force-releasing lock")
            LoRaManager.release(LoRaManager._holder)
            return

        now = time.ticks_ms()
        # Rate-limit recovery to once per 5s to avoid reset storms.
        if LoRaManager._last_reinit_ms and time.ticks_diff(now, LoRaManager._last_reinit_ms) < 5000:
            if __debug__:
                logger.debug("Watchdog: rate-limited, skipping recovery (last=%dms ago)",
                    time.ticks_diff(now, LoRaManager._last_reinit_ms))
            return

        # Two-tier recovery:
        #   Light: non-0x00 -> clear IRQ + restart continuous RX
        #   Hard:  3+ consecutive 0x00/0xff or corrupt mode -> HW reset via CH32
        if st in (0x00, 0xff) or (st & 0x70) not in (0x20, 0x30, 0x40, 0x50, 0x60):
            if LoRaManager._bad_count < 3:
                return
            bad = LoRaManager._bad_count
            LoRaManager._last_reinit_ms = now
            LoRaManager._bad_count = 0

            if __debug__:
                logger.debug("Watchdog: hardware reset (status 0x00, bad=%d)", bad)

            chip.disable_irq()
            if LoRaManager._lora_spi_device is not None and LoRaManager.reset_chip():
                # ponytail: reset_chip() already reset state flags
                # (_sleep=True, _configured=False, _rx=False) and did
                # TCXO init + SET_PACKET_TYPE + DIO_IRQ + _clear_irq
                # on the existing radio object. Reuse it — creating a
                # new SX1262 glitches the CS pin and fails.
                try:
                    r = chip._radio
                    cfg = chip._cfg
                    if cfg:
                        chip.suspend()
                        try:
                            r.configure(cfg)
                            r.calibrate_image()
                        finally:
                            chip.resume()
                    if chip._user_callback:
                        chip.set_callback(chip._user_callback)
                    if __debug__:
                        logger.debug("Watchdog: hardware reset + reconfigure OK")
                except Exception as e:
                    if __debug__:
                        logger.debug("Watchdog: reconfigure failed: %s", e)
        else:
            # Non-zero status but wrong mode: try light recovery.
            if __debug__:
                logger.debug("Watchdog: light recovery (status 0x%02x, mode=0x%02x)", st, mode)
            LoRaManager._last_reinit_ms = now
            LoRaManager._bad_count = 0
            try:
                chip._radio._clear_irq()
                chip._radio.start_recv(continuous=True)
            except Exception as e:
                if __debug__:
                    logger.debug("Watchdog: light recovery failed: %s", e)

    @staticmethod
    def blunt_reset():
        """Public test hook: hardware-reset the LoRa chip via CH32
        expander ONLY.  No SPI re-initialization — the chip comes back
        in a raw post-reset state.  The watchdog will detect the dead
        chip on its next cycle and run the real recovery path."""
        try:
            import mpos
            exp = getattr(mpos, "io_expander", None)
            if exp is None:
                return False
            import time
            exp.config = 0x03
            time.sleep_ms(200)
            exp.config = 0x13
            time.sleep_ms(200)
            if not exp.config[0]:
                if __debug__:
                    logger.debug("blunt_reset: readback check failed")
                return False
            if __debug__:
                logger.debug("blunt_reset: OK (watchdog will recover in ~6s)")
            return True
        except Exception as e:
            if __debug__:
                logger.debug("blunt_reset: failed: %s", e)
            return False
