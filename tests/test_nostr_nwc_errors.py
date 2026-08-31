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


if __name__ == "__main__":
    unittest.main()
