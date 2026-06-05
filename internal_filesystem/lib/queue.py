try:
    import _thread  # noqa: F401
except ImportError:
    _thread = None

class Queue:
    def __init__(self, maxsize=0):
        self._queue = []
        self.maxsize = maxsize  # 0 means unlimited
        self._lock = _thread.allocate_lock() if _thread else None

    def put(self, item):
        if self._lock:
            with self._lock:
                if self.maxsize > 0 and len(self._queue) >= self.maxsize:
                    raise RuntimeError("Queue is full")
                self._queue.append(item)
        else:
            if self.maxsize > 0 and len(self._queue) >= self.maxsize:
                raise RuntimeError("Queue is full")
            self._queue.append(item)

    def get(self):
        if self._lock:
            with self._lock:
                if not self._queue:
                    raise RuntimeError("Queue is empty")
                return self._queue.pop(0)
        else:
            if not self._queue:
                raise RuntimeError("Queue is empty")
            return self._queue.pop(0)

    def qsize(self):
        if self._lock:
            with self._lock:
                return len(self._queue)
        return len(self._queue)

    def empty(self):
        return self.qsize() == 0

    def full(self):
        return self.maxsize > 0 and self.qsize() >= self.maxsize
