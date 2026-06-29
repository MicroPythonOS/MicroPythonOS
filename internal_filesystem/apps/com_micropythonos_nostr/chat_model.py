import logging

logger = logging.getLogger(__name__)

# Nostr kind codes used by this client.
KIND_DM = 4
KIND_CHANNEL_CREATE = 40
KIND_CHANNEL_META = 41
KIND_CHANNEL_MESSAGE = 42
KIND_NIP17_CHAT = 14

# Default protocol for 1-on-1 KIND_DM chats without a per-chat override.
# Change to "nip4" if you want NIP-04 as the default instead of NIP-17.
DEFAULT_DM_PROTOCOL = "nip17"

# Human-readable protocol label shown next to each chat message.
PROTOCOL_LABELS = {
    KIND_DM: "NIP-04",
    KIND_NIP17_CHAT: "NIP-17",
    KIND_CHANNEL_MESSAGE: "NIP-28",
}

# Chat ID prefixes.
CHAT_ID_DM_PREFIX = "dm_"
CHAT_ID_CHANNEL_PREFIX = "channel_"
CHAT_ID_NIP17_PREFIX = "nip17_"

# Auto-joined public channel (#MicroPythonOS, NIP-28).
DEFAULT_CHANNEL_ID = "cbf20cd9212aea3c7d399777b69cec750a0109edd831001a5011d892268a9481"
DEFAULT_CHANNEL_NAME = "MicroPythonOS"
DEFAULT_CHANNEL_ABOUT = "MicroPythonOS community chat"


def _peer_sort_key(own_pubkey, peer_pubkey):
    """Return a stable chat id for a DM based on the two participants."""
    if own_pubkey < peer_pubkey:
        return own_pubkey, peer_pubkey
    return peer_pubkey, own_pubkey


def dm_chat_id(own_pubkey, peer_pubkey):
    """Stable DM chat id string from two pubkeys."""
    a, b = _peer_sort_key(own_pubkey, peer_pubkey)
    return f"{CHAT_ID_DM_PREFIX}{a}_{b}"


def channel_chat_id(channel_id):
    """Channel chat id string from a channel creation event id."""
    return f"{CHAT_ID_CHANNEL_PREFIX}{channel_id}"


def nip17_group_chat_id(participants):
    """Stable NIP-17 group chat id from a list of participant pubkeys."""
    return f"{CHAT_ID_NIP17_PREFIX}{'_'.join(sorted(participants))}"


def participants_from_nip17_event(event, own_pubkey):
    """Return the other participants of a kind 14 event, excluding the user."""
    tags = getattr(event, "tags", []) or []
    participants = set()
    for tag in tags:
        if isinstance(tag, (list, tuple)) and len(tag) >= 2 and tag[0] == "p":
            participants.add(tag[1])
    author = getattr(event, "public_key", None)
    if not author and hasattr(event, "pubkey"):
        author = event.pubkey
    if author:
        participants.add(author)
    participants.discard(own_pubkey)
    return sorted(participants)


def subject_from_nip17_event(event):
    """Return the subject tag value of a kind 14 event, if any."""
    tags = getattr(event, "tags", []) or []
    for tag in tags:
        if isinstance(tag, (list, tuple)) and len(tag) >= 2 and tag[0] == "subject":
            return tag[1]
    return None


def chat_id_for_event(event, own_pubkey):
    """Return the chat id that an incoming event belongs to, or None."""
    kind = getattr(event, "kind", None)
    if kind == KIND_DM:
        return _dm_chat_id_from_event(event, own_pubkey)
    if kind == KIND_CHANNEL_MESSAGE:
        return _channel_chat_id_from_event(event)
    if kind == KIND_NIP17_CHAT:
        participants = participants_from_nip17_event(event, own_pubkey)
        if len(participants) == 1:
            return dm_chat_id(own_pubkey, participants[0])
        if len(participants) > 1:
            return nip17_group_chat_id(participants)
    return None


def _dm_chat_id_from_event(event, own_pubkey):
    """Derive a DM chat id from the event's p-tag and the receiver's pubkey."""
    tags = getattr(event, "tags", []) or []
    peer = None
    for tag in tags:
        if isinstance(tag, (list, tuple)) and len(tag) >= 2 and tag[0] == "p":
            p = tag[1]
            if p != own_pubkey:
                peer = p
                break
    if peer is None:
        # Outgoing DM stored locally may only reference the recipient via p-tag.
        # If no peer different from self, use the event author's pubkey.
        peer = getattr(event, "public_key", None) or event.pubkey
    return dm_chat_id(own_pubkey, peer)


def _channel_chat_id_from_event(event):
    """Derive a channel chat id from the first e-tag on a kind 42 event."""
    tags = getattr(event, "tags", []) or []
    for tag in tags:
        if isinstance(tag, (list, tuple)) and len(tag) >= 2 and tag[0] == "e":
            return channel_chat_id(tag[1])
    return None


def peer_from_dm_event(event, own_pubkey):
    """Return the peer pubkey from a DM event's p-tags."""
    tags = getattr(event, "tags", []) or []
    for tag in tags:
        if isinstance(tag, (list, tuple)) and len(tag) >= 2 and tag[0] == "p":
            p = tag[1]
            if p != own_pubkey:
                return p
    return getattr(event, "public_key", None) or event.pubkey


def channel_id_from_event(event):
    """Return the raw channel id from the first e-tag on a kind 42 event."""
    tags = getattr(event, "tags", []) or []
    for tag in tags:
        if isinstance(tag, (list, tuple)) and len(tag) >= 2 and tag[0] == "e":
            return tag[1]
    return None


class Message:
    """Minimal chat message. Signatures are discarded after verification."""

    def __init__(
        self,
        event_id,
        ts,
        pubkey,
        content,
        kind,
        outgoing=False,
        queued=False,
    ):
        self.event_id = event_id
        self.ts = int(ts)
        self.pubkey = pubkey
        self.content = content
        self.kind = kind
        self.outgoing = bool(outgoing)
        self.queued = bool(queued)

    def to_dict(self):
        return {
            "id": self.event_id,
            "ts": self.ts,
            "pubkey": self.pubkey,
            "content": self.content,
            "kind": self.kind,
            "outgoing": self.outgoing,
            "queued": self.queued,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            event_id=data.get("id") or data.get("event_id", ""),
            ts=data.get("ts", 0),
            pubkey=data.get("pubkey", ""),
            content=data.get("content", ""),
            kind=data.get("kind", 0),
            outgoing=data.get("outgoing", False),
            queued=data.get("queued", False),
        )

    def short_preview(self, max_len=60):
        text = self.content.replace("\n", " ")
        if len(text) > max_len:
            text = text[:max_len - 1] + "…"
        return text


def _short_name(pubkey):
    if not pubkey:
        return "?"
    return pubkey[:8]


class Chat:
    """Summary of a DM or channel conversation."""

    def __init__(
        self,
        chat_id,
        kind,
        title=None,
        peer_pubkey=None,
        channel_id=None,
        participants=None,
        last_ts=0,
        last_preview="",
        unread=0,
    ):
        self.chat_id = chat_id
        self.kind = kind
        self.title = title or _default_title(kind, peer_pubkey, channel_id, participants)
        self.peer_pubkey = peer_pubkey
        self.channel_id = channel_id
        self.participants = list(participants) if participants else []
        self.last_ts = int(last_ts)
        self.last_preview = last_preview
        self.unread = int(unread)

    @classmethod
    def dm(cls, own_pubkey, peer_pubkey):
        chat_id = dm_chat_id(own_pubkey, peer_pubkey)
        return cls(
            chat_id=chat_id,
            kind=KIND_DM,
            peer_pubkey=peer_pubkey,
        )

    @classmethod
    def channel(cls, channel_id, title=None):
        chat_id = channel_chat_id(channel_id)
        return cls(
            chat_id=chat_id,
            kind=KIND_CHANNEL_MESSAGE,
            title=title or f"#{channel_id[:8]}",
            channel_id=channel_id,
        )

    @classmethod
    def nip17_group(cls, participants, title=None):
        chat_id = nip17_group_chat_id(participants)
        return cls(
            chat_id=chat_id,
            kind=KIND_NIP17_CHAT,
            title=title,
            peer_pubkey=participants[0] if len(participants) == 1 else None,
            participants=participants,
        )

    @classmethod
    def from_dict(cls, chat_id, data):
        return cls(
            chat_id=chat_id,
            kind=data.get("kind", 0),
            title=data.get("title"),
            peer_pubkey=data.get("peer_pubkey"),
            channel_id=data.get("channel_id"),
            participants=data.get("participants"),
            last_ts=data.get("last_ts", 0),
            last_preview=data.get("last_preview", ""),
            unread=data.get("unread", 0),
        )

    def to_dict(self):
        return {
            "kind": self.kind,
            "title": self.title,
            "peer_pubkey": self.peer_pubkey,
            "channel_id": self.channel_id,
            "participants": self.participants,
            "last_ts": self.last_ts,
            "last_preview": self.last_preview,
            "unread": self.unread,
        }

    def update_from_message(self, message):
        self.last_ts = max(self.last_ts, message.ts)
        self.last_preview = message.short_preview()

    def mark_read(self):
        self.unread = 0

    def increment_unread(self):
        self.unread += 1

    def sender_name(self, message):
        if message.outgoing:
            return "You"
        if self.kind == KIND_DM:
            return _short_name(self.peer_pubkey)
        return _short_name(message.pubkey)


def _default_title(kind, peer_pubkey, channel_id, participants=None):
    if kind == KIND_DM:
        return _short_name(peer_pubkey)
    if kind == KIND_NIP17_CHAT:
        if participants and len(participants) > 1:
            return ", ".join(_short_name(p) for p in participants)
        return _short_name(peer_pubkey)
    if channel_id:
        return f"#{channel_id[:8]}"
    return "Chat"
