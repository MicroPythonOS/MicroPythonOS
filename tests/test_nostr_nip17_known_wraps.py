"""NostrManager skips gift wraps that are already stored, before unwrapping.

Unwrapping costs two ECDH, two NIP-44 decryptions and the seal's signature
check (well over 0.1 s on an ESP32), and a stored wrap is dropped as known
by the event store anyway. Every app start re-fetches 4 days of wraps, and
each send's relay echo is the sender's own, already stored, wrap.
"""

import shutil
import sys
import unittest

sys.path.append("apps")

from nostr.event import Event
from nostr.key import PrivateKey
from nostr.nip17 import make_nip17_messages
from com_micropythonos_nostr import nostr_service
from com_micropythonos_nostr.chat_model import Message, dm_chat_id
from com_micropythonos_nostr.event_store import EventStore
from com_micropythonos_nostr.nostr_service import (
    KIND_NIP17_CHAT,
    NostrManager,
)


class _FakeRelayManager:
    def __init__(self):
        self.published = []

    def publish_event(self, event):
        self.published.append(event)


def _wrap_event(gift):
    return Event(content=gift["content"], public_key=gift["pubkey"],
                 created_at=gift["created_at"], kind=gift["kind"], tags=gift["tags"],
                 signature=gift["sig"])


class TestKnownGiftWraps(unittest.TestCase):
    APP_NAME = "com.test.nip17_known_wraps"

    def setUp(self):
        self.private_key = PrivateKey()
        self.own_hex = self.private_key.public_key.hex()
        self.peer = PrivateKey()

        self.mgr = NostrManager.get_instance()
        self.mgr._subscriptions = []
        self.mgr._subscription_ids = {}
        self.mgr._default_relays = []
        self.mgr._nostr_configured = True
        self.mgr._nostr_private_key = self.private_key
        self.mgr.relay_manager = _FakeRelayManager()
        self.mgr._event_handlers = {}
        self.mgr._post_event_handlers = {}
        self.saved_check = getattr(self.mgr, "_is_known_event", None)

        self.decrypted = []
        self.original_decrypt = nostr_service.decrypt_gift_wrap_to_rumor

        def counting_decrypt(gift, key):
            self.decrypted.append(gift)
            return self.original_decrypt(gift, key)

        nostr_service.decrypt_gift_wrap_to_rumor = counting_decrypt

        self.routed = []
        self.persisted = []
        self.mgr.register_event_handler(KIND_NIP17_CHAT, self.routed.append)
        self.mgr.register_post_event_handler(KIND_NIP17_CHAT, self.persisted.append)

        EventStore._instances.pop(self.APP_NAME, None)
        self._cleanup()

    def tearDown(self):
        nostr_service.decrypt_gift_wrap_to_rumor = self.original_decrypt
        self.mgr._is_known_event = self.saved_check
        self.mgr._event_handlers = {}
        self.mgr._post_event_handlers = {}
        EventStore._instances.pop(self.APP_NAME, None)
        self._cleanup()

    def _cleanup(self):
        try:
            shutil.rmtree(f"prefs/{self.APP_NAME}")
        except OSError:
            pass

    def _incoming_wrap(self, content="hello"):
        """A wrap from the peer, addressed to us."""
        gifts = make_nip17_messages(self.peer, content, [self.own_hex], include_sender=False)
        return _wrap_event(gifts[0])

    def test_known_wrap_is_dropped_before_unwrapping(self):
        wrap = self._incoming_wrap()
        self.mgr.set_known_event_check(lambda event_id: event_id == wrap.id)
        self.mgr._process_event(wrap)
        self.assertEqual(self.decrypted, [])
        self.assertEqual(self.routed, [])
        self.assertEqual(self.persisted, [])

    def test_unknown_wrap_is_unwrapped_and_routed(self):
        wrap = self._incoming_wrap("new one")
        asked = []

        def check(event_id):
            asked.append(event_id)
            return False

        self.mgr.set_known_event_check(check)
        self.mgr._process_event(wrap)
        self.assertEqual(asked, [wrap.id])
        self.assertEqual(len(self.decrypted), 1)
        self.assertEqual(len(self.routed), 1)
        self.assertEqual(self.persisted[0].event.content, "new one")
        # Routed under the wrap's id, the id the store dedups on.
        self.assertEqual(self.persisted[0].event.id, wrap.id)

    def test_without_a_check_every_wrap_is_unwrapped(self):
        self.mgr.set_known_event_check(None)
        self.mgr._process_event(self._incoming_wrap())
        self.assertEqual(len(self.decrypted), 1)
        self.assertEqual(len(self.persisted), 1)

    def test_a_failing_check_falls_back_to_unwrapping(self):
        def broken(event_id):
            raise OSError("flash read failed")

        self.mgr.set_known_event_check(broken)
        self.mgr._process_event(self._incoming_wrap())
        self.assertEqual(len(self.decrypted), 1)
        self.assertEqual(len(self.persisted), 1)

    def test_relay_echo_of_a_stored_send_is_not_unwrapped(self):
        # The send path stores the local copy under the sender's own wrap id
        # (ids[0]) before publishing; the relay then echoes that wrap back.
        store = EventStore(self.APP_NAME)
        self.mgr.set_known_event_check(store.has_event)
        peer_hex = self.peer.public_key.hex()
        ids = self.mgr.publish_nip17_message("sent from here", [peer_hex])
        chat_id = dm_chat_id(self.own_hex, peer_hex)
        store.add_message(chat_id, Message(event_id=ids[0], ts=1, pubkey=self.own_hex,
                                           content="sent from here", kind=KIND_NIP17_CHAT,
                                           outgoing=True))
        echo = self.mgr.relay_manager.published[0]
        self.assertEqual(echo.id, ids[0])
        self.mgr._process_event(echo)
        self.assertEqual(self.decrypted, [])
        self.assertEqual(self.persisted, [])

        # A wrap the store has not seen still comes through.
        self.mgr._process_event(self._incoming_wrap("reply"))
        self.assertEqual(len(self.decrypted), 1)
        self.assertEqual(self.persisted[0].event.content, "reply")


if __name__ == "__main__":
    unittest.main()
