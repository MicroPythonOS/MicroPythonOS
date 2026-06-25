"""Unit test for NostrManager.add_subscription idempotency.

Calling add_subscription with the same name and filter while already
connected must not re-send a REQ to the relays. Activities resume frequently,
so re-fetching would be wasteful.
"""

import sys
import unittest

sys.path.append("apps/com.micropythonos.nostr/assets")

from nostr.filter import Filter, Filters
from nostr_service import NostrManager


class _FakeRelayManager:
    def __init__(self):
        self.relays = {}
        self.subscriptions = []
        self.published_messages = []
        self.added_subscriptions = []

    def add_subscription(self, sub_id, filters):
        self.added_subscriptions.append((sub_id, filters))

    def publish_message(self, message):
        self.published_messages.append(message)


class TestNostrSubscriptionIdempotent(unittest.TestCase):

    def setUp(self):
        mgr = NostrManager.get_instance()
        mgr.stop()
        mgr._main_task = None
        mgr._cleanup_done = True
        mgr._subscriptions = []
        mgr._subscription_ids = {}
        mgr._default_relays = []
        mgr._nostr_configured = False
        mgr._nostr_private_key = None
        mgr._nwc_configured = False
        mgr._nwc_relays = []
        mgr._nwc_private_key = None
        mgr._nwc_nwc_url = None
        mgr.events = []
        mgr.connected = False
        mgr.relay_manager = None

    def test_identical_subscription_is_not_republished(self):
        mgr = NostrManager.get_instance()
        mgr.connected = True
        fake = _FakeRelayManager()
        mgr.relay_manager = fake

        filters = Filters([Filter(kinds=[42], event_refs=["a" * 64])])
        mgr.add_subscription("test-channel", filters)
        first_publish_count = len(fake.published_messages)
        self.assertTrue(first_publish_count > 0, "First subscription should be published")

        # Calling again with the exact same filter must not publish another REQ.
        mgr.add_subscription("test-channel", filters)
        self.assertEqual(
            len(fake.published_messages),
            first_publish_count,
            "Identical subscription should not be re-published",
        )

    def test_changed_subscription_is_republished(self):
        mgr = NostrManager.get_instance()
        mgr.connected = True
        fake = _FakeRelayManager()
        mgr.relay_manager = fake

        filters1 = Filters([Filter(kinds=[42], event_refs=["a" * 64])])
        mgr.add_subscription("test-channel", filters1)
        first_publish_count = len(fake.published_messages)

        filter2 = Filter(kinds=[42], event_refs=["b" * 64])
        filters2 = Filters([filter2])
        mgr.add_subscription("test-channel", filters2)
        self.assertEqual(
            len(fake.published_messages),
            first_publish_count + 1,
            "Changed subscription should be re-published",
        )


if __name__ == "__main__":
    unittest.main()
