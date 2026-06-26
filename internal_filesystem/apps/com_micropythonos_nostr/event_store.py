import logging
import os
import time as _time

try:
    import ujson as json
except ImportError:
    import json

from .chat_model import Chat, Message, channel_chat_id, dm_chat_id

logger = logging.getLogger(__name__)

# JSONL/index file layout under prefs/<app_fullname>/cache/.
CACHE_DIR = "cache"
INDEX_FILENAME = "index.json"
OUTBOX_FILENAME = "outbox.jsonl"
CHAT_FILE_SUFFIX = ".jsonl"
STORE_VERSION = 1

# Per-chat message store limits.
DEFAULT_MAX_MESSAGES_PER_CHAT = 200
MAX_MESSAGES_PER_CHAT_MIN = 10
MAX_MESSAGES_PER_CHAT_MAX = 2000


def _current_nostr_ts():
    """Return a Nostr-compatible Unix timestamp (handles ESP32 offset)."""
    try:
        from nostr.event import Event

        return Event.epoch_seconds()
    except Exception:
        return int(_time.time())


def _sanitize_chat_id(chat_id):
    """Keep chat ids filesystem-safe (hex and underscores are already safe)."""
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    return "".join(c for c in chat_id if c in allowed)


class EventStore:
    """Persistent but lightweight cache for decrypted Nostr chat messages.

    Incoming events are appended to per-chat JSONL files immediately.
    The lightweight chat index is batched in RAM and flushed on request.
    Outgoing messages that cannot be published immediately are written to an
    outbox file and retried when connectivity returns.
    """

    _instances = {}

    def __new__(cls, app_fullname):
        if app_fullname not in cls._instances:
            cls._instances[app_fullname] = super().__new__(cls)
        return cls._instances[app_fullname]

    def __init__(self, app_fullname):
        if getattr(self, "_loaded", False):
            return
        self._app_fullname = app_fullname
        self._prefs_dir = f"prefs/{app_fullname}"
        self._cache_dir = f"{self._prefs_dir}/{CACHE_DIR}"
        self._index = self._empty_index()
        self._index_dirty = False
        self._loaded = False
        self._known_ids = set()  # small in-memory dedup cache
        self._ensure_dirs()
        self._load_index()

    def _empty_index(self):
        return {
            "version": STORE_VERSION,
            "settings": {"max_messages_per_chat": DEFAULT_MAX_MESSAGES_PER_CHAT},
            "chats": {},
        }

    def _ensure_dirs(self):
        cache_existed = True
        for path in ("prefs", self._prefs_dir, self._cache_dir):
            try:
                os.stat(path)
            except OSError:
                if path == self._cache_dir:
                    cache_existed = False
                try:
                    os.mkdir(path)
                except OSError:
                    pass
        if not cache_existed:
            # Cache directory was recreated; in-memory dedup cache no longer
            # reflects persisted messages.
            self._known_ids = set()

    def _index_path(self):
        return f"{self._cache_dir}/{INDEX_FILENAME}"

    def _outbox_path(self):
        return f"{self._cache_dir}/{OUTBOX_FILENAME}"

    def _chat_path(self, chat_id):
        return f"{self._cache_dir}/{_sanitize_chat_id(chat_id)}{CHAT_FILE_SUFFIX}"

    def _load_index(self):
        path = self._index_path()
        try:
            with open(path, "r") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("version") == STORE_VERSION:
                self._index = data
            else:
                logger.warning("Discarding incompatible event store index")
                self._index = self._empty_index()
        except OSError:
            self._index = self._empty_index()
        except Exception as e:
            logger.error("Failed to load index: %s", e)
            self._index = self._empty_index()
        self._index_dirty = False
        self._rebuild_summaries()
        self._loaded = True

    def _rebuild_summaries(self):
        """Backfill last_ts/last_preview from JSONL files when index is stale.

        Messages are appended to per-chat JSONL files immediately, while the
        lightweight index is flushed periodically. After a hard reset the index
        may lag behind; rebuild summaries so the chat list shows DMs that have
        persisted history.
        """
        try:
            files = os.listdir(self._cache_dir)
        except OSError:
            return
        changed = False
        for name in files:
            if not name.endswith(CHAT_FILE_SUFFIX):
                continue
            chat_id = name[: -len(CHAT_FILE_SUFFIX)]
            entry = self._index.get("chats", {}).get(chat_id)
            if entry is None or entry.get("last_ts", 0):
                continue
            messages = self.load_messages(chat_id)
            if not messages:
                continue
            chat = Chat.from_dict(chat_id, entry)
            chat.update_from_message(messages[-1])
            self._index["chats"][chat_id] = chat.to_dict()
            changed = True
        if changed:
            self._index_dirty = True

    def flush_index(self):
        """Write the lightweight chat index to flash if it changed."""
        if not self._index_dirty:
            return True
        self._ensure_dirs()
        path = self._index_path()
        try:
            with open(path, "w") as f:
                json.dump(self._index, f)
            self._index_dirty = False
            return True
        except Exception as e:
            logger.error("Failed to flush index: %s", e)
            return False

    def _save_index(self):
        """Mark index dirty so it will be flushed by the next timer/pause."""
        self._index_dirty = True

    def _max_messages(self):
        value = self._index.get("settings", {}).get(
            "max_messages_per_chat", DEFAULT_MAX_MESSAGES_PER_CHAT
        )
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = DEFAULT_MAX_MESSAGES_PER_CHAT
        return max(MAX_MESSAGES_PER_CHAT_MIN, min(value, MAX_MESSAGES_PER_CHAT_MAX))

    def set_max_messages(self, value):
        """Update the per-chat message cap persisted in the index."""
        try:
            value = int(value)
        except (TypeError, ValueError):
            return
        value = max(MAX_MESSAGES_PER_CHAT_MIN, min(value, MAX_MESSAGES_PER_CHAT_MAX))
        if "settings" not in self._index:
            self._index["settings"] = {}
        if self._index["settings"].get("max_messages_per_chat") != value:
            self._index["settings"]["max_messages_per_chat"] = value
            self._save_index()

    def _chat_entry(self, chat_id):
        if "chats" not in self._index:
            self._index["chats"] = {}
        return self._index["chats"].setdefault(chat_id, {})

    def get_chat(self, chat_id):
        """Return a Chat object for the given id, or None."""
        entry = self._index.get("chats", {}).get(chat_id)
        if entry is None:
            return None
        return Chat.from_dict(chat_id, entry)

    def get_chats(self):
        """Return all known Chat objects sorted by last activity, newest first."""
        chats = [
            Chat.from_dict(cid, data)
            for cid, data in self._index.get("chats", {}).items()
        ]
        chats.sort(key=lambda c: c.last_ts, reverse=True)
        return chats

    def get_or_create_dm(self, own_pubkey, peer_pubkey):
        chat_id = dm_chat_id(own_pubkey, peer_pubkey)
        chat = self.get_chat(chat_id)
        if chat is None:
            chat = Chat.dm(own_pubkey, peer_pubkey)
            self._index["chats"][chat_id] = chat.to_dict()
            self._save_index()
        return chat

    def get_or_create_channel(self, channel_id, title=None):
        chat_id = channel_chat_id(channel_id)
        chat = self.get_chat(chat_id)
        if chat is None:
            chat = Chat.channel(channel_id, title=title)
            self._index["chats"][chat_id] = chat.to_dict()
            self._save_index()
        return chat

    def update_chat(self, chat):
        """Persist metadata changes for an existing Chat."""
        if chat.chat_id not in self._index.get("chats", {}):
            return
        self._index["chats"][chat.chat_id] = chat.to_dict()
        self._save_index()

    def load_messages(self, chat_id, limit=None):
        """Load messages for a chat, newest last, deduplicated by event id."""
        if limit is None:
            limit = self._max_messages()
        path = self._chat_path(chat_id)
        messages = []
        try:
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        messages.append(Message.from_dict(data))
                    except Exception as e:
                        if __debug__:
                            logger.debug("Skipping bad chat line: %s", e)
        except OSError:
            return []
        # Deduplicate by id; keep the latest occurrence.
        by_id = {}
        for msg in messages:
            existing = by_id.get(msg.event_id)
            if existing is None or msg.ts > existing.ts:
                by_id[msg.event_id] = msg
        messages = sorted(by_id.values(), key=lambda m: m.ts)
        if len(messages) > limit:
            messages = messages[-limit:]
        return messages

    def _append_jsonl(self, path, obj):
        self._ensure_dirs()
        with open(path, "a") as f:
            f.write(json.dumps(obj))
            f.write("\n")

    def _rewrite_jsonl(self, path, objs):
        self._ensure_dirs()
        with open(path, "w") as f:
            for obj in objs:
                f.write(json.dumps(obj.to_dict()))
                f.write("\n")

    def _add_known_id(self, event_id):
        self._known_ids.add(event_id)
        if len(self._known_ids) > 500:
            self._known_ids = set(list(self._known_ids)[-250:])

    def add_message(self, chat_id, message, mark_unread=False):
        """Persist an incoming message and update chat metadata.

        Returns True if the message was new, False if it was already known.
        """
        self._ensure_dirs()
        if not message.event_id:
            message.event_id = f"local:{chat_id}:{message.ts}"
        if message.event_id in self._known_ids:
            return False

        path = self._chat_path(chat_id)
        self._append_jsonl(path, message.to_dict())
        self._add_known_id(message.event_id)

        entry = self._chat_entry(chat_id)
        chat = Chat.from_dict(chat_id, entry)
        chat.update_from_message(message)
        if mark_unread:
            chat.increment_unread()
        entry.update(chat.to_dict())
        self._save_index()
        return True

    def prune_chat(self, chat_id):
        """Trim a chat file down to max_messages."""
        messages = self.load_messages(chat_id)
        limit = self._max_messages()
        if len(messages) > limit:
            messages = messages[-limit:]
            self._rewrite_jsonl(self._chat_path(chat_id), messages)

    def queue_outgoing(self, chat_id, content, kind, recipient_pubkey=None, channel_id=None):
        """Store an outgoing message that cannot be published right now.

        Returns the queued Message placeholder.
        """
        ts = _current_nostr_ts()
        placeholder_id = f"out:{chat_id}:{ts}"
        message = Message(
            event_id=placeholder_id,
            ts=ts,
            pubkey=recipient_pubkey or channel_id or "",
            content=content,
            kind=kind,
            outgoing=True,
            queued=True,
        )
        self.add_message(chat_id, message, mark_unread=False)

        outbox_item = {
            "placeholder_id": placeholder_id,
            "ts": ts,
            "chat_id": chat_id,
            "content": content,
            "kind": kind,
            "recipient_pubkey": recipient_pubkey,
            "channel_id": channel_id,
        }
        self._append_jsonl(self._outbox_path(), outbox_item)
        return message

    def load_outbox(self):
        """Return pending outgoing items as dicts."""
        path = self._outbox_path()
        items = []
        try:
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        items.append(json.loads(line))
                    except Exception as e:
                        if __debug__:
                            logger.debug("Skipping bad outbox line: %s", e)
        except OSError:
            pass
        return items

    def clear_outbox(self):
        """Remove all outbox items from disk."""
        path = self._outbox_path()
        try:
            os.remove(path)
        except OSError:
            pass

    def replace_message(self, chat_id, old_event_id, new_message):
        """Replace a placeholder message (e.g. queued) with a published one."""
        messages = self.load_messages(chat_id)
        found = False
        for i, msg in enumerate(messages):
            if msg.event_id == old_event_id:
                messages[i] = new_message
                found = True
                break
        if found:
            self._rewrite_jsonl(self._chat_path(chat_id), messages)
            chat = self.get_chat(chat_id)
            if chat is not None and new_message.ts >= chat.last_ts:
                chat.update_from_message(new_message)
                self.update_chat(chat)
        return found

    def get_outgoing_placeholder_ids(self, chat_id):
        """Return queued placeholder ids for a chat."""
        messages = self.load_messages(chat_id)
        return [m.event_id for m in messages if m.outgoing and m.queued]

    def stats(self):
        """Return a small diagnostic summary."""
        return {
            "chats": len(self._index.get("chats", {})),
            "index_dirty": self._index_dirty,
        }
