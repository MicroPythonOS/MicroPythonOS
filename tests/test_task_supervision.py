"""test_task_supervision.py - Unit tests for TaskManager task supervision and
aiorepl console resilience.

Reproduces the on-device bug where mpremote/raw-REPL connection attempts kill
the aiorepl serial console permanently:

1. A KeyboardInterrupt raised inside any asyncio task escapes MicroPython's
   run_until_complete (which only catches CancelledError and Exception), so a
   single stray Ctrl-C tears down the whole asyncio loop while the LVGL UI
   (driven by a hardware timer) keeps running. TaskManager.start() must catch
   this and resume the loop.

2. The aiorepl task itself can die from a KeyboardInterrupt or exception and
   is never restarted. TaskManager.create_supervised_task() restarts it.

3. aiorepl.task() returns permanently on stdin EOF (host disconnect), leaving
   kbd_intr(3) armed so later Ctrl-Cs nuke random tasks. The EOF path must
   retry instead of returning.

Tests are deterministic and hardware-free: they run their own asyncio loops
and monkeypatch asyncio.StreamReader for the EOF test.

The test harness (mpos_controller process backend) executes this file inside
the booted MPOS's own running asyncio loop, so tests must NOT call
asyncio.new_event_loop() (it would kill the harness's console and TaskManager
tasks). Nested asyncio.run() shares the global task queue and is safe.
TaskManager.keep_running is saved/restored so the harness's outer
TaskManager.start() loop resumes its main task after tests that call stop().
"""

import sys
import unittest

sys.path.insert(0, "../internal_filesystem/lib")

import asyncio


class TestCreateSupervisedTask(unittest.TestCase):

    def setUp(self):
        from mpos.task_manager import TaskManager
        self.TaskManager = TaskManager
        self._orig_keep_running = TaskManager.keep_running
        self._orig_disabled = TaskManager.disabled
        TaskManager.enable()

    def tearDown(self):
        self.TaskManager.keep_running = self._orig_keep_running
        self.TaskManager.disabled = self._orig_disabled

    def _run(self, coro):
        return asyncio.run(coro)

    def test_restarts_after_keyboard_interrupt(self):
        calls = {"n": 0}

        def factory():
            async def repl():
                calls["n"] += 1
                if calls["n"] == 1:
                    raise KeyboardInterrupt
                while True:
                    await asyncio.sleep_ms(10)
            return repl()

        async def main():
            task = self.TaskManager.create_supervised_task(factory, restart_delay_ms=10)
            await asyncio.sleep_ms(200)
            self.assertEqual(calls["n"], 2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._run(main())

    def test_restarts_after_exception(self):
        calls = {"n": 0}

        def factory():
            async def repl():
                calls["n"] += 1
                if calls["n"] == 1:
                    raise ValueError("boom")
                while True:
                    await asyncio.sleep_ms(10)
            return repl()

        async def main():
            task = self.TaskManager.create_supervised_task(factory, restart_delay_ms=10)
            await asyncio.sleep_ms(200)
            self.assertEqual(calls["n"], 2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._run(main())

    def test_clean_return_is_not_restarted(self):
        calls = {"n": 0}

        def factory():
            async def repl():
                calls["n"] += 1
            return repl()

        async def main():
            task = self.TaskManager.create_supervised_task(factory, restart_delay_ms=10)
            await asyncio.sleep_ms(100)
            self.assertEqual(calls["n"], 1)
            self.assertTrue(task.done())

        self._run(main())

    def test_console_is_restarted_after_a_clean_return(self):
        """restart_on_return brings the console back however it exited."""
        calls = {"n": 0}

        def factory():
            async def repl():
                calls["n"] += 1
            return repl()

        async def main():
            task = self.TaskManager.create_supervised_task(
                factory, restart_delay_ms=10, restart_on_return=True)
            await asyncio.sleep_ms(150)
            # MPOS's minimal unittest has no assertGreater.
            self.assertTrue(calls["n"] > 1, "console was not restarted")
            self.assertFalse(task.done())
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._run(main())

    def test_cancel_stops_supervision(self):
        calls = {"n": 0}

        def factory():
            async def repl():
                calls["n"] += 1
                while True:
                    await asyncio.sleep_ms(10)
            return repl()

        async def main():
            task = self.TaskManager.create_supervised_task(factory, restart_delay_ms=10)
            await asyncio.sleep_ms(50)
            self.assertEqual(calls["n"], 1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await asyncio.sleep_ms(100)
            self.assertEqual(calls["n"], 1)

        self._run(main())


class TestStartSurvivesKeyboardInterrupt(unittest.TestCase):

    def setUp(self):
        from mpos.task_manager import TaskManager
        self.TaskManager = TaskManager
        self._orig_keep_running = TaskManager.keep_running
        # The test harness boots MPOS with TaskManager.disable() applied, which
        # would turn start() into a no-op; enable it for the duration of the test.
        self._orig_disabled = TaskManager.disabled
        TaskManager.enable()

    def tearDown(self):
        self.TaskManager.keep_running = self._orig_keep_running
        self.TaskManager.disabled = self._orig_disabled

    def test_loop_resumes_after_keyboard_interrupt_in_task(self):
        events = []

        async def bomb():
            await asyncio.sleep_ms(10)
            events.append("bomb")
            raise KeyboardInterrupt

        async def later():
            await asyncio.sleep_ms(100)
            events.append("later")
            self.TaskManager.stop()

        self.TaskManager.create_task(bomb())
        self.TaskManager.create_task(later())
        self.TaskManager.start()

        self.assertTrue("bomb" in events)
        self.assertTrue("later" in events)


class TestAioreplEofResilience(unittest.TestCase):

    def setUp(self):
        self._orig_stream_reader = asyncio.StreamReader

    def tearDown(self):
        asyncio.StreamReader = self._orig_stream_reader

    def test_ctrl_d_does_not_kill_the_asyncio_loop(self):
        """Ctrl-D outside the raw-REPL protocol must not tear down asyncio.

        Upstream aiorepl answers Ctrl-D with asyncio.new_event_loop(), which
        on MPOS discards every running task -- the app, TaskManager's main
        task and the console itself -- and then returns. That is the whole
        "console dead until replug" bug: mpremote sessions that desync leave
        stray Ctrl-Ds in the stream outside raw mode.
        """
        import aiorepl

        killed = {"n": 0}
        real_new_event_loop = asyncio.new_event_loop

        def counting_new_event_loop(*args, **kwargs):
            killed["n"] += 1
            return real_new_event_loop(*args, **kwargs)

        class FakeCtrlDStdin:
            """Sends one Ctrl-D, then blocks like an idle console."""

            def __init__(self, *args, **kwargs):
                self.sent = False

            async def read(self, n):
                if not self.sent:
                    self.sent = True
                    return chr(0x04)
                await asyncio.sleep_ms(50)
                return ""

        asyncio.StreamReader = FakeCtrlDStdin
        asyncio.new_event_loop = counting_new_event_loop
        try:
            async def main():
                task = asyncio.create_task(aiorepl.task(g={}))
                await asyncio.sleep_ms(300)
                self.assertEqual(killed["n"], 0, "Ctrl-D tore down the event loop")
                self.assertFalse(task.done(), "console exited on Ctrl-D")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            asyncio.run(main())
        finally:
            asyncio.new_event_loop = real_new_event_loop

    def test_task_survives_stdin_eof(self):
        import aiorepl

        class FakeEofStdin:
            def __init__(self, *args, **kwargs):
                pass

            async def read(self, n):
                return ""

        asyncio.StreamReader = FakeEofStdin

        async def main():
            task = asyncio.create_task(aiorepl.task(g={}))
            await asyncio.sleep_ms(1200)
            self.assertFalse(task.done())
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(main())


if __name__ == "__main__":
    unittest.main()
