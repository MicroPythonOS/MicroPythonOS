"""async_dns.py -- Off-loop DNS resolution helper for MicroPythonOS.

Offloads socket.getaddrinfo to a _thread worker so the asyncio event loop
stays alive during blocking DNS lookups on ESP32-S3.

On ESP32-S3, socket.getaddrinfo() is a blocking call that wraps lwIP's DNS
resolver (lwip_getaddrinfo in ports/esp32/modsocket.c). Although lwIP DNS is
internally async, the MicroPython wrapper blocks the calling thread until the
result arrives. When this call runs on the asyncio event-loop thread (which is
also the LVGL task_handler thread), the entire UI freezes for the duration of
the DNS lookup -- worst case several seconds for non-existent hosts.

The GIL is released during the blocking C call (modsocket.c:239-253), so a
_thread worker keeps the main loop alive while DNS resolves. This module
provides getaddrinfo_async(), an awaitable coroutine that spawns the blocking
getaddrinfo in a worker thread and polls for completion with 20 ms sleeps,
yielding to the event loop on every iteration.

Usage:
    from mpos.net.async_dns import getaddrinfo_async
    ai = await getaddrinfo_async("example.com", 80)
    ip = ai[0][-1][0]
"""

import socket
import _thread
import sys
import time
from mpos.task_manager import TaskManager

# Module-level reference to the getaddrinfo implementation.  Tests replace this
# variable to monkeypatch without needing to modify the built-in socket module
# (MicroPython C modules do not allow attribute assignment at runtime).
_getaddrinfo = socket.getaddrinfo

# Bound the number of concurrent off-loop DNS worker threads. getaddrinfo() is a
# blocking C call that cannot be cancelled mid-flight, so if getaddrinfo_async is
# cancelled (e.g. an aiohttp request timeout fires during resolution) its worker
# keeps running until the lookup completes. Capping concurrency applies
# backpressure -- a burst of cancellations/retries cannot exhaust MicroPython's
# RAM-bounded thread budget; new lookups await a free slot.
_MAX_INFLIGHT = 2
_inflight_lock = _thread.allocate_lock()
_inflight = 0

# Cache successful resolutions per (host, port, proto, socktype). Apps that
# fetch many files from one host, or that repeatedly retry a relay connection,
# would otherwise spawn a fresh resolver thread per lookup; on a thread-starved
# ESP32-S3 a burst of those can exhaust the thread pool. A short TTL keeps
# results fresh enough to follow DNS changes. Only successful lookups are cached
# (errors must re-resolve).
_DNS_CACHE_TTL_MS = 300_000  # 5 minutes
_dns_cache = {}  # (host, port, proto, socktype) -> (result, resolved_ticks_ms)


def clear_dns_cache():
    """Drop all cached DNS results (call on network changes; used by tests)."""
    _dns_cache.clear()


def _dns_cache_get(key):
    entry = _dns_cache.get(key)
    if entry is None:
        return None
    result, ts = entry
    if time.ticks_diff(time.ticks_ms(), ts) >= _DNS_CACHE_TTL_MS:
        _dns_cache.pop(key, None)
        return None
    return result


async def getaddrinfo_async(host, port, proto=0, socktype=None):
    """Resolve host:port DNS off the asyncio event-loop thread.

    Spawns a _thread worker that calls socket.getaddrinfo() synchronously.
    The event loop keeps ticking via 20 ms TaskManager.sleep_ms() polls while
    the worker blocks. The "done" flag is set LAST so the poll loop never
    reads a half-written result cell.

    Args:
        host: hostname or IP string to resolve.
        port: port number (int).
        proto: protocol hint for getaddrinfo (default 0).
        socktype: socket type hint (default socket.SOCK_STREAM).

    Returns:
        List of addrinfo tuples as returned by socket.getaddrinfo().

    Raises:
        Whatever exception socket.getaddrinfo() raises (e.g. OSError on
        NXDOMAIN or network unreachable).
    """
    if socktype is None:
        socktype = socket.SOCK_STREAM

    # Serve a cached resolution immediately when still fresh -- no worker thread
    # (and no event-loop yield) needed. Applies on every platform.
    key = (host, port, proto, socktype)
    cached = _dns_cache_get(key)
    if cached is not None:
        return cached

    # On the unix port _thread is marked 'unsafe'; spawning worker threads for
    # DNS on desktop corrupts the heap and crashes the process. Call getaddrinfo
    # directly there (it is reasonably fast and does not block an LVGL task
    # handler on desktop). On ESP32 keep the off-loop worker thread.
    if sys.platform == "linux":
        result = _getaddrinfo(host, port, proto, socktype)
        _dns_cache[key] = (result, time.ticks_ms())
        return result

    global _inflight

    # Wait for a free worker slot without blocking the event loop. If cancelled
    # here, we have not reserved a slot yet, so nothing leaks.
    while True:
        with _inflight_lock:
            if _inflight < _MAX_INFLIGHT:
                _inflight += 1
                break
        await TaskManager.sleep_ms(20)

    _result = {"done": False, "value": None, "exc": None}

    def _worker():
        global _inflight
        try:
            try:
                _result["value"] = _getaddrinfo(host, port, proto, socktype)
            except Exception as e:
                _result["exc"] = e
            _result["done"] = True   # publish result before releasing the slot
        finally:
            with _inflight_lock:
                _inflight -= 1

    # _thread.stack_size() is process-global; save and restore it so we do not
    # change the default stack size for threads spawned later by other code.
    _prev_stack = _thread.stack_size(TaskManager.good_stack_size())
    try:
        _thread.start_new_thread(_worker, ())
    except Exception:
        # Spawn failed: release the slot we reserved and propagate.
        with _inflight_lock:
            _inflight -= 1
        raise
    finally:
        _thread.stack_size(_prev_stack)

    # If cancelled below, the worker keeps running and releases its slot in its
    # finally when getaddrinfo finally returns -- the slot is freed, not leaked.
    while not _result["done"]:
        await TaskManager.sleep_ms(20)

    if _result["exc"] is not None:
        raise _result["exc"]

    # Cache only successful results so a later lookup can skip the worker thread.
    _dns_cache[key] = (_result["value"], time.ticks_ms())
    return _result["value"]
