# Web (Emscripten) replacement for the frozen task_handler driver.
# Same public API as lvgl_micropython's task_handler.TaskHandler, but driven
# by an asyncio task instead of machine.Timer (unavailable in the web build).

import lvgl as lv  # NOQA
import sys
import time
import asyncio


TASK_HANDLER_STARTED = 0x01
TASK_HANDLER_FINISHED = 0x02

_default_timer_id = 0


class _DefaultUserData(object):
    pass


def _default_exception_hook(e):
    sys.print_exception(e)  # NOQA
    TaskHandler._current_instance.deinit()  # NOQA


class TaskHandler(object):
    _current_instance = None

    def __init__(
        self,
        duration=33,
        timer_id=_default_timer_id,
        max_scheduled=2,
        exception_hook=_default_exception_hook
    ):
        if TaskHandler._current_instance is not None:
            self.__dict__.update(TaskHandler._current_instance.__dict__)
        else:
            if not lv.is_initialized():
                lv.init()

            TaskHandler._current_instance = self

            self._callbacks = []
            self.duration = duration
            self.exception_hook = exception_hook
            self.max_scheduled = max_scheduled

            self._start_time = time.ticks_ms()  # NOQA
            self._running = False
            self._disabled = 0
            self._deinited = False
            # asyncio.create_task works before the loop is running in
            # MicroPython (the global task queue is a singleton), so the task
            # starts as soon as TaskManager.start() calls asyncio.run().
            self._task = asyncio.create_task(self._run_loop())

    async def _run_loop(self):
        while not self._deinited:
            if self._disabled <= 0:
                self._task_handler()
            await asyncio.sleep_ms(self.duration)

    def add_event_cb(self, callback, event, user_data=_DefaultUserData):
        for i, (cb, evt, data) in enumerate(self._callbacks):
            if cb == callback:
                evt = event
                if user_data != _DefaultUserData:
                    data = user_data

                self._callbacks[i] = (cb, evt, data)
                break
        else:
            if user_data == _DefaultUserData:
                user_data = None

            self._callbacks.append((callback, event, user_data))

    def remove_event_cb(self, callback):
        for (cb, evt, data) in self._callbacks:
            if cb == callback:
                self._callbacks.remove((cb, evt, data))
                break

    def deinit(self):
        self._deinited = True
        if TaskHandler._current_instance is self:
            TaskHandler._current_instance = None

    def disable(self):
        self._disabled += 1

    def enable(self):
        self._disabled -= 1

    @classmethod
    def is_running(cls):
        return cls._current_instance is not None

    def _task_handler(self):
        try:
            if lv._nesting.value == 0:  # NOQA
                self._running = True

                run_update = True
                for cb, evt, data in self._callbacks:
                    if not evt & TASK_HANDLER_STARTED:
                        continue

                    try:
                        if cb(TASK_HANDLER_STARTED, data) is False:
                            run_update = False

                    except Exception as err:  # NOQA
                        if (
                            self.exception_hook and
                            self.exception_hook != _default_exception_hook
                        ):
                            self.exception_hook(err)
                        else:
                            sys.print_exception(err)  # NOQA
                        print(f"TaskHandler callback {cb} threw exception, disabling it")
                        self.remove_event_cb(cb)

                stop_time = time.ticks_ms()  # NOQA
                ticks_diff = time.ticks_diff(stop_time, self._start_time)  # NOQA
                self._start_time = stop_time
                lv.tick_inc(ticks_diff)

                if run_update:
                    try:
                        lv.task_handler()
                    except Exception as e:
                        print(f"lv.task_handler() threw exception: {e}")
                        sys.print_exception(e)

                    start_time = time.ticks_ms()  # NOQA

                    for cb, evt, data in self._callbacks:
                        if not evt & TASK_HANDLER_FINISHED:
                            continue

                        try:
                            cb(TASK_HANDLER_FINISHED, data)
                        except Exception as err:  # NOQA
                            if (
                                self.exception_hook and
                                self.exception_hook != _default_exception_hook
                            ):
                                self.exception_hook(err)
                            else:
                                sys.print_exception(err)  # NOQA

                    stop_time = time.ticks_ms()  # NOQA
                    ticks_diff = time.ticks_diff(stop_time, start_time)  # NOQA
                    lv.tick_inc(ticks_diff)

                self._running = False

        except Exception as e:
            self._running = False

            if self.exception_hook:
                self.exception_hook(e)
