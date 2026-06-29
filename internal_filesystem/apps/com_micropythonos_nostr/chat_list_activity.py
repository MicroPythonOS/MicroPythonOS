import logging

import lvgl as lv

from mpos import (
    Activity,
    ConnectivityManager,
    DisplayMetrics,
    FontManager,
    Intent,
    SettingsActivity,
    SharedPreferences,
)

from .chat_activity import ChatActivity
from .chat_notifications import post_chat_notification
from .chat_model import (
    DEFAULT_CHANNEL_ID,
    DEFAULT_CHANNEL_NAME,
    DEFAULT_DM_PROTOCOL,
    KIND_CHANNEL_MESSAGE,
    KIND_DM,
    KIND_NIP17_CHAT,
    Message,
    channel_chat_id,
    channel_id_from_event,
    chat_id_for_event,
    participants_from_nip17_event,
    peer_from_dm_event,
    subject_from_nip17_event,
)
from .event_store import DEFAULT_MAX_MESSAGES_PER_CHAT, EventStore, _current_nostr_ts
from .new_chat_activity import NewChatActivity
from .nostr_initializer import DEFAULT_RELAY, configure_nostr_manager
from .nostr_service import NostrManager
from .show_npub_qr import ShowNpubQRActivity

logger = logging.getLogger(__name__)

# Index flush period (milliseconds).
INDEX_FLUSH_MS = 5000


class ChatListActivity(Activity):

    # UI widgets
    _screen = None
    _status_label = None
    _chat_list = None
    _new_btn = None
    _settings_btn = None

    # State
    _manager = None
    _store = None
    _prefs = None
    _handlers_registered = False
    _flush_timer = None
    _connectivity_cb = None

    def onCreate(self):
        self._prefs = SharedPreferences(self.appFullName)
        self._store = EventStore(self.appFullName)
        self._manager = NostrManager.get_instance()
        # Ensure the default public channel is joined before the UI is shown,
        # otherwise onResume/_refresh_chat_list runs during setContentView and
        # renders an empty list on first launch.
        self._auto_join_default_channel()
        self._setup_ui()

    def _setup_ui(self):
        self._screen = lv.obj()
        self._screen.set_style_pad_all(0, lv.PART.MAIN)
        self._screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        header = lv.obj(self._screen)
        header.set_width(lv.pct(100))
        header.set_height(lv.SIZE_CONTENT)
        header.set_style_pad_all(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
        header.set_flex_flow(lv.FLEX_FLOW.ROW)
        header.set_style_flex_main_place(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.PART.MAIN)
        header.set_style_border_width(0, lv.PART.MAIN)

        title = lv.label(header)
        title.set_text("Nostr")
        title.set_style_text_font(lv.font_montserrat_18, lv.PART.MAIN)

        self._status_label = lv.label(header)
        self._status_label.set_text(lv.SYMBOL.REFRESH)

        self._new_btn = lv.button(header)
        self._new_btn.set_size(DisplayMetrics.pct_of_width(12), DisplayMetrics.pct_of_width(12))
        new_lbl = lv.label(self._new_btn)
        new_lbl.set_text(lv.SYMBOL.PLUS)
        new_lbl.center()
        self._new_btn.add_event_cb(lambda e: self._new_chat(), lv.EVENT.CLICKED, None)

        self._settings_btn = lv.button(header)
        self._settings_btn.set_size(DisplayMetrics.pct_of_width(12), DisplayMetrics.pct_of_width(12))
        set_lbl = lv.label(self._settings_btn)
        set_lbl.set_text(lv.SYMBOL.SETTINGS)
        set_lbl.center()
        self._settings_btn.add_event_cb(lambda e: self._settings(), lv.EVENT.CLICKED, None)

        self._chat_list = lv.list(self._screen)
        self._chat_list.set_width(lv.pct(100))
        self._chat_list.set_flex_grow(1)

        self.setContentView(self._screen)

    def onResume(self, screen):
        super().onResume(screen)
        self._sync_settings()
        self._register_handlers()
        self._connectivity_cb = self.network_changed
        ConnectivityManager.get().register_callback(self._connectivity_cb)
        self.network_changed(ConnectivityManager.get().is_online())
        self._start_manager_and_subscriptions()
        self._start_flush_timer()
        self._refresh_chat_list()

    def onPause(self, screen):
        # Keep event handlers registered so notifications work while paused.
        if self._connectivity_cb:
            ConnectivityManager.get().unregister_callback(self._connectivity_cb)
            self._connectivity_cb = None
        self._stop_flush_timer()
        self._store.flush_index()

    def onDestroy(self, screen):
        self._unregister_handlers()
        self._stop_flush_timer()
        self._store.flush_index()

    def _register_handlers(self):
        if self._handlers_registered:
            return
        self._manager.register_event_handler(KIND_DM, self._on_event)
        self._manager.register_event_handler(KIND_CHANNEL_MESSAGE, self._on_event)
        self._manager.register_event_handler(KIND_NIP17_CHAT, self._on_event)
        self._handlers_registered = True

    def _unregister_handlers(self):
        if not self._handlers_registered:
            return
        self._manager.unregister_event_handler(KIND_DM, self._on_event)
        self._manager.unregister_event_handler(KIND_CHANNEL_MESSAGE, self._on_event)
        self._manager.unregister_event_handler(KIND_NIP17_CHAT, self._on_event)
        self._handlers_registered = False

    def _start_flush_timer(self):
        if self._flush_timer is not None:
            return
        try:
            self._flush_timer = lv.timer_create(
                lambda t: self._store.flush_index(), INDEX_FLUSH_MS, None
            )
        except Exception as e:
            logger.warning("Could not create index flush timer: %s", e)

    def _stop_flush_timer(self):
        if self._flush_timer is None:
            return
        try:
            self._flush_timer.delete()
        except Exception:
            pass
        self._flush_timer = None

    def network_changed(self, online):
        if online:
            self._status_label.set_text(lv.SYMBOL.WIFI)
            self._flush_outbox_if_online()
        else:
            self._status_label.set_text(lv.SYMBOL.CLOSE)

    def _start_manager_and_subscriptions(self):
        configure_nostr_manager(self._prefs, self._manager, store=self._store)
        self._flush_outbox_if_online()

    def _auto_join_default_channel(self):
        if not self._store.get_chat(channel_chat_id(DEFAULT_CHANNEL_ID)):
            self._store.get_or_create_channel(DEFAULT_CHANNEL_ID, title=f"#{DEFAULT_CHANNEL_NAME}")

    def _on_event(self, nostr_event):
        """Handle an incoming kind 4, kind 14, or kind 42 event."""
        try:
            own = self._manager.get_own_pubkey_hex()
            chat_id = chat_id_for_event(nostr_event.event, own)
            if chat_id is None:
                return

            kind = nostr_event.kind
            if kind in (KIND_DM, KIND_NIP17_CHAT):
                content = nostr_event.get_display_content()
            else:
                content = nostr_event.content

            message = Message(
                event_id=nostr_event.event.id,
                ts=nostr_event.created_at,
                pubkey=nostr_event.public_key,
                content=content,
                kind=kind,
            )

            # Ensure chat exists so metadata is available for notifications.
            chat = self._store.get_chat(chat_id)
            if chat is None:
                if kind == KIND_DM:
                    peer = peer_from_dm_event(nostr_event.event, own)
                    chat = self._store.get_or_create_dm(own, peer)
                elif kind == KIND_NIP17_CHAT:
                    participants = participants_from_nip17_event(
                        nostr_event.event, own
                    )
                    title = subject_from_nip17_event(nostr_event.event)
                    if len(participants) == 1:
                        chat = self._store.get_or_create_dm(own, participants[0])
                    else:
                        chat = self._store.get_or_create_nip17_group(
                            participants, title=title
                        )
                else:
                    channel_id = channel_id_from_event(nostr_event.event)
                    chat = self._store.get_or_create_channel(
                        channel_id or DEFAULT_CHANNEL_ID
                    )

            is_new = self._store.add_message(chat_id, message, mark_unread=True)
            if not is_new:
                return

            # If the user is already looking at this exact chat, don't bump
            # unread counts or notify.
            if ChatActivity.currently_open_chat_id == chat_id:
                chat.mark_read()
                self._store.update_chat(chat)
                if self.has_foreground():
                    self._refresh_chat_list()
                return

            if self.has_foreground():
                self._refresh_chat_list()

            self._post_notification(chat, message)
        except Exception as e:
            logger.error("Error handling Nostr event: %s", e)

    def _post_notification(self, chat, message):
        post_chat_notification(self.appFullName, chat, message)

    def _refresh_chat_list(self):
        self._chat_list.clean()
        chats = self._store.get_chats()
        now = _current_nostr_ts()
        visible = 0
        for chat in chats:
            # Hide empty DM chats that have never had any traffic.
            if chat.kind == KIND_DM and chat.last_ts == 0:
                continue
            text = self._format_chat_row(chat, now)
            btn = self._chat_list.add_button(None, text)
            btn.add_event_cb(lambda e, cid=chat.chat_id: self._open_chat(cid), lv.EVENT.CLICKED, None)
            lbl = btn.get_child(0)
            if lbl is not None:
                lbl.set_style_text_font(
                    FontManager.getFont(emoji=True), lv.PART.MAIN
                )
            # Highlight unread rows.
            if chat.unread:
                btn.add_state(lv.STATE.CHECKED)
            visible += 1
        if visible == 0:
            btn = self._chat_list.add_button(None, "No messages yet")
            btn.add_state(lv.STATE.DISABLED)

    def _format_chat_row(self, chat, now):
        title = chat.title
        preview = chat.last_preview or ""
        time_text = self._format_relative_time(now, chat.last_ts)
        unread = f" ({chat.unread})" if chat.unread else ""
        return f"{title}{unread}\n{preview}\n{time_text}"

    def _format_relative_time(self, now, ts):
        if not ts:
            return ""
        diff = now - ts
        if diff < 60:
            return "now"
        if diff < 3600:
            return f"{diff // 60}m"
        if diff < 86400:
            return f"{diff // 3600}h"
        return f"{diff // 86400}d"

    def _open_chat(self, chat_id):
        chat = self._store.get_chat(chat_id)
        if chat is None:
            return
        intent = Intent(activity_class=ChatActivity)
        intent.putExtra("chat_id", chat_id)
        intent.putExtra("kind", chat.kind)
        if chat.kind == KIND_CHANNEL_MESSAGE:
            intent.putExtra("channel_id", chat.channel_id)
        elif chat.kind == KIND_NIP17_CHAT:
            intent.putExtra("peer_pubkey", chat.peer_pubkey or chat.participants[0] if chat.participants else "")
        else:
            intent.putExtra("peer_pubkey", chat.peer_pubkey)
        self.startActivity(intent)

    def _new_chat(self):
        self.startActivity(Intent(activity_class=NewChatActivity))

    def _settings(self):
        intent = Intent(activity_class=SettingsActivity)
        intent.putExtra("prefs", self._prefs)
        intent.putExtra("settings", [
            {"title": "Nostr Private Key (nsec)", "key": "nostr_nsec", "placeholder": "nsec1...", "should_show": self._should_show_setting},
            {"title": "Nostr Relay", "key": "nostr_relay", "placeholder": DEFAULT_RELAY, "should_show": self._should_show_setting},
            {"title": "Connect at boot", "key": "connect_at_boot", "ui": "radiobuttons", "ui_options": [("On", "1"), ("Off", "0")], "default_value": "1", "should_show": self._should_show_setting},
            {"title": "Show My Public Key (npub)", "key": "show_npub_qr", "ui": "activity", "activity_class": ShowNpubQRActivity, "dont_persist": True, "should_show": self._should_show_setting},
            {"title": "New chats protocol", "key": "new_chats_protocol", "ui": "radiobuttons", "ui_options": [("nip17", "nip17"), ("nip4", "nip4")], "default_value": DEFAULT_DM_PROTOCOL, "should_show": self._should_show_setting},
            {"title": "Max messages per chat", "key": "max_messages_per_chat", "placeholder": "200", "should_show": self._should_show_setting},
        ])
        self.startActivity(intent)

    def _sync_settings(self):
        try:
            max_msgs = self._prefs.get_int("max_messages_per_chat", DEFAULT_MAX_MESSAGES_PER_CHAT)
            self._store.set_max_messages(max_msgs)
        except Exception as e:
            logger.warning("Could not sync settings: %s", e)

    def _should_show_setting(self, setting):
        return True

    def _flush_outbox_if_online(self):
        if not ConnectivityManager.get().is_online():
            return
        if not self._manager.is_connected():
            return
        items = self._store.load_outbox()
        if not items:
            return
        own = self._manager.get_own_pubkey_hex()
        for item in items:
            try:
                kind = item.get("kind")
                if kind == KIND_DM:
                    event_id = self._manager.publish_dm(
                        item["recipient_pubkey"], item["content"]
                    )
                elif kind == KIND_NIP17_CHAT:
                    participants = item.get("participants")
                    if not participants and item.get("recipient_pubkey"):
                        participants = [item["recipient_pubkey"]]
                    event_ids = self._manager.publish_nip17_message(
                        item["content"],
                        participants,
                        created_at=item.get("ts"),
                    )
                    event_id = event_ids[0]
                else:
                    event_id = self._manager.publish_channel_message(
                        item["channel_id"], item["content"]
                    )
                placeholder_id = item.get("placeholder_id")
                chat_id = item.get("chat_id")
                new_message = Message(
                    event_id=event_id,
                    ts=item.get("ts", _current_nostr_ts()),
                    pubkey=own or "",
                    content=item["content"],
                    kind=item["kind"],
                    outgoing=True,
                    queued=False,
                )
                self._store.replace_message(chat_id, placeholder_id, new_message)
            except Exception as e:
                logger.error("Failed to flush outbox item: %s", e)
                # Stop trying the rest until the next reconnect.
                return
        self._store.clear_outbox()
        if self.has_foreground():
            self._refresh_chat_list()
