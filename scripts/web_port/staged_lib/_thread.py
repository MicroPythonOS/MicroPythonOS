# Cooperative _thread shim for the single-threaded WebAssembly/Emscripten build.
#
# Real OS threads are unavailable in the browser without pthreads, so this
# emulates the subset of the CPython/MicroPython `_thread` API that
# MicroPythonOS relies on by scheduling work cooperatively on the asyncio event
# loop that TaskManager runs. Locks are no-ops because a single-threaded
# cooperative scheduler cannot have true contention.

_stack_size = 0


def stack_size(size=None):
    global _stack_size
    prev = _stack_size
    if size is not None:
        _stack_size = size
    return prev


def get_ident():
    return 1


def start_new_thread(function, args=(), kwargs=None):
    if kwargs is None:
        kwargs = {}

    try:
        import asyncio

        async def _runner():
            try:
                function(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                print("[_thread shim] thread function failed:", exc)

        asyncio.get_event_loop().create_task(_runner())
    except Exception:
        # No running event loop yet: run synchronously so behaviour stays defined.
        function(*args, **kwargs)

    return get_ident()


class LockType:
    def __init__(self):
        self._locked = False

    def acquire(self, waitflag=1, timeout=-1):
        self._locked = True
        return True

    def release(self):
        self._locked = False

    def locked(self):
        return self._locked

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def allocate_lock():
    return LockType()
