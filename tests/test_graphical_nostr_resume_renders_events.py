"""Graphical regression test for the Nostr chat list on resume.

When the Nostr app is reopened while NostrManager is already running, the
chat list should still render stored messages. This test pre-populates the
chat cache and verifies the chat list shows the message preview.
"""

import os
import shutil
import sys
import unittest

import lvgl as lv

sys.path.append("apps")

from com_micropythonos_nostr.chat_model import (
    DEFAULT_CHANNEL_ID,
    DEFAULT_CHANNEL_NAME,
    KIND_CHANNEL_MESSAGE,
    Message,
    channel_chat_id,
)
from com_micropythonos_nostr.event_store import EventStore

APP_FULLNAME = "com_micropythonos_nostr"
from com_micropythonos_nostr.nostr_service import NostrManager

from mpos import AppManager, wait_for_render
from mpos.ui.testing import click_label, find_label_with_text, wait_for_text

from nostr.event import Event


class TestNostrChatListResumeRendersEvents(unittest.TestCase):
    """Reopening Nostr should show stored channel events in the chat list."""

    def setUp(self):
        AppManager.restart_launcher()
        wait_for_render(5)

        # Clean up any stale chat cache.
        cache_dir = f"prefs/{APP_FULLNAME}/cache"
        try:
            for name in os.listdir(cache_dir):
                os.remove(f"{cache_dir}/{name}")
            os.rmdir(cache_dir)
        except OSError:
            pass

        # Start from a clean NostrManager singleton.
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

        # Pre-populate the store with a default-channel message.
        store = EventStore(APP_FULLNAME)
        store.get_or_create_channel(DEFAULT_CHANNEL_ID, title=DEFAULT_CHANNEL_NAME)
        message = Message(
            event_id="a" * 64,
            ts=1780516202,
            pubkey="b" * 64,
            content="Hello from regression test",
            kind=42,
        )
        store.add_message(channel_chat_id(DEFAULT_CHANNEL_ID), message, mark_unread=False)
        store.flush_index()
        wait_for_render(5)

    def tearDown(self):
        try:
            from mpos import ui

            ui.remove_and_stop_all_activities()
            wait_for_render(5)
        except Exception:
            pass

    def test_resumed_app_renders_stored_event(self):
        result = AppManager.start_app("com_micropythonos_nostr")
        self.assertTrue(result, "Nostr app should start")
        wait_for_render(10)

        # Poll briefly for the chat list row to appear.
        wait_for_text("Hello from regression test", timeout=20)
        found = find_label_with_text(lv.screen_active(), "Hello from regression test")
        self.assertIsNotNone(
            found,
            "Chat list should show the stored channel event preview",
        )

    def test_opening_default_channel_chat_works(self):
        result = AppManager.start_app("com_micropythonos_nostr")
        self.assertTrue(result, "Nostr app should start")
        wait_for_render(10)
        wait_for_text("Hello from regression test", timeout=20)

        # Click the default channel row. LVGL list buttons hold the text on the
        # button itself, so click_label (which does not require a child label) is
        # more reliable here than click_button.
        clicked = click_label("MicroPythonOS", timeout=10)
        self.assertTrue(clicked, "Should click the default channel row")
        wait_for_render(10)

        # The chat activity should show the title and the message history.
        self.assertIsNotNone(
            find_label_with_text(lv.screen_active(), "MicroPythonOS"),
            "Chat screen should show the channel title",
        )
        self.assertIsNotNone(
            find_label_with_text(lv.screen_active(), "Hello from regression test"),
            "Chat screen should show the stored message",
        )

    def test_incoming_channel_message_renders_in_open_chat(self):
        result = AppManager.start_app("com_micropythonos_nostr")
        self.assertTrue(result, "Nostr app should start")
        wait_for_render(10)
        wait_for_text("Hello from regression test", timeout=20)

        clicked = click_label("MicroPythonOS", timeout=10)
        self.assertTrue(clicked, "Should click the default channel row")
        wait_for_render(10)

        # Simulate an incoming kind-42 event for the default channel.
        event = Event(
            content="Incoming live message",
            public_key="c" * 64,
            kind=KIND_CHANNEL_MESSAGE,
            tags=[["e", DEFAULT_CHANNEL_ID, "", "root"]],
        )
        event.__post_init__()
        NostrManager.get_instance()._process_event(event)
        wait_for_render(10)

        self.assertIsNotNone(
            find_label_with_text(lv.screen_active(), "Incoming live message"),
            "Open chat should render the incoming channel message",
        )


class TestNostrFirstOpenShowsDefaultChannel(unittest.TestCase):
    """A brand new Nostr install should list the default public channel."""

    def setUp(self):
        AppManager.restart_launcher()
        wait_for_render(5)

        # Simulate a fresh install by wiping the app's prefs directory and
        # dropping any in-memory EventStore singleton.
        try:
            shutil.rmtree(f"prefs/{APP_FULLNAME}")
        except OSError:
            pass
        EventStore._instances.clear()

        # Reset NostrManager so each test starts from the same state.
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

    def tearDown(self):
        try:
            from mpos import ui

            ui.remove_and_stop_all_activities()
            wait_for_render(5)
        except Exception:
            pass

    def test_default_channel_visible_on_first_open(self):
        result = AppManager.start_app(APP_FULLNAME)
        self.assertTrue(result, "Nostr app should start")
        wait_for_render(10)
        self.assertTrue(
            wait_for_text("MicroPythonOS", timeout=20),
            "Default public channel should appear on first open",
        )


if __name__ == "__main__":
    unittest.main()
