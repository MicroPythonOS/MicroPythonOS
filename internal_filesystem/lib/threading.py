# Lightweight replacement for CPython's Thread module

import _thread

from mpos.task_manager import TaskManager
import mpos.apps

class Thread:
    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = {} if kwargs is None else kwargs
        self.name = name
        self.daemon = daemon  # Store daemon attribute (True, False, or None)

    def start(self):
        # In MicroPython, _thread.start_new_thread doesn't support daemon threads directly
        # We store the daemon attribute for compatibility, but it may not affect termination
        # 18KB or more causes "can't create thread" when starting relay.queue_worker thread
        # 16KB still too much
        # _thread.stack_size(32*1024)
        #_thread.stack_size(10*1024) # might not be enough
        #stacksize = 12*1024
        # small stack sizes 8KB gives segfault directly
        # 22KB or less is too tight on desktop, 23KB and more is fine
        #stacksize = 24*1024
        stacksize = TaskManager.good_stack_size()
        #stacksize = 20*1024
        print(f"starting thread with stacksize {stacksize}")
        _thread.stack_size(stacksize)
        _thread.start_new_thread(self.run, ())

    def run(self):
        try:
            self.target(*self.args, **self.kwargs)
        except Exception as e:
            # Basic error handling to prevent silent failures
            print(f"Thread {self.name or ''} failed: {e}")

    @property
    def daemon(self):
        return self._daemon

    @daemon.setter
    def daemon(self, value):
        self._daemon = value if value is not None else False


class Lock:
    def __init__(self):
        self._lock = _thread.allocate_lock()

    def __enter__(self):
        if self._lock:
            self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._lock:
            self._lock.release()

    def acquire(self):
        if self._lock:
            return self._lock.acquire()
        return True

    def release(self):
        if self._lock:
            self._lock.release()
