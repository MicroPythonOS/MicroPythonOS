import asyncio # this is the only place where asyncio is allowed to be imported - apps should not use it directly but use this TaskManager
import _thread
import mpos.apps

class TaskManager:

    task_list = [] # might be good to periodically remove tasks that are done, to prevent this list from growing huge
    keep_running = True

    @classmethod
    async def _asyncio_thread(cls, ms_to_sleep):
        print("asyncio_thread started")
        while TaskManager.should_keep_running() is True:
        #while self.keep_running is True:
            #print(f"asyncio_thread tick because {self.keep_running}")
            print(f"asyncio_thread tick because {TaskManager.should_keep_running()}")
            await asyncio.sleep_ms(ms_to_sleep)  # This delay determines how quickly new tasks can be started, so keep it below human reaction speed
        print("WARNING: asyncio_thread exited, now asyncio.create_task() won't work anymore")

    @classmethod
    def start(cls):
        #asyncio.run_until_complete(TaskManager._asyncio_thread(100)) # this actually works, but it blocks the real REPL (aiorepl works, but that's limited)
        asyncio.run(TaskManager._asyncio_thread(1000)) # this actually works, but it blocks the real REPL (aiorepl works, but that's limited)

    @classmethod
    def stop(cls):
        cls.keep_running = False

    @classmethod
    def should_keep_running(cls):
        return cls.keep_running

    @classmethod
    def set_keep_running(cls, value):
        cls.keep_running = value

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
