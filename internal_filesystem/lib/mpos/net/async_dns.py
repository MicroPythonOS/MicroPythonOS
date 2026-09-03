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

import logging
import socket
import _thread
import sys
import time
from mpos.task_manager import TaskManager

logger = logging.getLogger(__name__)

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

# Single-flight table: (host, port, proto, socktype) -> shared result cell.
# Concurrent lookups for the same key share one worker thread instead of each
# spawning its own; the ESP32 thread budget is far too small for per-connection
# resolvers (e.g. three WebSocket handshakes to one relay must not need three
# threads). The dict entry is removed once the shared worker finishes.
_inflight_lookups = {}


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

    # .local TLD triggers mDNS (libnss_mdns4_minimal on Linux, Bonjour on
    # macOS) which segfaults when called from a _thread worker. Resolve
    # synchronously on the main thread on desktop where getaddrinfo is fast
    # and mDNS is thread-safe.
    if host.lower().endswith(".local") and sys.platform in ("linux", "darwin"):
        result = _getaddrinfo(host, port, proto, socktype)
        _dns_cache[key] = (result, time.ticks_ms())
        return result

    global _inflight

    if __debug__: logger.debug("resolving %s:%s", host, port)

    # Wait for a free worker slot without blocking the event loop. If cancelled
    # here, we have not reserved a slot yet, so nothing leaks. The cap applies
    # to worker threads; waiters on an in-flight single-flight cell never take
    # a slot, so the same key is resolved by at most one thread.
    while True:
        with _inflight_lock:
            if _inflight < _MAX_INFLIGHT:
                _inflight += 1
                break
        await TaskManager.sleep_ms(20)

    # Re-check the cache: a concurrent lookup for this key may have completed
    # while we waited for the slot, so we can release it without spawning.
    cached = _dns_cache_get(key)
    if cached is not None:
        with _inflight_lock:
            _inflight -= 1
        return cached

    # Single-flight: if a lookup for this key is already in progress, share its
    # result cell instead of spawning another thread (three WebSocket handshakes
    # to one relay must not need three resolvers on a thread-starved ESP32).
    # The first caller owns the cell and spawns the worker; the rest poll the
    # same cell and release the slot they reserved.
    with _inflight_lock:
        _result = _inflight_lookups.get(key)
        if _result is None:
            _result = {"done": False, "value": None, "exc": None}
            _inflight_lookups[key] = _result
            creator = True
        else:
            creator = False

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
                _inflight_lookups.pop(key, None)

    if creator:
        # _thread.stack_size() is process-global; save and restore it so we do
        # not change the default stack size for threads spawned later by other
        # code.
        _prev_stack = _thread.stack_size(TaskManager.good_stack_size())
        try:
            try:
                _thread.start_new_thread(_worker, ())
            except Exception:
                # Thread budget temporarily exhausted (e.g. boot threads still
                # winding down, or a burst of lookups). Resolve synchronously on
                # this thread instead of failing the lookup: the result is
                # published to the shared cell (waiters still see it) and cached
                # so later callers skip the worker entirely. This blocks the
                # event loop for the duration of ONE lookup (typically <1s on a
                # warm DNS server) but beats failing the connection outright.
                try:
                    _result["value"] = _getaddrinfo(host, port, proto, socktype)
                except Exception as e:
                    _result["exc"] = e
                _result["done"] = True
                with _inflight_lock:
                    _inflight -= 1
                    _inflight_lookups.pop(key, None)
        finally:
            _thread.stack_size(_prev_stack)
    else:
        with _inflight_lock:
            _inflight -= 1

    # If cancelled below, the worker keeps running and releases its slot in its
    # finally when getaddrinfo finally returns -- the slot is freed, not leaked.
    while not _result["done"]:
        await TaskManager.sleep_ms(20)

    if _result["exc"] is not None:
        if __debug__: logger.debug("resolve %s:%s failed: %s", host, port, _result["exc"])
        raise _result["exc"]

    # Cache only successful results so a later lookup can skip the worker thread.
    _dns_cache[key] = (_result["value"], time.ticks_ms())
    if __debug__: logger.debug("resolve %s:%s done", host, port)
    return _result["value"]
