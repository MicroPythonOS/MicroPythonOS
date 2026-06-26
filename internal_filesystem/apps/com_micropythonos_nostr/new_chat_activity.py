import logging

import lvgl as lv

from mpos import Activity, DisplayMetrics, Intent, MposKeyboard

from .chat_activity import ChatActivity
from .chat_model import KIND_CHANNEL_MESSAGE, KIND_DM
from .event_store import EventStore
from .nostr_service import NostrManager

logger = logging.getLogger(__name__)


class NewChatActivity(Activity):

    _mode = KIND_DM

    # UI
    _screen = None
    _textarea = None
    _keyboard = None
    _error_label = None

    def onCreate(self):
        self._store = EventStore(self.appFullName)
        self._manager = NostrManager.get_instance()
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

        title = lv.label(header)
        title.set_text("New chat")
        title.set_style_text_font(lv.font_montserrat_18, lv.PART.MAIN)

        mode_label = lv.label(self._screen)
        mode_label.set_text("Mode:")
        mode_label.set_style_text_font(lv.font_montserrat_14, lv.PART.MAIN)

        mode_row = lv.obj(self._screen)
        mode_row.set_width(lv.pct(100))
        mode_row.set_height(lv.SIZE_CONTENT)
        mode_row.set_style_border_width(0, lv.PART.MAIN)
        mode_row.set_flex_flow(lv.FLEX_FLOW.ROW)

        dm_btn = lv.button(mode_row)
        dm_btn.set_size(lv.pct(45), lv.SIZE_CONTENT)
        dm_lbl = lv.label(dm_btn)
        dm_lbl.set_text("DM")
        dm_lbl.center()
        dm_btn.add_event_cb(lambda e: self._set_mode(KIND_DM), lv.EVENT.CLICKED, None)

        chan_btn = lv.button(mode_row)
        chan_btn.set_size(lv.pct(45), lv.SIZE_CONTENT)
        chan_lbl = lv.label(chan_btn)
        chan_lbl.set_text("Channel")
        chan_lbl.center()
        chan_btn.add_event_cb(lambda e: self._set_mode(KIND_CHANNEL_MESSAGE), lv.EVENT.CLICKED, None)

        hint = lv.label(self._screen)
        hint.set_text("Enter npub (DM) or channel id")
        hint.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)

        self._textarea = lv.textarea(self._screen)
        self._textarea.set_one_line(True)
        self._textarea.set_width(lv.pct(100))
        self._textarea.set_placeholder_text("npub1... or hex channel id")
        self._textarea.set_max_length(200)

        self._keyboard = MposKeyboard(self._screen)
        self._keyboard.add_flag(lv.obj.FLAG.HIDDEN)
        self._keyboard.set_textarea(self._textarea)

        self._error_label = lv.label(self._screen)
        self._error_label.set_text("")
        self._error_label.set_style_text_color(lv.color_hex(0xFF0000), lv.PART.MAIN)
        self._error_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self._error_label.set_width(lv.pct(95))

        save_btn = lv.button(self._screen)
        save_btn.set_width(lv.pct(100))
        save_btn.set_height(lv.SIZE_CONTENT)
        save_lbl = lv.label(save_btn)
        save_lbl.set_text("Start chat")
        save_lbl.center()
        save_btn.add_event_cb(lambda e: self._start_chat(), lv.EVENT.CLICKED, None)

        self.setContentView(self._screen)

    def _set_mode(self, mode):
        self._mode = mode
        if mode == KIND_DM:
            self._textarea.set_placeholder_text("npub1...")
        else:
            self._textarea.set_placeholder_text("channel id (hex)")

    def _start_chat(self):
        raw = self._textarea.get_text().strip()
        if not raw:
            return

        if self._mode == KIND_DM:
            peer_pubkey = self._parse_npub(raw)
            if peer_pubkey is None:
                self._error_label.set_text("Invalid npub")
                return
            own = self._manager.get_own_pubkey_hex() or ""
            chat = self._store.get_or_create_dm(own, peer_pubkey)
        else:
            channel_id = raw.lower().strip()
            if len(channel_id) != 64 or not all(c in "0123456789abcdef" for c in channel_id):
                self._error_label.set_text("Channel id must be 64 hex chars")
                return
            chat = self._store.get_or_create_channel(channel_id)

        self._store.flush_index()
        intent = Intent(activity_class=ChatActivity)
        intent.putExtra("chat_id", chat.chat_id)
        intent.putExtra("kind", chat.kind)
        if chat.kind == KIND_CHANNEL_MESSAGE:
            intent.putExtra("channel_id", chat.channel_id)
        else:
            intent.putExtra("peer_pubkey", chat.peer_pubkey)
        self.startActivity(intent)
        self.finish()

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
