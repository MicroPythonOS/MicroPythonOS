"""test_async_dns.py - Unit tests for mpos.net.async_dns.getaddrinfo_async.

Tests are deterministic and network-free: socket.getaddrinfo is monkeypatched
via async_dns_mod._getaddrinfo (a module-level variable) to return a canned
result (or raise) without hitting the network.

MicroPython built-in C modules do not allow attribute assignment at runtime, so
the async_dns module exposes a module-level _getaddrinfo reference that tests
can replace. tearDown restores the original to avoid test pollution.

Usage:
"""

import sys
import time
import unittest

sys.path.insert(0, '../internal_filesystem/lib')


FAKE_AI = [(2, 1, 0, '', ('93.184.216.34', 80))]


class TestGetaddrinfoAsync(unittest.TestCase):

    def setUp(self):
        import mpos.net.async_dns as async_dns_mod
        self._async_dns_mod = async_dns_mod
        # Save the module-level _getaddrinfo reference so tearDown can restore it.
        # This variable is a Python-level module attribute and CAN be replaced,
        # unlike the built-in socket.getaddrinfo C attribute.
        self._orig_getaddrinfo = async_dns_mod._getaddrinfo
        # Start each test with an empty DNS cache so a resolution actually runs
        # (a cached host would return instantly without spawning a worker).
        async_dns_mod.clear_dns_cache()
        # The off-loop worker thread is only used on ESP32; on linux getaddrinfo
        # runs synchronously, so thread-specific tests are skipped there.
        self._skip = sys.platform == "linux"

    def tearDown(self):
        # Restore original _getaddrinfo to avoid pollution between tests.
        self._async_dns_mod._getaddrinfo = self._orig_getaddrinfo
        self._async_dns_mod.clear_dns_cache()

    # ------------------------------------------------------------------

    async def _run_test_loop_alive(self):
        import asyncio
        from mpos.net.async_dns import getaddrinfo_async

        def _slow_getaddrinfo(*a, **kw):
            time.sleep(0.15)
            return FAKE_AI

        # Patch the module-level reference used by the _worker inner function.
        self._async_dns_mod._getaddrinfo = _slow_getaddrinfo

        counter = {"n": 0}

        async def _heartbeat():
            while True:
                counter["n"] += 1
                await asyncio.sleep_ms(5)

        hb_task = asyncio.create_task(_heartbeat())
        result = await getaddrinfo_async("example.com", 80)
        hb_task.cancel()
        return result, counter["n"]

    def test_event_loop_stays_alive_during_dns(self):
        """Event loop must keep ticking while the DNS worker blocks for 150 ms."""
        if self._skip:
            return
        import asyncio
        result, ticks = asyncio.run(self._run_test_loop_alive())
        # 150ms sleep / 5ms heartbeat = ~30 ticks expected; assert > 5 for safety
        self.assertTrue(ticks > 5, "event loop did not tick during DNS resolve")
        self.assertEqual(result, FAKE_AI)

    # ------------------------------------------------------------------

    async def _run_test_exception(self):
        import asyncio
        from mpos.net.async_dns import getaddrinfo_async

        def _fail_getaddrinfo(*a, **kw):
            raise OSError(-2, "Name or service not known")

        self._async_dns_mod._getaddrinfo = _fail_getaddrinfo

        try:
            await getaddrinfo_async("nonexistent.invalid", 80)
            return False
        except OSError:
            return True

    def test_worker_exception_is_reraised(self):
        """An OSError from the worker thread must propagate to the caller."""
        if self._skip:
            return
        import asyncio
        raised = asyncio.run(self._run_test_exception())
        self.assertTrue(raised, "OSError from worker thread was not re-raised")

    # ------------------------------------------------------------------

    async def _run_test_cache(self):
        import asyncio
        from mpos.net.async_dns import getaddrinfo_async
        calls = {"n": 0}

        def _counting_getaddrinfo(*a, **kw):
            calls["n"] += 1
            return FAKE_AI

        self._async_dns_mod._getaddrinfo = _counting_getaddrinfo
        r1 = await getaddrinfo_async("cached.example", 80)
        r2 = await getaddrinfo_async("cached.example", 80)
        return r1, r2, calls["n"]

    def test_repeat_lookup_hits_cache(self):
        """A repeated lookup for the same host serves from cache without re-resolving."""
        import asyncio
        r1, r2, ncalls = asyncio.run(self._run_test_cache())
        self.assertEqual(r1, FAKE_AI)
        self.assertEqual(r2, FAKE_AI)
        self.assertEqual(ncalls, 1, "second lookup should hit the cache, not re-resolve")

    async def _run_test_error_not_cached(self):
        import asyncio
        from mpos.net.async_dns import getaddrinfo_async
        calls = {"n": 0}

        def _failing(*a, **kw):
            calls["n"] += 1
            raise OSError(-2, "Name or service not known")

        self._async_dns_mod._getaddrinfo = _failing
        for _ in range(2):
            try:
                await getaddrinfo_async("bad.invalid", 80)
            except OSError:
                pass
        return calls["n"]

    def test_error_is_not_cached(self):
        """A failed resolution must not be cached; the next lookup re-resolves."""
        import asyncio
        ncalls = asyncio.run(self._run_test_error_not_cached())
        self.assertEqual(ncalls, 2, "failed lookups must re-resolve, not serve a cached error")
