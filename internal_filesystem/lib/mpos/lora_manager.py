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
        # ponytail: exp.config writes can silently fail on CH32 fw v2.0.1
        # due to I2C bus contention with LVGL's periodic expander reads
        # (buttons, joystick). Pausing the LVGL task handler lets the write
        # land cleanly. See issue #224.
        task_handler = None
        try:
            import mpos
            exp = getattr(mpos, "io_expander", None)
            if exp is None:
                return
            task_handler = getattr(getattr(mpos, "ui", None), "task_handler", None)
            import time
            if task_handler:
                task_handler.disable()
            exp.config = 0x03
            time.sleep_ms(100)
            exp.config = 0x13
            time.sleep_ms(100)
            if __debug__:
                logger.debug("LoRa chip reset via CH32 expander")
        except Exception as e:
            if __debug__:
                logger.debug("CH32 LoRa reset failed: %s", e)
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

        if mode == 0x50:
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

            LoRaManager.reset_chip()

            try:
                kwargs = chip._begin_kwargs
                chip.begin(**kwargs)
                blocking = kwargs.get("blocking", True)
                cb = chip._user_callback
                chip.setBlockingCallback(blocking, cb)
                if __debug__:
                    logger.debug("Watchdog: re-init complete")
            except Exception as e:
                if __debug__:
                    logger.debug("Watchdog: re-init failed: %s", e)
