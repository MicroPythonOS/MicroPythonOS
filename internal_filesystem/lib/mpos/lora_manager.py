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
    _watchdog_thread = None
    _last_status = None
    _bad_count = 0
    _last_reinit_ms = 0
    _unresponsive_ms = 0
    _last_check_ms = 0

    @staticmethod
    def acquire(app_name):
        if LoRaManager._holder is None:
            LoRaManager._holder = app_name
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
            try:
                LoRaManager.radioChip.sleep(retainConfig=False)
            except Exception:
                pass
        LoRaManager._holder = None
        if __debug__:
            logger.debug("LoRa lock released by %s", app_name)

    @property
    def holder(self):
        return LoRaManager._holder

    @staticmethod
    def reset_chip():
        # Toggle the CH32 expander config to hardware-reset the LoRa chip.
        # Uses task_handler.disable() to prevent LVGL I2C reads from
        # corrupting config writes (issue #224). Returns True on success.
        task_handler = None
        try:
            import mpos
            exp = getattr(mpos, "io_expander", None)
            if exp is None:
                return False
            task_handler = getattr(getattr(mpos, "ui", None), "task_handler", None)
            import time
            if task_handler:
                task_handler.disable()

            # Assert reset: 0x03 = aux on + LCD on + LoRa OFF
            for _ in range(5):
                exp.config = 0x03
                time.sleep_ms(10)
                try:
                    cfg = exp.config  # (lora_reset, remap, reboot, lcd_reset, aux_power)
                except Exception:
                    continue
                if cfg[0] is False:
                    break
            else:
                if __debug__:
                    logger.debug("CH32 LoRa reset: couldn't assert reset")
                return False

            time.sleep_ms(100)

            # Release reset: 0x13 = aux on + LCD on + LoRa ON
            for _ in range(10):
                exp.config = 0x13
                time.sleep_ms(10)
                try:
                    cfg = exp.config
                except Exception:
                    continue
                if cfg[0]:
                    if __debug__:
                        logger.debug("LoRa chip reset via CH32 expander")
                    return True

            if __debug__:
                logger.debug("CH32 LoRa reset: couldn't release reset")
            return False
        except Exception as e:
            if __debug__:
                logger.debug("CH32 LoRa reset failed: %s", e)
            return False
        finally:
            if task_handler:
                task_handler.enable()

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
            import _thread
            _thread.start_new_thread(LoRaManager._watchdog_loop, (interval_ms,))
        except Exception as e:
            LoRaManager._watchdog_active = False
            if __debug__:
                logger.debug("Watchdog thread start failed: %s", e)

    @staticmethod
    def stop_watchdog():
        LoRaManager._watchdog_active = False

    @staticmethod
    def _watchdog_loop(interval_ms):
        import time
        while LoRaManager._watchdog_active:
            time.sleep_ms(interval_ms)
            if not LoRaManager._watchdog_active:
                break
            if LoRaManager._holder is None:
                LoRaManager._watchdog_active = False
                break
            LoRaManager._check_once()

    @staticmethod
    def _check_once():
        import time
        chip = LoRaManager.radioChip
        if chip is None:
            return

        try:
            st = chip.getStatus()
        except Exception:
            st = 0x00

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
        else:
            LoRaManager._unresponsive_ms = 0

        if LoRaManager._unresponsive_ms > 30000:
            if __debug__:
                logger.debug("Watchdog: chip unresponsive for 30s, force-releasing lock")
            LoRaManager.release(LoRaManager._holder)
            return

        now = time.ticks_ms()
        if LoRaManager._last_reinit_ms and time.ticks_diff(now, LoRaManager._last_reinit_ms) < 5000:
            return

        if st == 0x00 or LoRaManager._bad_count >= 3:
            if __debug__:
                logger.debug("Watchdog: re-init (status 0x%02x, bad=%d)", st, LoRaManager._bad_count)
            LoRaManager._last_reinit_ms = now
            LoRaManager._bad_count = 0

            if not LoRaManager.reset_chip():
                if __debug__:
                    logger.debug("Watchdog: reset failed, skipping re-init (status 0x%02x)", st)
                return

            try:
                kwargs = chip._begin_kwargs
                chip.begin(**kwargs)
                blocking = chip._blocking  # ponytail: use live state, not _begin_kwargs[blocking=True]
                cb = chip._user_callback
                chip.setBlockingCallback(blocking, cb)
                if __debug__:
                    logger.debug("Watchdog: re-init complete (was status 0x%02x)", st)
            except Exception as e:
                if __debug__:
                    logger.debug("Watchdog: re-init failed: %s", e)
