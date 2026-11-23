"""
Unit tests for NIP-44 encryption in NostrManager's Nostr Wallet Connect client.

NIP-47 lets a wallet service advertise the encryption schemes it supports in
the "encryption" tag of its info event (kind 13194). NostrManager starts every
connection on nip04, switches to nip44_v2 when the wallet lists it, and falls
back to nip04 if the wallet then answers UNSUPPORTED_ENCRYPTION. Replies are
decrypted per event, so NIP-04 replies to requests sent before a switch still
work.

The wallet side is played with real keys, so these tests check the actual
NIP-04 and NIP-44 ciphertexts both ways, not mocks.

Usage:
    python3 scripts/test_runner.py tests/test_nostr_nwc_nip44.py
"""

import json
import sys
import time
import unittest

sys.path.append("apps/com_micropythonos_nostr")
from nostr.event import Event
from nostr.key import PrivateKey
from nostr import nip44
import nostr_service
from nostr_service import NostrManager


class _FakeRelayManager:
    def __init__(self):
        self.published = []
        self.messages = []
        self.subscriptions = []

    def publish_event(self, event):
        self.published.append(event)

    def publish_message(self, message):
        self.messages.append(message)

    def add_subscription(self, sub_id, filters):
        self.subscriptions.append((sub_id, filters))


class _BareManager(NostrManager):
    # Skip NostrManager.__init__ (relays, tasks). MicroPython has no usable
    # __new__, hence the subclass with a no-op constructor.
    def __init__(self):
        pass

    def _ensure_main_task(self):
        pass


def _manager(client_key, wallet_key):
    mgr = _BareManager()
    mgr._nwc_private_key = client_key
    mgr._nwc_wallet_pubkey = wallet_key.public_key.hex()
    mgr._nwc_configured = True
    mgr._nwc_sub_id = "micropython_nwc_test"
    mgr._nwc_filters = None
    mgr._nwc_encryption = "nip04"
    mgr._nwc_nip44_refused = False
    mgr._nwc_nip04_refused = False
    mgr._nwc_request_schemes = []
    mgr._nwc_list_limit = 21
    mgr._nwc_info = {}
    mgr._nwc_conversation_key = nip44.get_conversation_key(
        client_key, wallet_key.public_key.hex())
    mgr._last_nwc_poll = time.time()
    mgr._last_nwc_error = None
    mgr._polls_since_last_event = 0
    mgr._error_cb = None
    mgr._nwc_balance_cb = None
    mgr._nwc_payments_cb = None
    mgr._nwc_notification_cb = None
    mgr._events_updated_cb = None
    mgr.relay_manager = _FakeRelayManager()
    return mgr


def _info_event(wallet_key, encryption=None, created_at=None):
    tags = []
    if encryption is not None:
        tags.append(["encryption", encryption])
    kwargs = {}
    if created_at is not None:
        kwargs["created_at"] = created_at
    event = Event(
        content="get_balance list_transactions",
        public_key=wallet_key.public_key.hex(),
        kind=13194,
        tags=tags,
        **kwargs
    )
    wallet_key.sign_event(event)
    return event


def _reply_event(wallet_key, client_key, payload, scheme, kind=23195, request_id=None):
    text = json.dumps(payload)
    if scheme == "nip44_v2":
        ck = nip44.get_conversation_key(wallet_key, client_key.public_key.hex())
        content = nip44.encrypt(text, ck)
    else:
        content = wallet_key.encrypt_message(text, client_key.public_key.hex())
    event = Event(
        content=content,
        public_key=wallet_key.public_key.hex(),
        kind=kind,
        tags=[["p", client_key.public_key.hex()]] + ([["e", request_id]] if request_id else []),
    )
    wallet_key.sign_event(event)
    return event


_UNSUPPORTED = {"error": {"code": "UNSUPPORTED_ENCRYPTION", "message": "not supported"}}


def _unsupported(result_type):
    reply = dict(_UNSUPPORTED)
    reply["result_type"] = result_type
    return reply


def _filter_kinds(filters):
    return [f.get("kinds") for f in filters.to_json_array()]


class _FastNip44Case(unittest.TestCase):
    """Pretend the Viper ChaCha20 is present: the desktop build runs the
    pure-Python core, where NostrManager prefers nip04 when it can."""

    def setUp(self):
        self._fast = nostr_service.NIP44_FAST
        nostr_service.NIP44_FAST = True

    def tearDown(self):
        nostr_service.NIP44_FAST = self._fast


class TestNwcEncryptionNegotiation(_FastNip44Case):
    def setUp(self):
        super().setUp()
        self.client = PrivateKey()
        self.wallet = PrivateKey()
        self.mgr = _manager(self.client, self.wallet)

    def test_starts_on_nip04_with_nip04_notifications(self):
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        kinds = _filter_kinds(self.mgr._build_nwc_filters())
        self.assertEqual(kinds, [[23195, 23196], [13194]])

    def test_info_listing_nip44_switches_and_resubscribes(self):
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2 nip04"))
        self.assertEqual(self.mgr._nwc_encryption, "nip44_v2")
        self.assertEqual(_filter_kinds(self.mgr._nwc_filters), [[23195, 23197], [13194]])
        self.assertEqual(len(self.mgr.relay_manager.messages), 1)
        req = json.loads(self.mgr.relay_manager.messages[0])
        self.assertEqual(req[0], "REQ")
        self.assertEqual(req[1], "micropython_nwc_test")
        self.assertEqual(req[2]["kinds"], [23195, 23197])
        self.assertEqual(req[3], {"kinds": [13194], "authors": [self.wallet.public_key.hex()], "limit": 1})
        # The next poll is due straight away, so balances arrive in the new mode.
        self.assertTrue(time.time() - self.mgr._last_nwc_poll >= NostrManager.NWC_POLL_SECONDS)

    def test_repeated_info_event_changes_nothing(self):
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2 nip04"))
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2 nip04"))
        self.assertEqual(len(self.mgr.relay_manager.messages), 1)

    def test_info_without_encryption_tag_means_nip04(self):
        self.mgr._process_event(_info_event(self.wallet))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        self.assertEqual(self.mgr.relay_manager.messages, [])

    def test_info_listing_only_nip04_stays_nip04(self):
        self.mgr._process_event(_info_event(self.wallet, "nip04"))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")

    def test_newer_info_dropping_nip44_switches_back(self):
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2", created_at=1000))
        self.mgr._process_event(_info_event(self.wallet, "nip04", created_at=2000))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        self.assertEqual(_filter_kinds(self.mgr._nwc_filters), [[23195, 23196], [13194]])

    def test_older_info_from_another_relay_is_ignored(self):
        # Each relay returns its own latest copy of the replaceable event.
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2 nip04", created_at=2000))
        self.mgr._process_event(_info_event(self.wallet, None, created_at=1000))
        self.assertEqual(self.mgr._nwc_encryption, "nip44_v2")
        self.assertEqual(len(self.mgr.relay_manager.messages), 1)

    def test_older_info_first_then_newer_upgrades(self):
        self.mgr._process_event(_info_event(self.wallet, None, created_at=1000))
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2 nip04", created_at=2000))
        self.assertEqual(self.mgr._nwc_encryption, "nip44_v2")

    def test_info_from_another_author_is_ignored(self):
        stranger = PrivateKey()
        self.mgr._process_nwc_info = lambda event: self.fail("stranger's info event routed to NWC")
        self.mgr._event_handlers = {}
        self.mgr._post_event_handlers = {}
        self.mgr._subscriptions = []
        self.mgr.events = []
        self.mgr._is_known_event = None
        self.mgr._nostr_private_key = None
        self.mgr._process_event(_info_event(stranger, "nip44_v2"))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")

    def test_no_conversation_key_stays_nip04(self):
        self.mgr._nwc_conversation_key = None
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2 nip04"))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")


class TestNwcRequests(_FastNip44Case):
    def setUp(self):
        super().setUp()
        self.client = PrivateKey()
        self.wallet = PrivateKey()
        self.mgr = _manager(self.client, self.wallet)

    def _sent(self):
        self.assertEqual(len(self.mgr.relay_manager.published), 1)
        return self.mgr.relay_manager.published[0]

    def test_nip04_request_has_no_encryption_tag(self):
        self.mgr.nwc_fetch_balance()
        event = self._sent()
        self.assertEqual(event.kind, 23194)
        self.assertTrue("?iv=" in event.content)
        self.assertFalse(any(t[0] == "encryption" for t in event.tags))
        decrypted = self.wallet.decrypt_message(event.content, self.client.public_key.hex())
        self.assertEqual(json.loads(decrypted)["method"], "get_balance")

    def test_nip44_request_is_tagged_signed_and_decryptable_by_wallet(self):
        self.mgr._nwc_encryption = "nip44_v2"
        self.mgr._nwc_list_limit = 7
        self.mgr.nwc_fetch_payments()
        event = self._sent()
        self.assertEqual(event.kind, 23194)
        self.assertTrue(["encryption", "nip44_v2"] in event.tags)
        self.assertTrue(["p", self.wallet.public_key.hex()] in event.tags)
        self.assertFalse("?iv=" in event.content)
        self.assertEqual(event.public_key, self.client.public_key.hex())
        self.assertEqual(event.id, Event.compute_id(
            event.public_key, event.created_at, event.kind, event.tags, event.content))
        self.assertTrue(event.verify())
        ck = nip44.get_conversation_key(self.wallet, self.client.public_key.hex())
        request = json.loads(nip44.decrypt(event.content, ck))
        self.assertEqual(request, {"method": "list_transactions", "params": {"limit": 7}})


class TestNwcRequestsWhenNip44Breaks(_FastNip44Case):
    def test_encrypt_failure_sends_nip04_and_stays_there(self):
        client = PrivateKey()
        wallet = PrivateKey()
        mgr = _manager(client, wallet)
        mgr._nwc_encryption = "nip44_v2"
        original = nostr_service.nip44_encrypt

        def broken(*args):
            raise NameError("name 'uint' isn't defined")

        nostr_service.nip44_encrypt = broken
        try:
            mgr.nwc_fetch_balance()
        finally:
            nostr_service.nip44_encrypt = original
        self.assertEqual(len(mgr.relay_manager.published), 1)
        event = mgr.relay_manager.published[0]
        self.assertTrue("?iv=" in event.content)
        self.assertFalse(any(t[0] == "encryption" for t in event.tags))
        self.assertEqual(mgr._nwc_encryption, "nip04")
        self.assertTrue(mgr._nwc_nip44_refused)
        mgr._process_event(_info_event(wallet, "nip44_v2 nip04"))
        self.assertEqual(mgr._nwc_encryption, "nip04")


class TestNwcReplies(_FastNip44Case):
    def setUp(self):
        super().setUp()
        self.client = PrivateKey()
        self.wallet = PrivateKey()
        self.mgr = _manager(self.client, self.wallet)
        self.balances = []
        self.errors = []
        self.notifications = []
        self.mgr._nwc_balance_cb = self.balances.append
        self.mgr._error_cb = self.errors.append
        self.mgr._nwc_notification_cb = self.notifications.append

    def test_nip44_balance_reply(self):
        self.mgr._nwc_encryption = "nip44_v2"
        reply = {"result_type": "get_balance", "result": {"balance": 21000}}
        self.mgr._process_event(_reply_event(self.wallet, self.client, reply, "nip44_v2"))
        self.assertEqual(self.balances, [21])

    def test_nip04_reply_still_decrypts_after_switch(self):
        self.mgr._nwc_encryption = "nip44_v2"
        reply = {"result_type": "get_balance", "result": {"balance": 5000}}
        self.mgr._process_event(_reply_event(self.wallet, self.client, reply, "nip04"))
        self.assertEqual(self.balances, [5])

    def test_nip44_notification_kind_23197(self):
        self.mgr._nwc_encryption = "nip44_v2"
        payload = {"notification_type": "payment_received",
                   "notification": {"type": "incoming", "amount": 1000}}
        self.mgr._process_event(_reply_event(
            self.wallet, self.client, payload, "nip44_v2", kind=23197))
        self.assertEqual(self.notifications, [{"type": "incoming", "amount": 1000}])

    def _send_poll(self):
        """One poll: get_balance then list_transactions. Returns their ids."""
        self.mgr.nwc_fetch_balance()
        self.mgr.nwc_fetch_payments()
        return [e.id for e in self.mgr.relay_manager.published[-2:]]

    def test_unsupported_encryption_falls_back_to_nip04_for_good(self):
        self.mgr._nwc_encryption = "nip44_v2"
        balance_id, payments_id = self._send_poll()
        # Both requests of the poll are refused; neither reply is an error
        # the user should see.
        self.mgr._process_event(_reply_event(
            self.wallet, self.client, _unsupported("get_balance"), "nip04", request_id=balance_id))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        self.assertTrue(time.time() - self.mgr._last_nwc_poll >= NostrManager.NWC_POLL_SECONDS)
        self.mgr._process_event(_reply_event(
            self.wallet, self.client, _unsupported("list_transactions"), "nip04", request_id=payments_id))
        self.assertEqual(self.errors, [])
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        # The relay replays the stored info event on every resubscribe; it
        # must not flip the connection back to the refused scheme.
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2 nip04"))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")

    def test_nip44_only_wallet_refusing_the_first_nip04_poll_keeps_nip44(self):
        # The first poll goes out as nip04 before the info event arrives.
        balance_id, payments_id = self._send_poll()
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2"))
        self.assertEqual(self.mgr._nwc_encryption, "nip44_v2")
        for request_id, result_type in ((balance_id, "get_balance"), (payments_id, "list_transactions")):
            self.mgr._process_event(_reply_event(
                self.wallet, self.client, _unsupported(result_type), "nip44_v2", request_id=request_id))
        self.assertEqual(self.mgr._nwc_encryption, "nip44_v2")
        self.assertFalse(self.mgr._nwc_nip44_refused)
        self.assertEqual(self.errors, [])

    def test_unsupported_encryption_on_a_nip04_only_connection_is_reported(self):
        self.mgr._process_event(_info_event(self.wallet))
        balance_id, _ = self._send_poll()
        self.mgr._process_event(_reply_event(
            self.wallet, self.client, _unsupported("get_balance"), "nip04", request_id=balance_id))
        self.assertEqual(len(self.errors), 1)
        self.assertTrue("UNSUPPORTED_ENCRYPTION" in self.errors[0])

    def test_nip04_refusal_before_the_info_event_tries_nip44(self):
        balance_id, payments_id = self._send_poll()
        for request_id, result_type in ((balance_id, "get_balance"), (payments_id, "list_transactions")):
            self.mgr._process_event(_reply_event(
                self.wallet, self.client, _unsupported(result_type), "nip04", request_id=request_id))
        self.assertEqual(self.errors, [])
        self.assertEqual(self.mgr._nwc_encryption, "nip44_v2")
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2"))
        self.assertEqual(self.mgr._nwc_encryption, "nip44_v2")

    def test_wallet_refusing_both_without_an_info_event_is_reported(self):
        # The info event never arrives; the wallet refuses nip04, then nip44.
        for _ in range(3):
            ids = self._send_poll()
            for request_id, result_type in zip(ids, ("get_balance", "list_transactions")):
                self.mgr._process_event(_reply_event(
                    self.wallet, self.client, _unsupported(result_type), "nip04", request_id=request_id))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        self.assertTrue(self.mgr._nwc_nip44_refused)
        self.assertEqual(len(self.errors), 1)

    def test_nip04_refusal_without_nip44_available_is_reported(self):
        self.mgr._nwc_conversation_key = None
        balance_id, _ = self._send_poll()
        self.mgr._process_event(_reply_event(
            self.wallet, self.client, _unsupported("get_balance"), "nip04", request_id=balance_id))
        self.assertEqual(len(self.errors), 1)

    def test_unsupported_encryption_without_e_tag_in_nip44_mode_falls_back(self):
        self.mgr._nwc_encryption = "nip44_v2"
        self.mgr._process_event(_reply_event(
            self.wallet, self.client, _unsupported("get_balance"), "nip04"))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        self.assertEqual(self.errors, [])

    def test_untagged_refusals_of_a_nip44_poll_fall_back_at_once(self):
        # Info first (configure on a running manager does not poll), then a
        # wallet that refuses nip44 without "e" tags: fall back on the first
        # refusal, keep the second quiet.
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2 nip04"))
        self._send_poll()
        self.mgr._process_event(_reply_event(
            self.wallet, self.client, _unsupported("get_balance"), "nip04"))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        self.mgr._process_event(_reply_event(
            self.wallet, self.client, _unsupported("list_transactions"), "nip04"))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        self.assertEqual(self.errors, [])
        self.assertEqual(self.mgr._nwc_request_schemes, [])

    def test_untagged_successes_close_their_requests(self):
        self._send_poll()
        for _ in range(2):
            self.mgr._process_event(_reply_event(
                self.wallet, self.client, {"result_type": "get_balance", "result": {"balance": 1000}}, "nip04"))
        self.assertEqual(self.mgr._nwc_request_schemes, [])
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2 nip04"))
        self._send_poll()
        self.mgr._process_event(_reply_event(
            self.wallet, self.client, _unsupported("get_balance"), "nip04"))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        self.assertTrue(self.mgr._nwc_nip44_refused)

    def test_replayed_refusal_from_an_earlier_session_is_ignored(self):
        self.mgr._nwc_encryption = "nip44_v2"
        self._send_poll()
        self.mgr._process_event(_reply_event(
            self.wallet, self.client, _unsupported("get_balance"), "nip04", request_id="ab" * 32))
        self.assertEqual(self.mgr._nwc_encryption, "nip44_v2")
        self.assertFalse(self.mgr._nwc_nip44_refused)
        self.assertEqual(self.errors, [])
        self.assertEqual(len(self.mgr._nwc_request_schemes), 2)

    def test_requests_the_wallet_relay_never_got_are_not_awaited(self):
        # Boot: a default relay is up but the wallet's relay is still
        # reconnecting, so publish_message skips it and the first poll is
        # lost. Later untagged refusals must still match the right requests.
        class _Relay:
            connected = False

        relay = _Relay()
        self.mgr.relay_manager.relays = {"wss://wallet.example": relay}
        self.mgr._nwc_relays = ["wss://wallet.example"]
        self._send_poll()
        self.assertEqual([e[3] for e in self.mgr._nwc_request_schemes], [False, False])
        relay.connected = True
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2 nip04"))
        self._send_poll()
        self.mgr._process_event(_reply_event(
            self.wallet, self.client, _unsupported("get_balance"), "nip04"))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        self.assertTrue(self.mgr._nwc_nip44_refused)

    def test_reply_that_fails_to_decrypt_still_closes_its_request(self):
        self._send_poll()
        broken = Event(
            content="not-a-ciphertext",
            public_key=self.wallet.public_key.hex(),
            kind=23195,
            tags=[["p", self.client.public_key.hex()]],
        )
        self.wallet.sign_event(broken)
        self.mgr._process_event(broken)
        self.assertEqual(len(self.mgr._nwc_request_schemes), 1)

    def test_tagged_reply_still_matches_a_request_sent_while_the_relay_looked_down(self):
        # The same relay can sit in the pool under another spelling and
        # carry the request anyway.
        class _Relay:
            connected = False

        self.mgr.relay_manager.relays = {"wss://wallet.example": _Relay()}
        self.mgr._nwc_relays = ["wss://wallet.example"]
        self.mgr._nwc_encryption = "nip44_v2"
        balance_id, _ = self._send_poll()
        self.mgr._process_event(_reply_event(
            self.wallet, self.client, _unsupported("get_balance"), "nip04", request_id=balance_id))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        self.assertTrue(self.mgr._nwc_nip44_refused)

    def test_one_lost_poll_does_not_shift_later_matching(self):
        # Poll 1 is lost although the relay looked connected; poll 2 goes
        # out NWC_POLL_SECONDS later and its untagged replies must match it.
        self._send_poll()
        sent_earlier = time.time() - NostrManager.NWC_POLL_SECONDS
        self.mgr._nwc_request_schemes = [
            (i, sch, sent_earlier, up) for i, sch, _, up in self.mgr._nwc_request_schemes]
        self.mgr._nwc_encryption = "nip44_v2"
        self._send_poll()
        self.mgr._process_event(_reply_event(
            self.wallet, self.client, _unsupported("get_balance"), "nip04"))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        self.assertTrue(self.mgr._nwc_nip44_refused)

    def test_requests_older_than_the_reply_window_are_given_up(self):
        self._send_poll()
        old = time.time() - NostrManager.NWC_REPLY_WINDOW_SECONDS - 30
        self.mgr._nwc_request_schemes = [(i, sch, old, up) for i, sch, _, up in self.mgr._nwc_request_schemes]
        self.mgr._nwc_encryption = "nip44_v2"
        self._send_poll()
        self.mgr._process_event(_reply_event(
            self.wallet, self.client, _unsupported("get_balance"), "nip04"))
        # Matched to the nip44_v2 request, not to the stale nip04 ones.
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        self.assertTrue(self.mgr._nwc_nip44_refused)

    def test_request_scheme_memory_is_bounded(self):
        for _ in range(12):
            self._send_poll()
        self.assertEqual(len(self.mgr._nwc_request_schemes), 16)


class TestConfigureNwc(_FastNip44Case):
    def test_configure_derives_shared_conversation_key_and_resets_mode(self):
        client = PrivateKey()
        wallet = PrivateKey()
        mgr = _manager(client, wallet)
        mgr._nwc_nwc_url = None
        mgr._nwc_encryption = "nip44_v2"
        mgr._nwc_nip44_refused = True
        mgr._nwc_conversation_key = None
        url = "nostr+walletconnect://{}?relay=wss://relay.example&secret={}".format(
            wallet.public_key.hex(), client.raw_secret.hex())
        mgr.configure_nwc(url)
        self.assertEqual(mgr._nwc_encryption, "nip04")
        self.assertFalse(mgr._nwc_nip44_refused)
        # Rebuilt for the new connection: nip04 notifications, new client key.
        self.assertEqual(_filter_kinds(mgr._nwc_filters), [[23195, 23196], [13194]])
        self.assertEqual(mgr._nwc_filters.to_json_array()[0]["#p"], [client.public_key.hex()])
        wallet_ck = nip44.get_conversation_key(wallet, client.public_key.hex())
        self.assertEqual(mgr._nwc_conversation_key, wallet_ck)
        self.assertEqual(mgr._nwc_request_schemes, [])

    def _url(self, wallet, client):
        return "nostr+walletconnect://{}?relay=wss://relay.example&secret={}".format(
            wallet.public_key.hex(), client.raw_secret.hex())

    def test_repairing_with_the_same_wallet_reuses_its_info(self):
        # The relay pool drops the replayed info event as already seen, so the
        # new connection must not wait for it.
        wallet = PrivateKey()
        mgr = _manager(PrivateKey(), wallet)
        mgr._nwc_nwc_url = None
        mgr.configure_nwc(self._url(wallet, PrivateKey()))
        mgr._process_event(_info_event(wallet, "nip44_v2 nip04"))
        self.assertEqual(mgr._nwc_encryption, "nip44_v2")
        mgr.configure_nwc(self._url(wallet, PrivateKey()))
        self.assertEqual(mgr._nwc_encryption, "nip44_v2")
        self.assertEqual(_filter_kinds(mgr._build_nwc_filters()), [[23195, 23197], [13194]])

    def test_a_different_wallet_starts_on_nip04(self):
        wallet = PrivateKey()
        other = PrivateKey()
        mgr = _manager(PrivateKey(), wallet)
        mgr._nwc_nwc_url = None
        mgr.configure_nwc(self._url(wallet, PrivateKey()))
        mgr._process_event(_info_event(wallet, "nip44_v2 nip04", created_at=5000))
        mgr.configure_nwc(self._url(other, PrivateKey()))
        self.assertEqual(mgr._nwc_encryption, "nip04")
        self.assertEqual(list(mgr._nwc_info.keys()), [wallet.public_key.hex()])
        # An older info event from the new wallet still counts.
        mgr._process_event(_info_event(other, "nip44_v2", created_at=10))
        self.assertEqual(mgr._nwc_encryption, "nip44_v2")

    def test_switching_back_to_an_earlier_wallet_reuses_its_info(self):
        x = PrivateKey()
        y = PrivateKey()
        mgr = _manager(PrivateKey(), x)
        mgr._nwc_nwc_url = None
        mgr.configure_nwc(self._url(x, PrivateKey()))
        mgr._process_event(_info_event(x, "nip44_v2 nip04"))
        mgr.configure_nwc(self._url(y, PrivateKey()))
        mgr._process_event(_info_event(y, None))
        self.assertEqual(mgr._nwc_encryption, "nip04")
        mgr.configure_nwc(self._url(x, PrivateKey()))
        self.assertEqual(mgr._nwc_encryption, "nip44_v2")

    def test_info_cache_is_bounded(self):
        mgr = _manager(PrivateKey(), PrivateKey())
        mgr._nwc_nwc_url = None
        for _ in range(6):
            wallet = PrivateKey()
            mgr.configure_nwc(self._url(wallet, PrivateKey()))
            mgr._process_event(_info_event(wallet, "nip44_v2"))
        self.assertEqual(len(mgr._nwc_info), 4)

    def test_reconfiguring_a_running_manager_resubscribes_at_once(self):
        wallet = PrivateKey()
        client = PrivateKey()
        mgr = _manager(PrivateKey(), wallet)
        mgr._nwc_nwc_url = None
        mgr.configure_nwc(self._url(wallet, client))
        req = json.loads(mgr.relay_manager.messages[-1])
        self.assertEqual(req[1], "micropython_nwc_test")
        self.assertEqual(req[2]["#p"], [client.public_key.hex()])

    def test_configuring_before_the_manager_runs_does_not_subscribe(self):
        wallet = PrivateKey()
        mgr = _manager(PrivateKey(), wallet)
        mgr._nwc_nwc_url = None
        mgr.relay_manager = None
        mgr.configure_nwc(self._url(wallet, PrivateKey()))
        self.assertTrue(mgr._relays_dirty)


class TestNwcOnTheSlowChaCha20Core(unittest.TestCase):
    """Firmware whose micropython-nostr lacks the Viper core (MPOS 0.22.0 and
    older): a transaction list takes seconds to decrypt with NIP-44."""

    def setUp(self):
        self._fast = nostr_service.NIP44_FAST
        nostr_service.NIP44_FAST = False
        self.wallet = PrivateKey()
        self.client = PrivateKey()
        self.mgr = _manager(self.client, self.wallet)
        self.errors = []
        self.mgr._error_cb = self.errors.append

    def tearDown(self):
        nostr_service.NIP44_FAST = self._fast

    def test_wallet_offering_nip04_too_stays_on_nip04(self):
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2 nip04"))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")

    def test_wallet_listing_only_nip44_stays_on_nip04_while_it_answers(self):
        # Rizful listed only nip44_v2 in November 2026 but still answered
        # nip04, which decrypts in C instead of seconds of Python.
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2"))
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        self.assertEqual(self.mgr.relay_manager.messages, [])

    def _poll_refused(self):
        self.mgr.nwc_fetch_balance()
        self.mgr.nwc_fetch_payments()
        ids = [e.id for e in self.mgr.relay_manager.published[-2:]]
        for request_id, result_type in zip(ids, ("get_balance", "list_transactions")):
            self.mgr._process_event(_reply_event(
                self.wallet, self.client, _unsupported(result_type), "nip04", request_id=request_id))

    def test_nip04_refusal_switches_a_nip44_wallet_to_nip44(self):
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2"))
        self._poll_refused()
        self.assertEqual(self.mgr._nwc_encryption, "nip44_v2")
        self.assertEqual(self.errors, [])
        self.assertTrue(time.time() - self.mgr._last_nwc_poll >= NostrManager.NWC_POLL_SECONDS)
        self.mgr.nwc_fetch_balance()
        self.assertTrue(["encryption", "nip44_v2"] in self.mgr.relay_manager.published[-1].tags)

    def test_nip04_refusal_without_nip44_on_offer_is_reported(self):
        self.mgr._process_event(_info_event(self.wallet, "nip04"))
        self._poll_refused()
        self.assertEqual(self.mgr._nwc_encryption, "nip04")
        self.assertEqual(len(self.errors), 1)

    def test_refusals_without_e_tags_switch_once_and_stay_quiet(self):
        # NIP-47 only says replies SHOULD carry the "e" tag.
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2"))
        self.mgr.nwc_fetch_balance()
        self.mgr.nwc_fetch_payments()
        for result_type in ("get_balance", "list_transactions"):
            self.mgr._process_event(_reply_event(
                self.wallet, self.client, _unsupported(result_type), "nip04"))
        self.assertEqual(self.mgr._nwc_encryption, "nip44_v2")
        self.assertFalse(self.mgr._nwc_nip44_refused)
        self.assertEqual(self.errors, [])

    def test_configure_forgets_the_nip04_refusal(self):
        self.mgr._process_event(_info_event(self.wallet, "nip44_v2"))
        self._poll_refused()
        self.mgr._nwc_nwc_url = None
        self.mgr.configure_nwc("nostr+walletconnect://{}?relay=wss://relay.example&secret={}".format(
            self.wallet.public_key.hex(), PrivateKey().raw_secret.hex()))
        self.assertFalse(self.mgr._nwc_nip04_refused)
        self.assertEqual(self.mgr._nwc_encryption, "nip04")


if __name__ == "__main__":
    unittest.main()
