import logging

import lvgl as lv

from mpos import (
    Activity,
    ConnectivityManager,
    DisplayMetrics,
    MposKeyboard,
    SharedPreferences,
)

from chat_model import KIND_CHANNEL_MESSAGE, KIND_DM, Message
from constants import (
    DEFAULT_RELAYS,
    LOOKBACK_WINDOW_SECONDS,
    OVERLAP_SECONDS,
    SUBSCRIPTION_LIMIT_INITIAL,
)
from event_store import EventStore, _current_nostr_ts
from nostr_service import NostrManager

logger = logging.getLogger(__name__)


class ChatActivity(Activity):

    _chat_id = None
    _kind = None
    _peer_pubkey = None
    _channel_id = None
    _title = None

    # UI
    _screen = None
    _title_label = None
    _messages_container = None
    _input_textarea = None
    _keyboard = None
    _send_btn = None

    # State
    _manager = None
    _store = None
    _prefs = None
    _handler_registered = False
    _rendered_ids = None

    def onCreate(self):
        self._prefs = SharedPreferences(self.appFullName)
        self._store = EventStore(self.appFullName)
        self._manager = NostrManager.get_instance()

        extras = self.getIntent().extras or {}
        self._chat_id = extras.get("chat_id")
        self._kind = extras.get("kind", KIND_DM)
        self._peer_pubkey = extras.get("peer_pubkey")
        self._channel_id = extras.get("channel_id")
        self._title = extras.get("title")

        if self._chat_id is None:
            if self._kind == KIND_CHANNEL_MESSAGE and self._channel_id:
                from chat_model import channel_chat_id
                self._chat_id = channel_chat_id(self._channel_id)
            elif self._peer_pubkey:
                from chat_model import dm_chat_id
                own = self._manager.get_own_pubkey_hex() or ""
                self._chat_id = dm_chat_id(own, self._peer_pubkey)

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

        back_btn = lv.button(header)
        back_btn.set_size(DisplayMetrics.pct_of_width(12), DisplayMetrics.pct_of_width(12))
        back_lbl = lv.label(back_btn)
        back_lbl.set_text(lv.SYMBOL.LEFT)
        back_lbl.center()
        back_btn.add_event_cb(lambda e: self.finish(), lv.EVENT.CLICKED, None)

        self._title_label = lv.label(header)
        self._title_label.set_text(self._title or self._chat_id or "Chat")
        self._title_label.set_style_text_font(lv.font_montserrat_18, lv.PART.MAIN)

        self._messages_container = lv.obj(self._screen)
        self._messages_container.set_width(lv.pct(100))
        self._messages_container.set_flex_grow(1)
        self._messages_container.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self._messages_container.set_style_pad_all(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
        self._messages_container.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

        input_row = lv.obj(self._screen)
        input_row.set_width(lv.pct(100))
        input_row.set_height(lv.SIZE_CONTENT)
        input_row.set_style_border_width(0, lv.PART.MAIN)
        input_row.set_style_pad_all(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
        input_row.set_flex_flow(lv.FLEX_FLOW.ROW)
        input_row.set_style_flex_main_place(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.PART.MAIN)

        self._input_textarea = lv.textarea(input_row)
        self._input_textarea.set_one_line(True)
        self._input_textarea.set_width(lv.pct(75))
        self._input_textarea.set_placeholder_text("Type a message...")
        self._input_textarea.set_max_length(280)

        self._send_btn = lv.button(input_row)
        self._send_btn.set_size(lv.SIZE_CONTENT, lv.SIZE_CONTENT)
        send_lbl = lv.label(self._send_btn)
        send_lbl.set_text("Send")
        send_lbl.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
        send_lbl.center()
        self._send_btn.add_event_cb(lambda e: self._send(), lv.EVENT.CLICKED, None)

        self._keyboard = MposKeyboard(self._screen)
        self._keyboard.add_flag(lv.obj.FLAG.HIDDEN)
        self._keyboard.set_textarea(self._input_textarea)

        self.setContentView(self._screen)

    def onResume(self, screen):
        super().onResume(screen)
        self._register_handler()
        self._start_subscriptions()
        self._load_and_render()
        # Mark this chat as read while it is open.
        chat = self._store.get_chat(self._chat_id)
        if chat is not None and chat.unread:
            chat.mark_read()
            self._store.update_chat(chat)
            self._store.flush_index()

    def onPause(self, screen):
        self._unregister_handler()
        self._store.flush_index()

    def onDestroy(self, screen):
        self._unregister_handler()
        self._store.flush_index()

    def _register_handler(self):
        if self._handler_registered:
            return
        self._manager.register_event_handler(self._kind, self._on_event)
        self._handler_registered = True

    def _unregister_handler(self):
        if not self._handler_registered:
            return
        self._manager.unregister_event_handler(self._kind, self._on_event)
        self._handler_registered = False

    def _start_subscriptions(self):
        if not self._manager.is_running():
            self._manager.start()

        nsec = self._prefs.get_string("nostr_nsec")
        if nsec:
            relay = self._prefs.get_string("nostr_relay") or DEFAULT_RELAYS
            if not self._manager._nostr_configured:
                try:
                    self._manager.configure_identity(nsec, relays=relay)
                except Exception as e:
                    logger.error("Failed to configure identity: %s", e)
                    return

        if self._kind == KIND_CHANNEL_MESSAGE and self._channel_id:
            since = self._since_for_chat()
            try:
                self._manager.subscribe_channel(
                    self._channel_id,
                    name=self._chat_id,
                    since=since,
                    limit=SUBSCRIPTION_LIMIT_INITIAL,
                )
            except Exception as e:
                logger.error("Channel subscription failed: %s", e)

        # Always keep a DM subscription active so incoming DMs arrive.
        try:
            own = self._manager.get_own_pubkey_hex()
            chats = self._store.get_chats()
            dm_since = _current_nostr_ts() - LOOKBACK_WINDOW_SECONDS
            for chat in chats:
                if chat.kind == KIND_DM and chat.last_ts:
                    dm_since = min(dm_since, chat.last_ts - OVERLAP_SECONDS)
            self._manager.subscribe_dms(since=dm_since, limit=SUBSCRIPTION_LIMIT_INITIAL)
        except Exception as e:
            logger.error("DM subscription failed: %s", e)

    def _since_for_chat(self):
        chat = self._store.get_chat(self._chat_id)
        if chat is not None and chat.last_ts:
            return max(0, chat.last_ts - OVERLAP_SECONDS)
        return max(0, _current_nostr_ts() - LOOKBACK_WINDOW_SECONDS)

    def _load_and_render(self):
        self._messages_container.clean()
        self._rendered_ids = set()
        messages = self._store.load_messages(self._chat_id)
        chat = self._store.get_chat(self._chat_id)
        if chat is not None:
            if not self._title:
                self._title_label.set_text(chat.title)
        for msg in messages:
            self._append_message_row(msg)
        self._scroll_to_bottom()

    def _append_message_row(self, message):
        if self._rendered_ids is None:
            self._rendered_ids = set()
        self._rendered_ids.add(message.event_id)

        row = lv.obj(self._messages_container)
        row.set_width(lv.pct(100))
        row.set_height(lv.SIZE_CONTENT)
        row.set_style_border_width(0, lv.PART.MAIN)
        row.set_style_pad_bottom(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
        row.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        chat = self._store.get_chat(self._chat_id)
        sender = chat.sender_name(message) if chat else "?"
        if message.outgoing and message.queued:
            sender = f"{sender} (queued)"

        meta = lv.label(row)
        meta.set_text(f"{sender} · {self._format_time(message.ts)}")
        meta.set_style_text_font(lv.font_montserrat_10, lv.PART.MAIN)

        body = lv.label(row)
        body.set_text(message.content)
        body.set_width(lv.pct(100))
        body.set_long_mode(lv.label.LONG_MODE.WRAP)

    def _scroll_to_bottom(self):
        try:
            count = self._messages_container.get_child_count()
            if count > 0:
                self._messages_container.get_child(count - 1).scroll_to_view_recursive(
                    True
                )
        except Exception:
            pass

    def _format_time(self, ts):
        try:
            import time as _t
            t = _t.localtime(ts)
            return "{:02d}:{:02d}".format(t[3], t[4])
        except Exception:
            return ""

    def _send(self):
        text = self._input_textarea.get_text().strip()
        if not text:
            return

        online = ConnectivityManager.get().is_online() and self._manager.is_connected()
        own = self._manager.get_own_pubkey_hex() or ""

        if online:
            try:
                if self._kind == KIND_DM:
                    event_id = self._manager.publish_dm(self._peer_pubkey, text)
                else:
                    event_id = self._manager.publish_channel_message(self._channel_id, text)
                message = Message(
                    event_id=event_id,
                    ts=_current_nostr_ts(),
                    pubkey=own,
                    content=text,
                    kind=self._kind,
                    outgoing=True,
                    queued=False,
                )
                self._store.add_message(self._chat_id, message, mark_unread=False)
                self._append_message_row(message)
                self._scroll_to_bottom()
            except Exception as e:
                logger.error("Send failed: %s", e)
                self._queue_local_message(text, own)
        else:
            self._queue_local_message(text, own)

        self._input_textarea.set_text("")
        self._keyboard.add_flag(lv.obj.FLAG.HIDDEN)

    def _queue_local_message(self, text, own_pubkey):
        if self._kind == KIND_DM:
            message = self._store.queue_outgoing(
                self._chat_id,
                text,
                KIND_DM,
                recipient_pubkey=self._peer_pubkey,
            )
        else:
            message = self._store.queue_outgoing(
                self._chat_id,
                text,
                KIND_CHANNEL_MESSAGE,
                channel_id=self._channel_id,
            )
        if message is not None:
            self._append_message_row(message)
            self._scroll_to_bottom()

    def _on_event(self, nostr_event):
        try:
            from chat_model import chat_id_for_event
            own = self._manager.get_own_pubkey_hex()
            chat_id = chat_id_for_event(nostr_event.event, own)
            if chat_id != self._chat_id:
                return

            if self._kind == KIND_DM:
                content = nostr_event.get_display_content()
            else:
                content = nostr_event.content

            message = Message(
                event_id=nostr_event.event.id,
                ts=nostr_event.created_at,
                pubkey=nostr_event.public_key,
                content=content,
                kind=self._kind,
            )
            # Persist if not already stored; render regardless, because
            # ChatListActivity may have stored this event before our handler runs.
            self._store.add_message(self._chat_id, message, mark_unread=False)
            if message.event_id not in self._rendered_ids:
                self._append_message_row(message)
                self._scroll_to_bottom()
        except Exception as e:
            logger.error("Error handling chat event: %s", e)
