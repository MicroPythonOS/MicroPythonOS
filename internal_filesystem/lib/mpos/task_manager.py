import asyncio # this is the only place where asyncio is allowed to be imported - apps should not use it directly but use this TaskManager
import _thread
import mpos.apps

class TaskManager:

    task_list = [] # might be good to periodically remove tasks that are done, to prevent this list from growing huge
    keep_running = None
    disabled = False

    @classmethod
    async def _asyncio_thread(cls, ms_to_sleep):
        print("asyncio_thread started")
        while cls.keep_running is True:
            #print(f"asyncio_thread tick because {cls.keep_running}")
            await asyncio.sleep_ms(ms_to_sleep)  # This delay determines how quickly new tasks can be started, so keep it below human reaction speed
        print("WARNING: asyncio_thread exited, now asyncio.create_task() won't work anymore")

    @classmethod
    def start(cls):
        if cls.disabled is True:
            print("Not starting TaskManager because it's been disabled.")
            return
        cls.keep_running = True
        # New thread works but LVGL isn't threadsafe so it's preferred to do this in the same thread:
        #_thread.stack_size(mpos.apps.good_stack_size())
        #_thread.start_new_thread(asyncio.run, (self._asyncio_thread(100), ))
        # Same thread works, although it blocks the real REPL, but aiorepl works:
        asyncio.run(TaskManager._asyncio_thread(10)) # 100ms is too high, causes lag. 10ms is fine. not sure if 1ms would be better...

    @classmethod
    def stop(cls):
        cls.keep_running = False

    @classmethod
    def disable(cls):
        cls.disabled = True

    @classmethod
    def create_task(cls, coroutine):
        cls.task_list.append(asyncio.create_task(coroutine))

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
