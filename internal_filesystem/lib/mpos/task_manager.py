import logging

import asyncio # this is the only place where asyncio is allowed to be imported - apps should not use it directly but use this TaskManager
logger = logging.getLogger(__name__)

class TaskManager:

    task_list = [] # might be good to periodically remove tasks that are done, to prevent this list from growing huge
    keep_running = None
    disabled = False

    @classmethod
    async def _asyncio_thread(cls, sleep_ms):
        if __debug__: logger.debug("asyncio_thread started")
        while cls.keep_running is True:
            # According to the docs, lv.timer_handler should be called periodically, but everything seems to work fine without it.
            # Perhaps lvgl_micropython is doing this somehow, although I can't find it... I guess the task_handler...?
            # sleep_ms can't handle too big values, so limit it to 30 ms, which equals 33 fps
            # sleep_ms = min(lv.timer_handler(), 30) # lv.timer_handler() will return LV_NO_TIMER_READY (UINT32_MAX) if there are no running timers
            await asyncio.sleep_ms(sleep_ms)
        logger.warning("asyncio_thread exited, now asyncio.create_task() won't work anymore")

    @classmethod
    def start(cls):
        if cls.disabled:
            logger.warning("Not starting TaskManager because it's been disabled.")
            return
        cls.keep_running = True
        while cls.keep_running is True:
            try:
                asyncio.run(TaskManager._asyncio_thread(10)) # 100ms is too high, causes lag. 10ms is fine. not sure if 1ms would be better...
            except KeyboardInterrupt:
                # A KeyboardInterrupt raised inside any task escapes MicroPython's
                # run_until_complete (it only catches CancelledError and Exception),
                # which would tear down every task. The task queue survives the
                # unwind, so re-entering asyncio.run resumes the remaining tasks.
                logger.warning("asyncio loop got KeyboardInterrupt, resuming remaining tasks")

    @classmethod
    def stop(cls):
        cls.keep_running = False

    @classmethod
    def enable(cls):
        cls.disabled = False

    @classmethod
    def disable(cls):
        cls.disabled = True

    @classmethod
    async def _run_task(cls, coroutine):
        task = asyncio.current_task()
        try:
            return await coroutine
        finally:
            if task in cls.task_list:
                cls.task_list.remove(task)

    @classmethod
    def create_task(cls, coroutine):
        task = asyncio.create_task(cls._run_task(coroutine))
        cls.task_list.append(task)
        return task

    @classmethod
    def create_supervised_task(cls, coroutine_factory, restart_delay_ms=200,
                               restart_on_return=False):
        """Keep a task alive across crashes.

        restart_on_return also restarts it when the coroutine finishes
        normally. Use it for tasks that are only ever meant to stop when
        the device does -- the serial console above all, where any quiet
        exit path leaves no way back in short of a power cycle.
        """
        async def _supervisor():
            while True:
                try:
                    await coroutine_factory()
                    if not restart_on_return:
                        return
                    logger.warning("supervised task returned, restarting it")
                except asyncio.CancelledError:
                    raise
                except KeyboardInterrupt as e:
                    logger.warning("supervised task got KeyboardInterrupt, restarting it: %s", e)
                except Exception as e:
                    logger.warning("supervised task died, restarting it: %s", e)
                await asyncio.sleep_ms(restart_delay_ms)
        return cls.create_task(_supervisor())

    @classmethod
    def list_tasks(cls):
        for index, task in enumerate(cls.task_list):
            if __debug__: logger.debug("task %s: ph_key:%s done:%s running %s", index, task.ph_key, task.done(), task.coro)

    @staticmethod
    def sleep_ms(ms):
        return asyncio.sleep_ms(ms)

    @staticmethod
    def sleep(s):
        return asyncio.sleep(s)

    @staticmethod
    def notify_event():
        return asyncio.Event()

    @staticmethod
    def wait_for(awaitable, timeout):
        return asyncio.wait_for(awaitable, timeout)

    @staticmethod
    def good_stack_size():
        stacksize = 24*1024 # less than 20KB crashes on desktop when doing heavy apps, like LightningPiggy's Wallet connections
        import sys
        if sys.platform == "esp32":
            stacksize = 16*1024
        return stacksize

    @staticmethod
    def start_new_thread():
        logger.warning("Starting new threads is really not recommended for regular apps, as we're limited to just a few in total, and they can't be stopped from the outside - they have to stop themselves.")
        if __debug__: logger.debug("We could add some framework with a 'halting' variable that the thread *should* check and then stop itself, but there's no guarantees.")
