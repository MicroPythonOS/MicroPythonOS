import unittest
from mpos.task_manager import TaskManager


class TestTaskManagerState(unittest.TestCase):

    def setUp(self):
        TaskManager.disabled = False
        TaskManager.keep_running = None

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
