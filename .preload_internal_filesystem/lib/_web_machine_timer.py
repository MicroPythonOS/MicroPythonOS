# asyncio-backed machine.Timer replacement for the WebAssembly/Emscripten build.
import asyncio


class Timer:
    ONE_SHOT = 0
    PERIODIC = 1

    def __init__(self, id=-1, **kwargs):
        self.id = id
        self._task = None
        self._mode = Timer.PERIODIC
        self._period = 0
        self._callback = None
        if kwargs:
            self.init(**kwargs)

    def init(self, mode=PERIODIC, period=-1, callback=None, **kwargs):
        self.deinit()
        self._mode = mode
        self._period = period
        self._callback = callback
        if period is not None and period >= 0:
            # create_task works before the asyncio loop is running in
            # MicroPython (singleton task queue); the timer starts once
            # TaskManager.start() calls asyncio.run().
            self._task = asyncio.create_task(self._run())

    async def _run(self):
        try:
            while True:
                await asyncio.sleep_ms(self._period)
                cb = self._callback
                if cb is not None:
                    try:
                        cb(self)
                    except Exception as e:
                        import sys
                        sys.print_exception(e)
                if self._mode == Timer.ONE_SHOT:
                    break
        except asyncio.CancelledError:
            pass

    def deinit(self):
        if self._task is not None:
            try:
                self._task.cancel()
            except Exception:
                pass
            self._task = None
