import logging
import time as _time

import lvgl as lv

from mpos import Activity, DisplayMetrics, Intent, MposKeyboard

from .chat_activity import ChatActivity
from .chat_model import KIND_CHANNEL_MESSAGE, KIND_NIP17_CHAT
from .event_store import EventStore
from .nostr_initializer import search_channel_directory
from .nostr_service import NostrManager

logger = logging.getLogger(__name__)

MODE_DM = 0
MODE_JOIN_CHANNEL = 1
MODE_CREATE_CHANNEL = 2

_SEARCH_REFRESH_MS = 500
_SEARCH_TIMEOUT_S = 6


class NewChatActivity(Activity):

    _mode = MODE_DM

    _screen = None
    _textarea = None
    _keyboard = None
    _error_label = None
    _hint_label = None
    _action_btn = None
    _action_btn_label = None
    _results_list = None
    _search_sub_name = None
    _search_results = None
    _search_timer = None
    _search_start_time = 0

    def onCreate(self):
        self._store = EventStore(self.appFullName)
        self._manager = NostrManager.get_instance()
        self._setup_ui()
        self._update_for_mode()

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
        back_btn.add_event_cb(lambda e: self._cleanup_and_finish(), lv.EVENT.CLICKED, None)

        title = lv.label(header)
        title.set_text("New chat")
        title.set_style_text_font(lv.font_montserrat_18, lv.PART.MAIN)

        spacer = lv.obj(header)
        spacer.set_size(DisplayMetrics.pct_of_width(12), DisplayMetrics.pct_of_width(12))
        spacer.set_style_border_width(0, lv.PART.MAIN)

        mode_label = lv.label(self._screen)
        mode_label.set_text("Mode:")
        mode_label.set_style_text_font(lv.font_montserrat_14, lv.PART.MAIN)

        mode_row = lv.obj(self._screen)
        mode_row.set_width(lv.pct(100))
        mode_row.set_height(lv.SIZE_CONTENT)
        mode_row.set_style_border_width(0, lv.PART.MAIN)
        mode_row.set_flex_flow(lv.FLEX_FLOW.ROW)

        self._make_mode_btn(mode_row, "DM", MODE_DM)
        self._make_mode_btn(mode_row, "Join Ch.", MODE_JOIN_CHANNEL)
        self._make_mode_btn(mode_row, "Create Ch.", MODE_CREATE_CHANNEL)

        self._hint_label = lv.label(self._screen)
        self._hint_label.set_text("")
        self._hint_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)

        self._textarea = lv.textarea(self._screen)
        self._textarea.set_one_line(True)
        self._textarea.set_width(lv.pct(100))
        self._textarea.set_max_length(200)

        self._keyboard = MposKeyboard(self._screen)
        self._keyboard.add_flag(lv.obj.FLAG.HIDDEN)
        self._keyboard.set_textarea(self._textarea)

        self._error_label = lv.label(self._screen)
        self._error_label.set_text("")
        self._error_label.set_style_text_color(lv.color_hex(0xFF0000), lv.PART.MAIN)
        self._error_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self._error_label.set_width(lv.pct(95))

        self._results_list = lv.list(self._screen)
        self._results_list.set_width(lv.pct(100))
        self._results_list.set_flex_grow(1)
        self._results_list.add_flag(lv.obj.FLAG.HIDDEN)

        self._action_btn = lv.button(self._screen)
        self._action_btn.set_width(lv.pct(100))
        self._action_btn.set_height(lv.SIZE_CONTENT)
        self._action_btn_label = lv.label(self._action_btn)
        self._action_btn_label.set_text("Start chat")
        self._action_btn_label.center()
        self._action_btn.add_event_cb(lambda e: self._on_action(), lv.EVENT.CLICKED, None)

        self.setContentView(self._screen)

    def _make_mode_btn(self, parent, label, mode):
        btn = lv.button(parent)
        btn.set_size(lv.pct(30), lv.SIZE_CONTENT)
        btn.set_flex_grow(1)
        lbl = lv.label(btn)
        lbl.set_text(label)
        lbl.center()
        btn.add_event_cb(lambda e, m=mode: self._set_mode(m), lv.EVENT.CLICKED, None)
        return btn

    def _set_mode(self, mode):
        if self._mode == mode:
            return
        self._cleanup_search()
        self._mode = mode
        self._textarea.set_text("")
        self._error_label.set_text("")
        self._results_list.add_flag(lv.obj.FLAG.HIDDEN)
        self._results_list.clean()
        self._update_for_mode()

    def _update_for_mode(self):
        if self._mode == MODE_DM:
            self._hint_label.set_text("Enter npub(s) comma-separated")
            self._textarea.set_placeholder_text("npub1...")
            self._action_btn_label.set_text("Start chat")
        elif self._mode == MODE_JOIN_CHANNEL:
            self._hint_label.set_text("Channel name or hex id")
            self._textarea.set_placeholder_text("name or hex channel id")
            self._action_btn_label.set_text("Search")
        else:
            self._hint_label.set_text("Enter a name for the new channel")
            self._textarea.set_placeholder_text("channel name")
            self._action_btn_label.set_text("Create channel")

    def _on_action(self):
        raw = self._textarea.get_text().strip()
        if not raw:
            return
        if self._mode == MODE_DM:
            self._start_dm(raw)
        elif self._mode == MODE_JOIN_CHANNEL:
            self._join_channel(raw)
        else:
            self._create_channel(raw)

    def _start_dm(self, raw):
        pubkeys = self._parse_pubkeys(raw)
        if pubkeys is None:
            self._error_label.set_text("Invalid npub(s)")
            return
        own = self._manager.get_own_pubkey_hex() or ""
        if len(pubkeys) == 1:
            chat = self._store.get_or_create_dm(own, pubkeys[0])
        else:
            chat = self._store.get_or_create_nip17_group(pubkeys)
        self._navigate_to_chat(chat)

    def _join_channel(self, raw):
        lower = raw.lower().strip()
        if len(lower) == 64 and all(c in "0123456789abcdef" for c in lower):
            chat = self._store.get_or_create_channel(lower)
            self._navigate_to_chat(chat)
            return

        self._error_label.set_text("Searching...")
        self._search_results = []
        self._results_list.clean()

        local = search_channel_directory(raw)
        for cid, name, about in local:
            self._search_results.append((cid, name, about))

        self._results_list.remove_flag(lv.obj.FLAG.HIDDEN)
        self._show_search_results()

        try:
            self._search_sub_name = self._manager.search_channels(
                raw,
                lambda cid, name, about: self._on_search_result(cid, name, about),
            )
        except Exception as e:
            logger.warning("channel search failed: %s", e)

        self._search_start_time = _time.time()
        self._search_timer = lv.timer_create(
            lambda t: self._search_timer_cb(), _SEARCH_REFRESH_MS, None
        )

    def _on_search_result(self, channel_id, name, about):
        for i, (cid, _, _) in enumerate(self._search_results):
            if cid == channel_id:
                return
        self._search_results.append((channel_id, name, about))

    def _search_timer_cb(self):
        elapsed = _time.time() - self._search_start_time
        if elapsed >= _SEARCH_TIMEOUT_S or not self._search_sub_name:
            self._cleanup_search()
            if not self._search_results:
                self._error_label.set_text("No channels found")
            return
        self._show_search_results()

    def _show_search_results(self):
        self._results_list.clean()
        if not self._search_results:
            btn = self._results_list.add_button(None, "Searching...")
            btn.add_state(lv.STATE.DISABLED)
            return
        for cid, name, about in self._search_results:
            text = f"{name}\n{about}" if about else name
            btn = self._results_list.add_button(None, text)
            btn.add_event_cb(lambda e, c=cid, n=name: self._join_result(c, n), lv.EVENT.CLICKED, None)

    def _join_result(self, channel_id, name):
        chat = self._store.get_or_create_channel(channel_id, title=name)
        self._navigate_to_chat(chat)

    def _create_channel(self, raw):
        name = raw.strip()
        if not name:
            return
        if self._action_btn.has_state(lv.STATE.DISABLED):
            return
        self._action_btn_label.set_text("Creating...")
        self._action_btn.add_state(lv.STATE.DISABLED)
        try:
            channel_id = self._manager.publish_channel_creation(name)
            self._manager.publish_channel_metadata(channel_id, name)
            chat = self._store.get_or_create_channel(channel_id, title=name)
            self._navigate_to_chat(chat)
        except Exception as e:
            logger.error("channel creation failed: %s", e)
            self._error_label.set_text("Creation failed")
            self._action_btn_label.set_text("Create channel")
            self._action_btn.remove_state(lv.STATE.DISABLED)

    def _navigate_to_chat(self, chat):
        self._store.flush_index()
        intent = Intent(activity_class=ChatActivity)
        intent.putExtra("chat_id", chat.chat_id)
        intent.putExtra("kind", chat.kind)
        if chat.kind == KIND_CHANNEL_MESSAGE:
            intent.putExtra("channel_id", chat.channel_id)
        elif chat.kind == KIND_NIP17_CHAT:
            intent.putExtra("peer_pubkey", chat.peer_pubkey or (chat.participants[0] if chat.participants else ""))
        else:
            intent.putExtra("peer_pubkey", chat.peer_pubkey)
        self.startActivity(intent)
        self.finish()

    def _cleanup_search(self):
        if self._search_sub_name:
            try:
                self._manager.close_subscription(self._search_sub_name)
            except Exception:
                pass
            self._search_sub_name = None
        if self._search_timer is not None:
            try:
                self._search_timer.delete()
            except Exception:
                pass
            self._search_timer = None

    def _cleanup_and_finish(self):
        self._cleanup_search()
        self.finish()

    def onDestroy(self, screen):
        self._cleanup_search()

    def _parse_npub(self, text):
        text = text.strip()
        if text.startswith("npub1"):
            try:
                from nostr.key import PublicKey

                return PublicKey.from_npub(text).hex()
            except Exception as e:
                logger.warning("npub parse failed: %s", e)
                return None
        if len(text) == 64 and all(c in "0123456789abcdef" for c in text):
            return text
        return None

    def _parse_pubkeys(self, text):
        parts = [p.strip() for p in text.split(",") if p.strip()]
        pubkeys = []
        for part in parts:
            pk = self._parse_npub(part)
            if pk is None:
                return None
            pubkeys.append(pk)
        return pubkeys if pubkeys else None
