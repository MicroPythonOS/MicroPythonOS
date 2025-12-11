import asyncio # this is the only place where asyncio is allowed to be imported - apps should not use it directly but use this TaskManager
import _thread
import mpos.apps

class TaskManager:

    task_list = [] # might be good to periodically remove tasks that are done, to prevent this list from growing huge

    def __init__(self):
        print("TaskManager starting asyncio_thread")
        _thread.stack_size(mpos.apps.good_stack_size()) # tiny stack size of 1024 is fine for tasks that do nothing but for real-world usage, it needs more
        _thread.start_new_thread(asyncio.run, (self._asyncio_thread(), ))

    async def _asyncio_thread(self):
        print("asyncio_thread started")
        while True:
            #print("asyncio_thread tick")
            await asyncio.sleep_ms(100)  # This delay determines how quickly new tasks can be started, so keep it below human reaction speed
        print("WARNING: asyncio_thread exited, this shouldn't happen because now asyncio.create_task() won't work anymore!")

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
