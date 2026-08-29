"""Test only the first-open case"""
import gc
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


class TestNostrFirstOpenShowsDefaultChannel(unittest.TestCase):
    """A brand new Nostr install should list the default public channel."""

    def setUp(self):
        # Match the manual test order that worked: restart launcher FIRST,
        # then wipe prefs and reset NostrManager.
        AppManager.restart_launcher()
        wait_for_render(10)

        # Wipe prefs with a delay to let any timer callbacks settle
        import time
        time.sleep(2)
        gc.collect()
        try:
            shutil.rmtree(f"prefs/{APP_FULLNAME}")
        except OSError:
            pass
        time.sleep(2)
        gc.collect()
        EventStore._instances.clear()
        time.sleep(1)
        gc.collect()

        # Final NostrManager reset
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
        wait_for_render(5)

    def tearDown(self):
        try:
            from mpos import ui
            ui.remove_and_stop_all_activities()
            wait_for_render(5)
        except Exception:
            pass

    def test_default_channel_visible_on_first_open(self):
        gc.collect()
        result = AppManager.start_app(APP_FULLNAME)
        self.assertTrue(result, "Nostr app should start")
        wait_for_render(10)
        self.assertTrue(
            wait_for_text("MicroPythonOS", timeout=20),
            "Default public channel should appear on first open",
        )

if __name__ == "__main__":
    unittest.main()
