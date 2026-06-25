try:
    import _thread  # noqa: F401
except ImportError:
    _thread = None


def _is_valid_lock(lock):
    """Return True if an object looks like a usable lock."""
    return lock is not None and callable(getattr(lock, "acquire", None)) and callable(getattr(lock, "release", None))


class Queue:
    def __init__(self, maxsize=0):
        self._queue = []
        self.maxsize = maxsize  # 0 means unlimited
        raw_lock = _thread.allocate_lock() if _thread else None
        self._lock = raw_lock if _is_valid_lock(raw_lock) else None

    def _ensure_queue(self):
        # Recover from heap corruption that has replaced the internal list.
        if not isinstance(self._queue, list):
            self._queue = []

    def put(self, item):
        if self._lock:
            self._lock.acquire()
            try:
                self._ensure_queue()
                if self.maxsize > 0 and len(self._queue) >= self.maxsize:
                    raise RuntimeError("Queue is full")
                self._queue.append(item)
            finally:
                self._lock.release()
        else:
            self._ensure_queue()
            if self.maxsize > 0 and len(self._queue) >= self.maxsize:
                raise RuntimeError("Queue is full")
            self._queue.append(item)

    def get(self):
        if self._lock:
            self._lock.acquire()
            try:
                self._ensure_queue()
                if not self._queue:
                    raise RuntimeError("Queue is empty")
                return self._queue.pop(0)
            finally:
                self._lock.release()
        else:
            self._ensure_queue()
            if not self._queue:
                raise RuntimeError("Queue is empty")
            return self._queue.pop(0)

    def qsize(self):
        if self._lock:
            self._lock.acquire()
            try:
                self._ensure_queue()
                return len(self._queue)
            finally:
                self._lock.release()
        self._ensure_queue()
        return len(self._queue)

    def empty(self):
        return self.qsize() == 0

    def full(self):
        return self.maxsize > 0 and self.qsize() >= self.maxsize
