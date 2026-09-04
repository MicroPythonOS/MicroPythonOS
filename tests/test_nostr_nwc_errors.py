"""
Unit tests for NostrManager._process_nwc_event error handling.

A NIP-47 error reply (e.g. UNAUTHORIZED when the wallet service has retired
the connection) must be surfaced through the error callback instead of being
silently discarded, must reset the silence watchdog (an error reply is
wallet-service activity), and must not be re-forwarded every poll while the
error stays the same. A successful result afterwards re-arms forwarding.

The manager instance is built via a no-op-__init__ subclass with only the attributes
_process_nwc_event touches, so no relays, LVGL, or network are involved.

Usage:
    python3 scripts/test_runner.py tests/test_nostr_nwc_errors.py
"""

import json
import sys
import unittest

sys.path.append("apps/com_micropythonos_nostr")
from nostr_service import NostrManager


class _FakeKey:
    def __init__(self, plaintext):
        self.plaintext = plaintext

    def decrypt_message(self, content, pubkey):
        return self.plaintext


class _FakeEvent:
    kind = 23195
    content = "irrelevant-ciphertext"
    public_key = "wallet-pubkey"


class _BareManager(NostrManager):
    # Skip NostrManager.__init__ (relays, tasks); the tests set exactly the
    # attributes _process_nwc_event touches. MicroPython has no usable
    # __new__, hence the subclass with a no-op constructor.
    def __init__(self):
        pass


def _bare_manager(plaintext):
    mgr = _BareManager()
    mgr._nwc_private_key = _FakeKey(plaintext)
    mgr._last_nwc_error = None
    mgr._polls_since_last_event = 3
    mgr._error_cb = None
    mgr._nwc_balance_cb = None
    mgr._nwc_payments_cb = None
    mgr._nwc_notification_cb = None
    return mgr


_ERROR_REPLY = json.dumps({
    "result_type": "get_balance",
    "error": {"code": "UNAUTHORIZED",
              "message": "This NWC connection has been retired; create a new one"},
})

_BALANCE_REPLY = json.dumps({
    "result_type": "get_balance",
    "result": {"balance": 21000},
})


class TestNwcErrorSurfacing(unittest.TestCase):
    def test_error_reaches_error_cb(self):
        mgr = _bare_manager(_ERROR_REPLY)
        seen = []
        mgr._error_cb = seen.append
        mgr._process_nwc_event(_FakeEvent())
        self.assertEqual(len(seen), 1)
        self.assertTrue("UNAUTHORIZED" in seen[0])
        self.assertTrue("retired" in seen[0])

    def test_error_resets_watchdog(self):
        mgr = _bare_manager(_ERROR_REPLY)
        mgr._process_nwc_event(_FakeEvent())
        self.assertEqual(mgr._polls_since_last_event, 0)

    def test_repeat_error_forwarded_once(self):
        mgr = _bare_manager(_ERROR_REPLY)
        seen = []
        mgr._error_cb = seen.append
        mgr._process_nwc_event(_FakeEvent())
        mgr._process_nwc_event(_FakeEvent())
        mgr._process_nwc_event(_FakeEvent())
        self.assertEqual(len(seen), 1)

    def test_success_rearms_error_forwarding(self):
        mgr = _bare_manager(_ERROR_REPLY)
        seen = []
        mgr._error_cb = seen.append
        balances = []
        mgr._nwc_balance_cb = balances.append
        mgr._process_nwc_event(_FakeEvent())
        mgr._nwc_private_key = _FakeKey(_BALANCE_REPLY)
        mgr._process_nwc_event(_FakeEvent())
        self.assertEqual(balances, [21])
        mgr._nwc_private_key = _FakeKey(_ERROR_REPLY)
        mgr._process_nwc_event(_FakeEvent())
        self.assertEqual(len(seen), 2)

    def test_alternating_request_types_dedupe(self):
        # get_balance and list_transactions errors alternate every poll;
        # the same underlying error must be forwarded only once even though
        # the display message differs by result_type.
        mgr = _bare_manager(_ERROR_REPLY)
        seen = []
        mgr._error_cb = seen.append
        mgr._process_nwc_event(_FakeEvent())
        alt = json.loads(_ERROR_REPLY)
        alt["result_type"] = "list_transactions"
        mgr._nwc_private_key = _FakeKey(json.dumps(alt))
        mgr._process_nwc_event(_FakeEvent())
        mgr._nwc_private_key = _FakeKey(_ERROR_REPLY)
        mgr._process_nwc_event(_FakeEvent())
        self.assertEqual(len(seen), 1)

    def test_error_without_cb_does_not_raise(self):
        mgr = _bare_manager(_ERROR_REPLY)
        mgr._process_nwc_event(_FakeEvent())


class _RaisingKey:
    def decrypt_message(self, content, pubkey):
        raise ValueError("bad ciphertext")


class TestNwcWatchdogCountsAnyEvent(unittest.TestCase):
    """Bug 2 of #287 (broad form): any event on the NWC subscription is
    wallet-service activity and must reset the silence watchdog, even if it
    cannot be decrypted or carries neither result nor error."""

    def test_unknown_reply_resets_watchdog(self):
        mgr = _bare_manager(json.dumps({"result_type": "something_new"}))
        mgr._process_nwc_event(_FakeEvent())
        self.assertEqual(mgr._polls_since_last_event, 0)

    def test_undecryptable_reply_resets_watchdog(self):
        mgr = _bare_manager("unused")
        mgr._nwc_private_key = _RaisingKey()
        mgr._process_nwc_event(_FakeEvent())  # must not raise
        self.assertEqual(mgr._polls_since_last_event, 0)


class _FakeTask:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class _FakeRelay:
    def __init__(self, url, pool):
        self.url = url
        self.message_pool = pool
        self.task = _FakeTask()
        self.connected = True


class _FakeRelayManager:
    """Mimics nostr.relay_manager.RelayManager: a fresh MessagePool per
    instance, relays bind the pool current at add_relay() time."""
    instances = []

    def __init__(self, fail_close=False):
        self.message_pool = object()
        self.relays = {}
        self._fail_close = fail_close
        _FakeRelayManager.instances.append(self)

    def add_relay(self, url, *a, **kw):
        self.relays[url] = _FakeRelay(url, self.message_pool)

    async def close_connections(self):
        if self._fail_close:
            raise OSError("socket already gone")

    async def open_connections(self, *a, **kw):
        return None

    def connected_relays(self):
        return len(self.relays)


class TestReconnectKeepsMessagePool(unittest.TestCase):
    """Bug 3 of #287: the watchdog reconnect must not split-brain the receive
    path. The rebuilt manager reuses the existing MessagePool (so relays
    added afterwards, and any old websocket still delivering, feed the pool
    the consumer loop reads) and old relay tasks are cancelled even when
    close_connections() fails part-way."""

    def setUp(self):
        import asyncio
        asyncio.new_event_loop()
        import nostr_service
        self._orig_rm = nostr_service.RelayManager
        self._orig_sleep = nostr_service.TaskManager.sleep
        nostr_service.RelayManager = _FakeRelayManager

        async def _no_sleep(*a, **kw):
            return None
        nostr_service.TaskManager.sleep = _no_sleep
        _FakeRelayManager.instances = []

    def tearDown(self):
        import nostr_service
        nostr_service.RelayManager = self._orig_rm
        nostr_service.TaskManager.sleep = self._orig_sleep

    def _reconnect(self, fail_close):
        import asyncio
        mgr = _bare_manager("unused")
        old = _FakeRelayManager(fail_close=fail_close)
        old.add_relay("wss://relay.example")
        old_pool = old.message_pool
        old_task = old.relays["wss://relay.example"].task
        mgr.relay_manager = old
        mgr.keep_running = True
        mgr._relay_connected_state = {}
        mgr._subscription_ids = {}
        mgr._send_subscriptions_to_relays = lambda urls: None
        loop = asyncio.get_event_loop()
        loop.run_until_complete(mgr._reconnect_relay())
        return mgr, old, old_pool, old_task

    def test_pool_reused_and_tasks_cancelled_on_clean_close(self):
        mgr, old, old_pool, old_task = self._reconnect(fail_close=False)
        self.assertIsNot(mgr.relay_manager, old)
        self.assertIs(mgr.relay_manager.message_pool, old_pool)
        self.assertIs(mgr.relay_manager.relays["wss://relay.example"].message_pool, old_pool)
        self.assertTrue(old_task.cancelled)
        self.assertEqual(mgr._polls_since_last_event, 0)

    def test_pool_reused_and_tasks_cancelled_when_close_fails(self):
        mgr, old, old_pool, old_task = self._reconnect(fail_close=True)
        self.assertIs(mgr.relay_manager.message_pool, old_pool)
        self.assertIs(mgr.relay_manager.relays["wss://relay.example"].message_pool, old_pool)
        self.assertTrue(old_task.cancelled)


if __name__ == "__main__":
    unittest.main()
