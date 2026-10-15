"""NostrManager NIP-17 group sends: sender copy, yielding loop, failure report."""

import asyncio
import sys
import unittest

sys.path.append("apps")

from mpos import TaskManager

from nostr.key import PrivateKey
from nostr.nip17 import decrypt_gift_wrap_to_rumor
from com_micropythonos_nostr.nostr_service import NostrManager


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


if __name__ == "__main__":
    unittest.main()
