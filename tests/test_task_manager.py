import asyncio
import unittest
from mpos.task_manager import TaskManager


class TestTaskManagerState(unittest.TestCase):

    def setUp(self):
        self.original_task_list = TaskManager.task_list
        TaskManager.disabled = False
        TaskManager.keep_running = None
        TaskManager.task_list = []

    def tearDown(self):
        TaskManager.task_list = self.original_task_list

    def test_enable_sets_disabled_false(self):
        TaskManager.disabled = True
        TaskManager.enable()
        self.assertFalse(TaskManager.disabled)

    def test_disable_sets_disabled_true(self):
        TaskManager.disable()
        self.assertTrue(TaskManager.disabled)

    def test_enable_when_already_false(self):
        TaskManager.disabled = False
        TaskManager.enable()
        self.assertFalse(TaskManager.disabled)

    def test_disable_when_already_true(self):
        TaskManager.disabled = True
        TaskManager.disable()
        self.assertTrue(TaskManager.disabled)

    def test_stop_sets_keep_running_false(self):
        TaskManager.keep_running = True
        TaskManager.stop()
        self.assertFalse(TaskManager.keep_running)

    def test_stop_when_not_running(self):
        TaskManager.keep_running = None
        TaskManager.stop()
        self.assertFalse(TaskManager.keep_running)

    def test_good_stack_size_returns_positive(self):
        size = TaskManager.good_stack_size()
        self.assertIsInstance(size, int)
        self.assertTrue(size > 0)

    def test_good_stack_size_is_reasonable(self):
        size = TaskManager.good_stack_size()
        self.assertTrue(size >= 16 * 1024)
        self.assertTrue(size <= 64 * 1024)

    def test_start_new_thread_logs_warning(self):
        TaskManager.start_new_thread()

    def test_completed_task_is_removed_and_returns_result(self):
        async def return_result():
            return "result"

        async def run_task():
            task = TaskManager.create_task(return_result())
            self.assertIn(task, TaskManager.task_list)
            result = await task
            return task, result

        task, result = asyncio.run(run_task())

        self.assertEqual(result, "result")
        self.assertTrue(task.done())
        self.assertTrue(task not in TaskManager.task_list)

    def test_failed_task_is_removed_and_preserves_exception(self):
        async def raise_error():
            raise ValueError("failure")

        async def run_task():
            task = TaskManager.create_task(raise_error())
            try:
                await task
            except ValueError as error:
                return task, str(error)

        task, message = asyncio.run(run_task())

        self.assertEqual(message, "failure")
        self.assertTrue(task.done())
        self.assertTrue(task not in TaskManager.task_list)

    def test_cancelled_task_is_removed_and_preserves_cancellation(self):
        async def wait():
            await asyncio.sleep(60)

        async def run_task():
            task = TaskManager.create_task(wait())
            await asyncio.sleep_ms(0)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return task, True
            return task, False

        task, cancelled = asyncio.run(run_task())

        self.assertTrue(cancelled)
        self.assertTrue(task.done())
        self.assertTrue(task not in TaskManager.task_list)

    def test_cleanup_preserves_running_tasks(self):
        async def wait_for_event(event):
            await event.wait()

        async def finish():
            return None

        async def run_tasks():
            event = asyncio.Event()
            running_task = TaskManager.create_task(wait_for_event(event))
            completed_task = TaskManager.create_task(finish())
            await completed_task
            completed_removed = completed_task not in TaskManager.task_list
            running_preserved = running_task in TaskManager.task_list
            event.set()
            await running_task
            return completed_removed, running_preserved

        completed_removed, running_preserved = asyncio.run(run_tasks())

        self.assertTrue(completed_removed)
        self.assertTrue(running_preserved)
        self.assertEqual(TaskManager.task_list, [])

    def test_many_completed_tasks_do_not_accumulate(self):
        async def allocate_buffer():
            buffer = bytearray(10 * 1024)
            await asyncio.sleep_ms(0)
            return len(buffer)

        async def run_tasks():
            tasks = []
            for _ in range(100):
                tasks.append(TaskManager.create_task(allocate_buffer()))
            total = 0
            for task in tasks:
                total += await task
            return total

        total = asyncio.run(run_tasks())

        self.assertEqual(total, 100 * 10 * 1024)
        self.assertEqual(TaskManager.task_list, [])
