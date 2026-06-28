"""test_async_dns.py - Unit tests for mpos.net.async_dns.getaddrinfo_async.

Tests are deterministic and network-free: socket.getaddrinfo is monkeypatched
via async_dns_mod._getaddrinfo (a module-level variable) to return a canned
result (or raise) without hitting the network.

MicroPython built-in C modules do not allow attribute assignment at runtime, so
the async_dns module exposes a module-level _getaddrinfo reference that tests
can replace. tearDown restores the original to avoid test pollution.

Usage:
    Desktop: ./tests/unittest.sh tests/test_async_dns.py
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

    def tearDown(self):
        # Restore original _getaddrinfo to avoid pollution between tests.
        self._async_dns_mod._getaddrinfo = self._orig_getaddrinfo

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
        import asyncio
        raised = asyncio.run(self._run_test_exception())
        self.assertTrue(raised, "OSError from worker thread was not re-raised")
