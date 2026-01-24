import asyncio # this is the only place where asyncio is allowed to be imported - apps should not use it directly but use this TaskManager
import _thread

class TaskManager:

    task_list = [] # might be good to periodically remove tasks that are done, to prevent this list from growing huge
    keep_running = None
    disabled = False

    @classmethod
    async def _asyncio_thread(cls, sleep_ms):
        print("asyncio_thread started")
        while cls.keep_running is True:
            #print(f"asyncio_thread tick because cls.keep_running:{cls.keep_running}")
            # According to the docs, lv.timer_handler should be called periodically, but everything seems to work fine without it.
            # Perhaps lvgl_micropython is doing this somehow, although I can't find it... I guess the task_handler...?
            # sleep_ms can't handle too big values, so limit it to 30 ms, which equals 33 fps
            # sleep_ms = min(lv.timer_handler(), 30) # lv.timer_handler() will return LV_NO_TIMER_READY (UINT32_MAX) if there are no running timers
            await asyncio.sleep_ms(sleep_ms)
        print("WARNING: asyncio_thread exited, now asyncio.create_task() won't work anymore")

    @classmethod
    def start(cls):
        if cls.disabled is True:
            print("Not starting TaskManager because it's been disabled.")
            return
        cls.keep_running = True
        asyncio.run(TaskManager._asyncio_thread(10)) # 100ms is too high, causes lag. 10ms is fine. not sure if 1ms would be better...

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
    def create_task(cls, coroutine):
        task = asyncio.create_task(coroutine)
        cls.task_list.append(task)
        return task

    @classmethod
    def list_tasks(cls):
        for index, task in enumerate(cls.task_list):
            print(f"task {index}: ph_key:{task.ph_key} done:{task.done()} running {task.coro}")

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

