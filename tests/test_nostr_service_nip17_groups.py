"""NostrManager NIP-17 group sends: sender copy, yielding loop, failure report,
local-copy id before publish, wrap timestamps from the Nostr clock."""

import asyncio
import sys
import unittest

sys.path.append("apps")

from mpos import TaskManager

from nostr.event import Event
from nostr.key import PrivateKey
from nostr.nip17 import decrypt_gift_wrap_to_rumor
import com_micropythonos_nostr.nostr_service as nostr_service_module
from com_micropythonos_nostr.nostr_service import NostrManager

TWO_DAYS = 2 * 24 * 60 * 60


class _FakeRelayManager:
    def __init__(self, fail_on=()):
        self.published = []
        self.calls = 0
        self.fail_on = set(fail_on)

    def publish_event(self, event):
        self.calls += 1
        if self.calls in self.fail_on:
            raise OSError("relay down")
        self.published.append(event)


def _recipient_of(event):
    for tag in event.tags:
        if len(tag) >= 2 and tag[0] == "p":
            return tag[1]
    return None


def _as_dict(event):
    return {
        "id": event.id,
        "content": event.content,
        "pubkey": event.public_key,
        "created_at": event.created_at,
        "kind": event.kind,
        "tags": event.tags,
        "sig": event.signature,
    }


class TestNip17GroupPublish(unittest.TestCase):
    def setUp(self):
        self.key = PrivateKey(bytes.fromhex(
            "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"
        ))
        self.own = self.key.public_key.hex()
        self.peers = [PrivateKey() for _ in range(3)]
        self.peer_hex = [p.public_key.hex() for p in self.peers]
        self.mgr = NostrManager.get_instance()
        self.mgr._subscriptions = []
        self.mgr._subscription_ids = {}
        self.mgr._default_relays = []
        self.mgr._nostr_configured = True
        self.mgr._nostr_private_key = self.key
        self.mgr.relay_manager = _FakeRelayManager()
        self.mgr._event_handlers = {}
        self.mgr._post_event_handlers = {}

    def test_sync_publish_wraps_for_sender_first_then_each_recipient(self):
        ids = self.mgr.publish_nip17_message(
            "hi room", self.peer_hex[:2], subject="Room", created_at=1700000000
        )
        published = self.mgr.relay_manager.published
        self.assertEqual(len(ids), 3)
        self.assertEqual([e.id for e in published], ids)
        self.assertEqual(_recipient_of(published[0]), self.own)
        self.assertEqual([_recipient_of(e) for e in published[1:]], self.peer_hex[:2])

        rumor = decrypt_gift_wrap_to_rumor(_as_dict(published[0]), self.key)
        self.assertEqual(rumor["content"], "hi room")
        self.assertEqual(rumor["created_at"], 1700000000)
        self.assertEqual([t[1] for t in rumor["tags"] if t[0] == "p"], self.peer_hex[:2])
        self.assertEqual([t[1] for t in rumor["tags"] if t[0] == "subject"], ["Room"])
        self.assertEqual(len(rumor.get("id") or ""), 64)

    def test_sync_publish_to_self_only_makes_one_wrap(self):
        ids = self.mgr.publish_nip17_message("note", [self.own])
        self.assertEqual(len(ids), 1)
        self.assertEqual(_recipient_of(self.mgr.relay_manager.published[0]), self.own)

    def test_async_publish_yields_between_wraps_and_reports_progress(self):
        progress = []
        sleeps = []
        original = TaskManager.sleep_ms

        def recording_sleep(ms):
            sleeps.append(ms)
            return asyncio.sleep_ms(ms)

        TaskManager.sleep_ms = staticmethod(recording_sleep)
        try:
            result = asyncio.run(self.mgr.publish_nip17_message_async(
                "hi all",
                self.peer_hex,
                subject="Room",
                created_at=1700000000,
                progress=lambda done, total: progress.append((done, total)),
            ))
        finally:
            TaskManager.sleep_ms = staticmethod(original)

        self.assertEqual(progress, [(1, 4), (2, 4), (3, 4), (4, 4)])
        self.assertEqual(len(sleeps), 4)
        published = self.mgr.relay_manager.published
        self.assertEqual(len(published), 4)
        self.assertEqual(result.ids, [e.id for e in published])
        self.assertEqual(result.local_id, published[0].id)
        self.assertEqual(_recipient_of(published[0]), self.own)
        self.assertEqual(result.failed, [])
        self.assertEqual([r for r, _ in result.published], [self.own] + self.peer_hex)

    def test_async_publish_keeps_going_after_a_failed_wrap(self):
        self.mgr.relay_manager = _FakeRelayManager(fail_on=(2,))
        result = asyncio.run(self.mgr.publish_nip17_message_async(
            "hi all", self.peer_hex, created_at=1700000000
        ))
        published = self.mgr.relay_manager.published
        self.assertEqual(len(published), 3)
        self.assertEqual(result.failed, [self.peer_hex[0]])
        self.assertEqual([r for r, _ in result.published], [self.own, self.peer_hex[1], self.peer_hex[2]])
        self.assertEqual(result.local_id, published[0].id)

    def test_async_publish_raises_when_nothing_was_published(self):
        self.mgr.relay_manager = _FakeRelayManager(fail_on=(1, 2, 3))
        try:
            asyncio.run(self.mgr.publish_nip17_message_async(
                "hi", self.peer_hex[:2], created_at=1700000000
            ))
        except RuntimeError:
            return
        raise AssertionError("publish_nip17_message_async should raise when no wrap was published")

    def test_async_publish_reports_the_local_id_before_anything_is_published(self):
        seen = []
        relay = self.mgr.relay_manager

        def on_local_id(gift_id):
            # Nothing may have reached the relay yet: the caller stores its
            # local copy under this id so the relay echo deduplicates.
            seen.append((gift_id, len(relay.published)))

        result = asyncio.run(self.mgr.publish_nip17_message_async(
            "hi all", self.peer_hex, created_at=1700000000, on_local_id=on_local_id
        ))
        self.assertEqual(len(seen), 1)
        gift_id, published_before = seen[0]
        self.assertEqual(published_before, 0)
        self.assertEqual(gift_id, relay.published[0].id)
        self.assertEqual(_recipient_of(relay.published[0]), self.own)
        self.assertEqual(result.local_id, gift_id)
        self.assertEqual(result.ids[0], gift_id)

    def test_local_id_is_the_sender_wrap_even_when_its_publish_fails(self):
        self.mgr.relay_manager = _FakeRelayManager(fail_on=(1,))
        seen = []
        result = asyncio.run(self.mgr.publish_nip17_message_async(
            "hi all", self.peer_hex[:2], created_at=1700000000, on_local_id=seen.append
        ))
        self.assertEqual(len(seen), 1)
        self.assertEqual(result.local_id, seen[0])
        self.assertEqual(result.failed, [self.own])
        # The published list starts with the first recipient's wrap.
        self.assertEqual([r for r, _ in result.published], self.peer_hex[:2])
        self.assertNotEqual(result.ids[0], result.local_id)


class TestNip17WrapTimestamps(unittest.TestCase):
    """Seals and gift wraps must be dated from the Nostr (Unix) clock.

    On the ESP32 port time.time() counts from 2000-01-01, which is why
    Event.epoch_seconds() exists. The library defaults read time.time(), so
    the app passes the timestamps itself. Simulated by pinning the clock the
    app and the library share."""

    PINNED = 1700000000

    def setUp(self):
        self.key = PrivateKey(bytes.fromhex(
            "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"
        ))
        self.peer = PrivateKey()
        self.mgr = NostrManager.get_instance()
        self.mgr._subscriptions = []
        self.mgr._subscription_ids = {}
        self.mgr._default_relays = []
        self.mgr._nostr_configured = True
        self.mgr._nostr_private_key = self.key
        self.mgr.relay_manager = _FakeRelayManager()
        self.mgr._event_handlers = {}
        self.mgr._post_event_handlers = {}
        self._orig_epoch_seconds = Event.epoch_seconds
        Event.epoch_seconds = staticmethod(lambda: self.PINNED)
        self._orig_tweaked = nostr_service_module._tweaked_timestamp

    def tearDown(self):
        Event.epoch_seconds = self._orig_epoch_seconds
        nostr_service_module._tweaked_timestamp = self._orig_tweaked

    def _seal_of(self, wrap):
        from nostr.nip44 import decrypt as nip44_decrypt
        from nostr.nip44 import get_conversation_key
        import json

        conv_key = get_conversation_key(self.peer, wrap.public_key)
        return json.loads(nip44_decrypt(wrap.content, conv_key))

    def _assert_within_two_days_before(self, ts, now):
        self.assertTrue(
            now - TWO_DAYS <= ts <= now,
            "%s is not within two days before the Nostr clock %s" % (ts, now),
        )

    def test_wraps_and_seals_are_dated_from_the_nostr_clock(self):
        self.mgr.publish_nip17_message("hello", [self.peer.public_key.hex()])
        wraps = self.mgr.relay_manager.published
        self.assertEqual(len(wraps), 2)
        for wrap in wraps:
            self._assert_within_two_days_before(wrap.created_at, self.PINNED)
        seal = self._seal_of(wraps[1])
        self._assert_within_two_days_before(seal["created_at"], self.PINNED)
        rumor = decrypt_gift_wrap_to_rumor(_as_dict(wraps[1]), self.peer)
        self.assertEqual(rumor["created_at"], self.PINNED)

    def test_async_wraps_are_dated_from_the_nostr_clock(self):
        asyncio.run(self.mgr.publish_nip17_message_async("hello", [self.peer.public_key.hex()]))
        for wrap in self.mgr.relay_manager.published:
            self._assert_within_two_days_before(wrap.created_at, self.PINNED)

    def test_queued_message_keeps_its_time_but_wraps_are_dated_from_now(self):
        # An outbox flush passes the moment the user wrote the message.
        written = self.PINNED - 3 * TWO_DAYS
        self.mgr.publish_nip17_message("later", [self.peer.public_key.hex()], created_at=written)
        wraps = self.mgr.relay_manager.published
        for wrap in wraps:
            self._assert_within_two_days_before(wrap.created_at, self.PINNED)
        rumor = decrypt_gift_wrap_to_rumor(_as_dict(wraps[1]), self.peer)
        self.assertEqual(rumor["created_at"], written)

    def test_without_library_backdating_wraps_carry_the_nostr_send_time(self):
        # Older micropython-nostr: no tweaked_timestamp; the app must still
        # not fall back to the library's time.time() default.
        nostr_service_module._tweaked_timestamp = None
        self.mgr.publish_nip17_message("hello", [self.peer.public_key.hex()])
        wraps = self.mgr.relay_manager.published
        self.assertEqual([w.created_at for w in wraps], [self.PINNED, self.PINNED])
        self.assertEqual(self._seal_of(wraps[1])["created_at"], self.PINNED)


if __name__ == "__main__":
    unittest.main()
