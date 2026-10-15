"""Graphical test: creating a NIP-17 private group from the Nostr "New chat" screen.

Opens the Nostr app, taps "+", switches to the "Group" mode, fills in the
member list and the subject, and checks that the group chat opens with the
subject as its title and is stored with the sorted member list. A second
test checks the member cap error message.
"""

import gc
import os
import sys
import time
import unittest

import lvgl as lv

sys.path.append("apps")
sys.path.append("tests")

from com_micropythonos_nostr.chat_model import (
    KIND_NIP17_CHAT,
    MAX_GROUP_MEMBERS,
    nip17_group_chat_id,
)
from com_micropythonos_nostr.event_store import EventStore
from com_micropythonos_nostr.nostr_service import NostrManager

from mpos import AppManager, wait_for_render
from mpos.ui.testing import click_label, find_label_with_text, wait_for_text

from _mpos_device_unittest import patch_unittest_main

patch_unittest_main()

APP_FULLNAME = "com_micropythonos_nostr"

MEMBERS = ["c" * 64, "b" * 64, "d" * 64]


def _find_textareas(obj, found=None):
    if found is None:
        found = []
    try:
        if obj.get_class() == lv.textarea_class:
            found.append(obj)
    except Exception:
        pass
    try:
        count = obj.get_child_count()
    except Exception:
        return found
    for i in range(count):
        _find_textareas(obj.get_child(i), found)
    return found


def _textarea_with_placeholder(text):
    for ta in _find_textareas(lv.screen_active()):
        try:
            if text in ta.get_placeholder_text():
                return ta
        except Exception:
            pass
    return None


class TestNostrNewGroupChat(unittest.TestCase):
    """The 'Group' mode of NewChatActivity creates a NIP-17 room."""

    def setUp(self):
        from mpos import ui

        ui.remove_and_stop_all_activities()
        wait_for_render(5)

        mgr = NostrManager.get_instance()
        mgr.stop()
        wait_for_render(5)

        cache_dir = f"prefs/{APP_FULLNAME}/cache"
        try:
            for name in os.listdir(cache_dir):
                os.remove(f"{cache_dir}/{name}")
            os.rmdir(cache_dir)
        except OSError:
            pass
        EventStore._instances.clear()

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
        time.sleep(2)
        gc.collect()

    def tearDown(self):
        try:
            from mpos import ui

            ui.remove_and_stop_all_activities()
            wait_for_render(5)
        except Exception:
            pass

    def _open_group_mode(self):
        self.assertTrue(AppManager.start_app(APP_FULLNAME), "Nostr app should start")
        wait_for_render(10)
        self.assertTrue(wait_for_text("MicroPythonOS", timeout=20), "chat list should show")
        self.assertTrue(click_label(lv.SYMBOL.PLUS, timeout=10), "should tap the + button")
        wait_for_render(10)
        self.assertTrue(wait_for_text("New chat", timeout=10), "New chat screen should open")
        self.assertTrue(click_label("Group", timeout=10), "should tap the Group mode")
        wait_for_render(10)
        members = _textarea_with_placeholder("npub")
        subject = _textarea_with_placeholder("subject")
        self.assertIsNotNone(members, "Group mode should show a members input")
        self.assertIsNotNone(subject, "Group mode should show a subject input")
        return members, subject

    def test_group_mode_creates_chat_titled_by_subject(self):
        members, subject = self._open_group_mode()
        members.set_text("%s,\n%s, %s" % (MEMBERS[0], MEMBERS[1], MEMBERS[2]))
        subject.set_text("Weekend plans")
        wait_for_render(5)
        self.assertTrue(click_label("Create group", timeout=10), "should tap Create group")
        wait_for_render(10)

        self.assertTrue(
            wait_for_text("Weekend plans", timeout=10),
            "the group chat should open with the subject as its title",
        )
        self.assertIsNotNone(
            find_label_with_text(lv.screen_active(), "Send"),
            "the chat screen (with its Send button) should be open",
        )

        store = EventStore(APP_FULLNAME)
        chat = store.get_chat(nip17_group_chat_id(MEMBERS))
        self.assertIsNotNone(chat, "the group chat should be stored")
        self.assertEqual(chat.kind, KIND_NIP17_CHAT)
        self.assertEqual(chat.participants, sorted(MEMBERS))
        self.assertEqual(chat.subject, "Weekend plans")
        self.assertEqual(chat.title, "Weekend plans")

    def test_group_mode_rejects_more_than_max_members(self):
        members, subject = self._open_group_mode()
        too_many = [("%02x" % i) * 32 for i in range(1, MAX_GROUP_MEMBERS + 2)]
        members.set_text(",".join(too_many))
        wait_for_render(5)
        self.assertTrue(click_label("Create group", timeout=10), "should tap Create group")
        wait_for_render(10)
        self.assertTrue(
            wait_for_text("at most %d people" % (MAX_GROUP_MEMBERS + 1), timeout=10),
            "the member cap should be explained on screen",
        )
        self.assertIsNotNone(find_label_with_text(lv.screen_active(), "New chat"))

    def test_switching_fields_does_not_stack_keyboard_handlers(self):
        # MposKeyboard.set_textarea() hooks a textarea's CLICKED once; tapping
        # members, subject and members again must not add handlers (each
        # extra one would show the keyboard again per tap).
        members, subject = self._open_group_mode()
        # First taps: the keyboard hooks each field once.
        for ta in (members, subject, members):
            ta.send_event(lv.EVENT.CLICKED, None)
            wait_for_render(3)
        members_before = members.get_event_count()
        subject_before = subject.get_event_count()
        for ta in (subject, members, subject, members):
            ta.send_event(lv.EVENT.CLICKED, None)
            wait_for_render(3)
        self.assertEqual(members.get_event_count(), members_before)
        self.assertEqual(subject.get_event_count(), subject_before)
        # And the mode switch that re-targets the keyboard does not either.
        self.assertTrue(click_label("DM", timeout=10))
        wait_for_render(5)
        self.assertTrue(click_label("Group", timeout=10))
        wait_for_render(5)
        self.assertEqual(members.get_event_count(), members_before)


if __name__ == "__main__":
    unittest.main()
