import ssl
import json
import time

import logging

from mpos import Service, TaskManager
from mpos.time_zone import TimeZone

from nostr.relay_manager import RelayManager
from nostr.message_type import ClientMessageType
from nostr.filter import Filter, Filters
from nostr.event import Event, EncryptedDirectMessage
from nostr.key import PrivateKey


logger = logging.getLogger(__name__)

try:
    from nostr.nip17 import decrypt_gift_wrap_to_rumor, make_nip17_messages
except ImportError:
    decrypt_gift_wrap_to_rumor = None
    make_nip17_messages = None

KIND_SET_METADATA = 0

# NIP-65 relay list metadata and NIP-17 DM relay list / private messages.
KIND_RELAY_LIST = 10002
KIND_DM_RELAY_LIST = 10050
KIND_NIP17_SEAL = 13
KIND_NIP17_CHAT = 14
KIND_NIP17_FILE = 15
KIND_NIP17_GIFT_WRAP = 1059
KIND_NIP17_GIFT_WRAP_EPHEMERAL = 21059

NIP17_KINDS = (
    KIND_NIP17_SEAL,
    KIND_NIP17_CHAT,
    KIND_NIP17_FILE,
    KIND_NIP17_GIFT_WRAP,
    KIND_NIP17_GIFT_WRAP_EPHEMERAL,
)

EVENT_KIND_NAMES = {
    0: "SET_METADATA",
    1: "TEXT_NOTE",
    2: "RECOMMEND_RELAY",
    3: "CONTACTS",
    4: "ENCRYPTED_DM",
    5: "DELETE",
    13: "NIP17_SEAL",
    14: "NIP17_CHAT",
    15: "NIP17_FILE",
    40: "CHANNEL_CREATE",
    41: "CHANNEL_META",
    42: "CHANNEL_MESSAGE",
    10002: "RELAY_LIST",
    10050: "DM_RELAY_LIST",
    1059: "GIFT_WRAP",
    21059: "GIFT_WRAP_EPHEMERAL",
}


def get_kind_name(kind):
    return EVENT_KIND_NAMES.get(kind, f"UNKNOWN({kind})")


def format_timestamp(timestamp):
    try:
        import time as time_module
        time_tuple = time_module.localtime(timestamp)
        return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}".format(
            time_tuple[0], time_tuple[1], time_tuple[2],
            time_tuple[3], time_tuple[4]
        )
    except Exception:
        return str(timestamp)


def format_tags(tags):
    if not tags:
        return ""
    tag_strs = []
    for tag in tags:
        if len(tag) >= 2:
            tag_type = tag[0]
            tag_value = tag[1]
            if len(tag_value) > 16:
                tag_value = tag_value[:16] + "..."
            tag_strs.append(f"{tag_type}:{tag_value}")
    if tag_strs:
        return "Tags: " + ", ".join(tag_strs)
    return ""


class NostrSubscription:
    """A generic Nostr subscription managed by NostrManager."""

    def __init__(self, name, filters, callback=None):
        self.name = name
        self.filters = filters
        self.callback = callback


class NostrEvent:
    def __init__(self, event_obj, private_key=None):
        self.event = event_obj
        self.created_at = event_obj.created_at
        self.content = event_obj.content
        self.public_key = event_obj.public_key
        self.kind = event_obj.kind
        self.tags = event_obj.tags if hasattr(event_obj, 'tags') else []
        self.private_key = private_key
        self.decrypted_content = None
        if self.kind == 4 and self.private_key:
            self._try_decrypt()

    def _try_decrypt(self):
        try:
            if self.kind == 4 and self.content:
                decrypted = self.private_key.decrypt_message(
                    self.content,
                    self.public_key
                )
                self.decrypted_content = decrypted
                if __debug__:
                    logger.debug("Successfully decrypted DM: %s", decrypted)
        except Exception as e:
            if __debug__:
                logger.debug("Failed to decrypt DM: %s", e)

    def get_kind_name(self):
        return get_kind_name(self.kind)

    def get_formatted_timestamp(self):
        return format_timestamp(self.created_at)

    def get_formatted_tags(self):
        return format_tags(self.tags)

    def get_display_content(self):
        if self.decrypted_content is not None:
            return self.decrypted_content
        return self.content

    def __str__(self):
        if self.kind == 42:
            return self._format_channel_message()
        kind_name = self.get_kind_name()
        timestamp = self.get_formatted_timestamp()
        tags_str = self.get_formatted_tags()
        display_content = self.get_display_content()
        result = f"[{kind_name}] {timestamp}\n"
        if display_content:
            result += f"{display_content}"
        if tags_str:
            result += f"\n{tags_str}"
        return result

    def _format_channel_message(self):
        timestamp = self.get_formatted_timestamp()
        pubkey = (self.public_key[:16] + "...") if self.public_key else "?"
        content = self.get_display_content()
        return f"[{timestamp}] {pubkey}\n{content}"


_sub_id_counter = 0


def _make_subscription_id(prefix):
    global _sub_id_counter
    _sub_id_counter += 1
    return prefix + str(int(time.time())) + "_" + str(_sub_id_counter)


def _filter_identity(filter_obj):
    """Return the filter without time-window fields, for identity comparison."""
    identity = filter_obj.to_json_object()
    identity.pop("since", None)
    identity.pop("until", None)
    identity.pop("limit", None)
    return identity


def _filters_identity_equal(a, b):
    """Compare two Filters objects ignoring since/until/limit."""
    if len(a.data) != len(b.data):
        return False
    for fa, fb in zip(a.data, b.data):
        if _filter_identity(fa) != _filter_identity(fb):
            return False
    return True


def _parse_nsec(nsec):
    if nsec.startswith("nsec1"):
        return PrivateKey.from_nsec(nsec)
    return PrivateKey(bytes.fromhex(nsec))


def _normalize_relays(relays):
    """Return a deduplicated list of relay URL strings."""
    if relays is None:
        return []
    if isinstance(relays, str):
        relays = [r.strip() for r in relays.split(",") if r.strip()]
    seen = set()
    out = []
    for url in relays:
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _pubkey_to_hex(pubkey_or_npub):
    if pubkey_or_npub.startswith("npub1"):
        from nostr.key import PublicKey
        return PublicKey.from_npub(pubkey_or_npub).hex()
    return pubkey_or_npub


class NostrManager:

    _instance = None
    EVENTS_TO_SHOW = 50
    NWC_POLL_SECONDS = 120
    RELAY_SILENT_RECONNECT_THRESHOLD = 3

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.relay_manager = None
        self._main_task = None
        self.connected = False
        self._polls_since_last_event = 0
        self._last_nwc_poll = 0
        self._relays_configured = False
        # How many transactions list_transactions requests. Kept in sync
        # with the wallet's PAYMENTS_TO_SHOW (the per-slot "Transactions
        # Shown" slider, 1..21) via NWCWallet's PAYMENTS_TO_SHOW property —
        # without that link, NWC would always fetch the class default while
        # LNBits (limit=) and on-chain (pageSize=) honour the user setting.
        self._nwc_list_limit = 21

        # Nostr app state
        self.events = []
        self._nostr_private_key = None
        self._default_relays = []
        self._current_nsec = None
        self._configured_relays = []
        self._relay_list_pending = False
        self._relay_list_published_for = None
        self._subscriptions = []
        self._subscription_ids = {}
        self._nostr_configured = False

        # NWC state
        self._nwc_private_key = None
        self._nwc_wallet_pubkey = None
        self._nwc_relays = []
        self._nwc_sub_id = None
        self._nwc_lud16 = None
        self._nwc_configured = False
        self._nwc_nwc_url = None

        # Set when new relays are configured after the manager started; the
        # main loop picks them up and hot-adds them to the running relay pool.
        self._relays_dirty = False

        # Track per-relay connected state so we can re-send subscriptions when
        # a relay (re)connects. On ESP32 the first SSL handshake often errors
        # and the websocket reconnects a few seconds later, after the initial
        # subscription broadcast has already been dropped.
        self._relay_connected_state = {}
        self._nwc_filters = None

        # Event callbacks: kind -> [callbacks]
        self._event_handlers = {}

        # Post-event callbacks run after normal handlers/subscriptions so
        # background persistence can store events already processed by the UI.
        self._post_event_handlers = {}

        # NWC-specific callbacks (set by NWCWallet)
        self._nwc_balance_cb = None
        self._nwc_payments_cb = None
        self._nwc_notification_cb = None

        # Generic event update callback (called for every event)
        self._events_updated_cb = None

        # Error callback
        self._error_cb = None

        # Lifecycle
        self.keep_running = False
        self._cleanup_done = True
        self._cm_callback = None

    # --- Public lifecycle ---

    def start(self):
        """Initialize the manager. Call before any configure_* methods."""
        if self.keep_running:
            return
        self.keep_running = True
        try:
            from mpos.net.connectivity_manager import ConnectivityManager

            if self._cm_callback is None:
                self._cm_callback = self._on_connectivity_change
                ConnectivityManager.register_callback(self._cm_callback)
                if __debug__:
                    logger.debug("NostrManager: registered connectivity callback")
        except Exception:
            if __debug__:
                logger.debug(
                    "NostrManager: ConnectivityManager unavailable, "
                    "online/offline handling disabled"
                )

    def stop(self):
        """Stop the manager and close all relay connections.

        Subscriptions and configuration are preserved so the manager can be
        restarted when the device comes back online.
        """
        self.keep_running = False
        if (
            self._main_task is not None
            and self._main_task is not True
            and self._cleanup_done
        ):
            self._cleanup_done = False
            TaskManager.create_task(self._do_close())

    async def _do_close(self):
        # Let the main loop finish cleanly first so it doesn't touch
        # relay_manager while we are closing it.
        if self._main_task is not None and self._main_task is not True:
            try:
                await self._main_task
            except Exception:
                pass
        if self.relay_manager is not None:
            try:
                await self.relay_manager.close_connections()
            except Exception as e:
                logger.warning("NostrManager: error closing connections: %s", e)
        self._main_task = None
        self.connected = False
        self.relay_manager = None
        self._relay_connected_state = {}
        # Subscriptions, identity and NWC config are intentionally kept so
        # start() can restore them on the next online event.
        self._cleanup_done = True

    def _on_connectivity_change(self, online):
        if online:
            if not self.keep_running:
                self.start()
            self._ensure_main_task()
        else:
            if self.keep_running:
                self.stop()

    def is_running(self):
        return self.keep_running

    def is_connected(self):
        return self.connected

    # --- Event handler registration ---

    def register_event_handler(self, kind, callback):
        if kind not in self._event_handlers:
            self._event_handlers[kind] = []
        self._event_handlers[kind].append(callback)

    def unregister_event_handler(self, kind, callback):
        if kind in self._event_handlers:
            self._event_handlers[kind] = [
                cb for cb in self._event_handlers[kind] if cb != callback
            ]

    def register_post_event_handler(self, kind, callback):
        """Register a callback that runs after normal UI event handlers.

        Post handlers receive the same NostrEvent instance and are intended
        for background persistence/notification work that should not race
        with foreground UI updates.
        """
        if kind not in self._post_event_handlers:
            self._post_event_handlers[kind] = []
        self._post_event_handlers[kind].append(callback)

    def unregister_post_event_handler(self, kind, callback):
        if kind in self._post_event_handlers:
            self._post_event_handlers[kind] = [
                cb for cb in self._post_event_handlers[kind] if cb != callback
            ]

    def set_nwc_callbacks(self, balance_cb=None, payments_cb=None, notification_cb=None):
        self._nwc_balance_cb = balance_cb
        self._nwc_payments_cb = payments_cb
        self._nwc_notification_cb = notification_cb

    def set_nwc_list_limit(self, n):
        """Set how many transactions list_transactions requests. Clamped
        defensively to 1..100 (matches the on-chain wallet's pageSize
        guard); the Settings slider only produces 1..21."""
        try:
            self._nwc_list_limit = max(1, min(int(n), 100))
        except (TypeError, ValueError):
            pass

    def set_events_updated_callback(self, cb):
        self._events_updated_cb = cb

    def set_error_callback(self, cb):
        self._error_cb = cb

    # --- Configuration ---

    # --- Identity and subscriptions ---

    def _relay_config_key(self, nsec, relays):
        """Return an identity-normalised config key for relay-list publishing."""
        return (nsec, tuple(relays))

    def configure_identity(self, nsec, relays=None):
        """Set the user's private key and default relay(s).

        relays may be a single URL string or a list of URLs."""
        normalised = _normalize_relays(relays)
        same_config = (
            self._nostr_configured
            and nsec == self._current_nsec
            and normalised == self._configured_relays
        )
        if same_config and not self._relay_list_pending:
            self._ensure_main_task()
            return

        self._nostr_private_key = _parse_nsec(nsec)
        self._current_nsec = nsec
        self._default_relays = list(normalised)
        self._configured_relays = list(normalised)
        if not same_config:
            self._relays_dirty = True
        self._relay_list_pending = True
        self._nostr_configured = True
        self._ensure_main_task()

    def subscribe_channel(self, channel_id, name=None, callback=None, since=None, limit=None):
        """Subscribe to a NIP-28 public group chat channel."""
        sub_name = name or f"channel-{channel_id[:8]}"
        filters = Filters([Filter(kinds=[42], event_refs=[channel_id], since=since, limit=limit)])
        self.add_subscription(sub_name, filters, callback)

    def subscribe_metadata(self, pubkey_or_npub, callback=None, since=None, limit=None):
        """Subscribe to kind 0 metadata events for a single profile."""
        hex_pubkey = _pubkey_to_hex(pubkey_or_npub)
        filters = Filters([Filter(kinds=[KIND_SET_METADATA], authors=[hex_pubkey], since=since, limit=limit)])
        self.add_subscription(f"profile-{hex_pubkey[:16]}", filters, callback)

    def subscribe_dms(self, callback=None, since=None, limit=None):
        """Subscribe to NIP-04 direct messages addressed to the configured identity."""
        if self._nostr_private_key is None:
            raise RuntimeError("Identity must be configured before subscribing to DMs")
        own_hex = self._nostr_private_key.public_key.hex()
        filters = Filters([Filter(kinds=[4], pubkey_refs=[own_hex], since=since, limit=limit)])
        self.add_subscription("dms", filters, callback)

    def subscribe_nip17_dms(self, callback=None, since=None, limit=None):
        """Subscribe to NIP-17 / NIP-59 message kinds for debugging.

        We do not decrypt gift wraps here yet; this subscription lets us log
        when these events arrive from relays.
        """
        if self._nostr_private_key is None:
            raise RuntimeError("Identity must be configured before subscribing to DMs")
        own_hex = self._nostr_private_key.public_key.hex()
        filters = Filters([
            Filter(
                kinds=[KIND_NIP17_GIFT_WRAP, KIND_NIP17_GIFT_WRAP_EPHEMERAL],
                pubkey_refs=[own_hex],
                since=since,
                limit=limit,
            ),
            Filter(
                kinds=[KIND_DM_RELAY_LIST, KIND_RELAY_LIST],
                authors=[own_hex],
                since=since,
                limit=limit,
            ),
        ])
        self.add_subscription("nip17-debug", filters, callback)

    def publish_relay_list(self):
        """Publish NIP-65 (kind 10002) and NIP-17 (kind 10050) relay lists."""
        if self._nostr_private_key is None or self.relay_manager is None:
            return None
        if not self._default_relays:
            return None
        own_hex = self._nostr_private_key.public_key.hex()
        relay_tags = [["r", url] for url in self._default_relays if url]
        dm_relay_tags = [["relay", url] for url in self._default_relays if url]
        ids = []
        for kind, tags in ((KIND_RELAY_LIST, relay_tags), (KIND_DM_RELAY_LIST, dm_relay_tags)):
            event = Event(
                content="",
                public_key=own_hex,
                kind=kind,
                tags=tags,
            )
            event.__post_init__()
            self._nostr_private_key.sign_event(event)
            self.relay_manager.publish_event(event)
            ids.append(event.id)
        key = self._relay_config_key(self._current_nsec, self._configured_relays)
        self._relay_list_published_for = key
        self._relay_list_pending = False
        logger.info(
            "NostrManager: published relay lists (%s)", len(ids)
        )
        return ids

    def publish_channel_message(self, channel_id, content):
        """Sign and publish a NIP-28 channel message (kind 42)."""
        if self._nostr_private_key is None:
            raise RuntimeError("Identity must be configured before publishing messages")
        if not content:
            raise ValueError("Message content cannot be empty")
        if self.relay_manager is None:
            raise RuntimeError("Relay manager is not ready yet")
        event = Event(
            content=content,
            public_key=self._nostr_private_key.public_key.hex(),
            kind=42,
            tags=[["e", channel_id, "", "root"]],
        )
        event.__post_init__()
        self._nostr_private_key.sign_event(event)
        self.relay_manager.publish_event(event)
        logger.info("NostrManager: published channel message to %s", channel_id[:16])
        return event.id

    def publish_channel_creation(self, name):
        """Publish a NIP-28 channel creation event (kind 40).

        Returns the channel ID (the event ID of the creation event).
        """
        if self._nostr_private_key is None:
            raise RuntimeError("Identity must be configured before creating channels")
        if self.relay_manager is None:
            raise RuntimeError("Relay manager is not ready yet")
        event = Event(
            content=json.dumps({"name": name, "about": "", "picture": ""}),
            public_key=self._nostr_private_key.public_key.hex(),
            kind=40,
        )
        event.__post_init__()
        self._nostr_private_key.sign_event(event)
        self.relay_manager.publish_event(event)
        logger.info("NostrManager: published channel creation '%s' -> %s", name, event.id[:16])
        return event.id

    def publish_metadata(self, content):
        """Publish a kind 0 metadata event for the configured identity."""
        if self._nostr_private_key is None:
            raise RuntimeError("Identity must be configured before publishing metadata")
        if self.relay_manager is None:
            raise RuntimeError("Relay manager is not ready yet")
        event = Event(
            content=content,
            public_key=self._nostr_private_key.public_key.hex(),
            kind=KIND_SET_METADATA,
        )
        event.__post_init__()
        self._nostr_private_key.sign_event(event)
        self.relay_manager.publish_event(event)
        logger.info("NostrManager: published metadata profile")
        return event.id

    def publish_channel_metadata(self, channel_id, name, about="", picture=""):
        """Publish a NIP-28 channel metadata event (kind 41).

        References the channel creation event (kind 40) via an e-tag.
        """
        if self._nostr_private_key is None:
            raise RuntimeError("Identity must be configured before publishing metadata")
        if self.relay_manager is None:
            raise RuntimeError("Relay manager is not ready yet")
        content = json.dumps({"name": name, "about": about, "picture": picture})
        event = Event(
            content=content,
            public_key=self._nostr_private_key.public_key.hex(),
            kind=41,
            tags=[["e", channel_id, "", "root"]],
        )
        event.__post_init__()
        self._nostr_private_key.sign_event(event)
        self.relay_manager.publish_event(event)
        logger.info("NostrManager: published channel metadata for %s: %s", channel_id[:16], name)
        return event.id

    def search_channels(self, search_term, callback, limit=10):
        """Subscribe to kind 41 events matching a NIP-50 search term.

        The callback receives (channel_id, name, about) for each result.
        """
        filters = Filters([Filter(kinds=[41], search=search_term, limit=limit)])
        sub_name = f"channel-search-{search_term[:16]}"
        results = set()

        def _wrapper(nostr_event):
            try:
                meta = json.loads(nostr_event.content) if nostr_event.content else {}
                name = meta.get("name", "")
                about = meta.get("about", "")
                tags = getattr(nostr_event.event, "tags", []) or []
                channel_id = None
                for tag in tags:
                    if isinstance(tag, (list, tuple)) and len(tag) >= 2 and tag[0] == "e":
                        channel_id = tag[1]
                        break
                if channel_id and channel_id not in results:
                    results.add(channel_id)
                    callback(channel_id, name, about)
            except Exception:
                pass

        self.add_subscription(sub_name, filters, _wrapper)
        return sub_name

    def _publish_signed_dm(self, private_key, recipient_hex, content, kind=4, reference_event_id=None):
        """Build, sign and publish an encrypted direct message."""
        if self.relay_manager is None:
            raise RuntimeError("Relay manager is not ready yet")
        dm = EncryptedDirectMessage(
            recipient_pubkey=recipient_hex,
            cleartext_content=content,
            kind=kind,
            reference_event_id=reference_event_id,
        )
        private_key.sign_event(dm)
        self.relay_manager.publish_event(dm)
        return dm.id

    def publish_dm(self, recipient_pubkey_or_npub, content, reference_event_id=None):
        """Sign and publish a NIP-04 encrypted direct message (kind 4)."""
        if self._nostr_private_key is None:
            raise RuntimeError("Identity must be configured before publishing messages")
        if not content:
            raise ValueError("Message content cannot be empty")
        if self.relay_manager is None:
            raise RuntimeError("Relay manager is not ready yet")
        recipient_hex = _pubkey_to_hex(recipient_pubkey_or_npub)
        dm_id = self._publish_signed_dm(
            self._nostr_private_key,
            recipient_hex,
            content,
            reference_event_id=reference_event_id,
        )
        logger.info("NostrManager: published DM to %s", recipient_hex[:16])
        return dm_id

    def publish_nip17_message(
        self, content, recipients, subject=None, reply_to=None, created_at=None
    ):
        """Sign and publish a NIP-17 gift-wrapped chat message (kind 14).

        Returns a list of the published kind 1059 event ids.
        """
        if self._nostr_private_key is None:
            raise RuntimeError("Identity must be configured before publishing messages")
        if not content:
            raise ValueError("Message content cannot be empty")
        if self.relay_manager is None:
            raise RuntimeError("Relay manager is not ready yet")
        if not recipients:
            raise ValueError("Recipients cannot be empty")
        if make_nip17_messages is None:
            raise RuntimeError("NIP-17 support is not available")

        hex_recipients = [_pubkey_to_hex(r) for r in recipients]
        # Capture the wall-clock timestamp once, before the pure-Python
        # ChaCha20 loop can starve the ESP32 scheduler and make time.time()
        # stale.
        if created_at is None:
            created_at = Event.epoch_seconds()
        gift_events = make_nip17_messages(
            self._nostr_private_key,
            content,
            hex_recipients,
            subject=subject,
            reply_to=reply_to,
            created_at=created_at,
        )
        ids = []
        for gift in gift_events:
            event = Event(
                content=gift["content"],
                public_key=gift["pubkey"],
                created_at=gift["created_at"],
                kind=gift["kind"],
                tags=gift["tags"],
                signature=gift["sig"],
            )
            self.relay_manager.publish_event(event)
            ids.append(gift["id"])
        logger.info(
            "NostrManager: published NIP-17 message to %s recipient(s)",
            len(ids)
        )
        return ids

    def get_own_pubkey_hex(self):
        """Return the configured identity's public key in hex, or None."""
        if self._nostr_private_key is None:
            return None
        return self._nostr_private_key.public_key.hex()

    def close_subscription(self, name):
        """Remove a named subscription and close it on relays."""
        self._subscriptions = [s for s in self._subscriptions if s.name != name]
        self._subscription_ids.pop(name, None)
        if self.relay_manager is not None:
            try:
                self.relay_manager.close_subscription(name)
            except Exception as e:
                logger.warning("NostrManager: error closing subscription '%s': %s", name, e)

    def add_subscription(self, name, filters, callback=None, since=None, limit=None):
        """Add a generic subscription, reusing an existing one with the same name.

        Optional ``since`` and ``limit`` are applied to every Filter in the
        supplied Filters object that does not already set them. This lets the
        client fetch only recent events instead of the full relay history.

        If a subscription with the same name is already registered, the callback
        and filter window are refreshed. A new request is sent only when the
        subscription's identity (kinds, authors, event/pubkey refs, etc.)
        changes, not when only the time window or limit moves. The stored filter
        is used on the next reconnect or when the subscription is first
        published. This prevents activities from re-subscribing every time they
        resume.
        """
        if since is not None or limit is not None:
            for f in filters.data:
                if since is not None and f.since is None:
                    f.since = since
                if limit is not None and f.limit is None:
                    f.limit = limit

        existing = None
        for s in self._subscriptions:
            if s.name == name:
                existing = s
                break

        if existing is not None:
            if callback is not None:
                existing.callback = callback
            # ponytail: callers use stable names (dms, channel-<id>, dm-<pair>).
            # Re-publish only when the subscription identity changes, not when
            # only the time window or limit moves.
            identity_changed = not _filters_identity_equal(existing.filters, filters)
            existing.filters = filters
            if identity_changed and self.connected and self.relay_manager is not None:
                sub_id = self._subscription_ids.get(name)
                if sub_id is None:
                    sub_id = _make_subscription_id("mpos_sub_")
                    self._subscription_ids[name] = sub_id
                self._publish_subscription(existing, sub_id)
            return

        sub = NostrSubscription(name, filters, callback)
        self._subscriptions.append(sub)
        if self.connected and self.relay_manager is not None:
            sub_id = _make_subscription_id("mpos_sub_")
            self._subscription_ids[name] = sub_id
            self._publish_subscription(sub, sub_id)

    def _publish_subscription(self, sub, sub_id):
        self.relay_manager.add_subscription(sub_id, sub.filters)
        req = [ClientMessageType.REQUEST, sub_id]
        req.extend(sub.filters.to_json_array())
        self.relay_manager.publish_message(json.dumps(req))
        logger.info("NostrManager: subscribed to '%s' with filters %s",
            sub.name, sub.filters.to_json_array())

    def _send_subscriptions_to_relays(self, urls):
        """Re-send all active subscriptions to a specific set of relays.

        Used when a relay (re)connects after the initial broadcast, so the
        relay does not silently drop events.
        """
        if self.relay_manager is None or not urls:
            return
        for sub in self._subscriptions:
            sub_id = self._subscription_ids.get(sub.name)
            if sub_id is None:
                sub_id = _make_subscription_id("mpos_sub_")
                self._subscription_ids[sub.name] = sub_id
            self.relay_manager.add_subscription(sub_id, sub.filters)
            req = [ClientMessageType.REQUEST, sub_id]
            req.extend(sub.filters.to_json_array())
            req_json = json.dumps(req)
            for url in urls:
                relay = self.relay_manager.relays.get(url)
                if relay is not None and relay.connected:
                    relay.publish(req_json)
        if self._nwc_configured and self._nwc_sub_id:
            if self._nwc_filters is None:
                self._nwc_filters = Filters([Filter(
                    kinds=[23195, 23196],
                    authors=[self._nwc_wallet_pubkey],
                    pubkey_refs=[self._nwc_private_key.public_key.hex()]
                )])
            self.relay_manager.add_subscription(self._nwc_sub_id, self._nwc_filters)
            req = [ClientMessageType.REQUEST, self._nwc_sub_id]
            req.extend(self._nwc_filters.to_json_array())
            req_json = json.dumps(req)
            for url in urls:
                relay = self.relay_manager.relays.get(url)
                if relay is not None and relay.connected:
                    relay.publish(req_json)

    def configure_nwc(self, nwc_url):
        """Configure and start NWC subscriptions."""
        if self._nwc_nwc_url == nwc_url:
            # Same URL — config unchanged, but the main task may have been
            # torn down by a stop()/start() cycle in between (e.g.
            # NostrClientService.onDestroy). Without this, reconfiguring
            # with an identical URL after a manager restart would leave NWC
            # permanently dead: no main task, nothing polling.
            self._ensure_main_task()
            return

        relays, wallet_pubkey, secret, lud16 = self._parse_nwc_url(nwc_url)
        self._nwc_relays = relays
        self._nwc_wallet_pubkey = wallet_pubkey
        self._nwc_private_key = PrivateKey(bytes.fromhex(secret))
        self._nwc_lud16 = lud16
        self._nwc_nwc_url = nwc_url
        self._nwc_configured = True
        self._relays_dirty = True
        self._ensure_main_task()

    def _parse_nwc_url(self, nwc_url):
        from mpos.util import urldecode
        if __debug__:
            logger.debug("Starting to parse NWC URL")
        try:
            if nwc_url.startswith('nostr+walletconnect://'):
                nwc_url = nwc_url[22:]
            elif nwc_url.startswith('nwc:'):
                nwc_url = nwc_url[4:]
            else:
                raise ValueError("Invalid NWC URL: missing 'nostr+walletconnect://' or 'nwc:' prefix")
            nwc_url = urldecode(nwc_url)
            parts = nwc_url.split('?')
            pubkey = parts[0]
            if len(pubkey) != 64 or not all(c in '0123456789abcdef' for c in pubkey):
                raise ValueError("Invalid NWC URL: pubkey must be 64 hex characters")
            relays = []
            lud16 = None
            secret = None
            if len(parts) > 1:
                params = parts[1].split('&')
                for param in params:
                    if param.startswith('relay='):
                        relay = param[6:]
                        relays.append(relay)
                    elif param.startswith('secret='):
                        secret = param[7:]
                    elif param.startswith('lud16='):
                        lud16 = param[6:]
            if not pubkey or not len(relays) > 0 or not secret:
                raise ValueError("Invalid NWC URL: missing required fields (pubkey, relay, or secret)")
            if len(secret) != 64 or not all(c in '0123456789abcdef' for c in secret):
                raise ValueError("Invalid NWC URL: secret must be 64 hex characters")
            if __debug__:
                logger.debug("Parsed NWC data - Relays: %s, lud16: %s", relays, lud16)
            return relays, pubkey, secret, lud16
        except Exception as e:
            raise RuntimeError(f"Exception parsing NWC URL: {e}")

    def _ensure_main_task(self):
        if self._main_task is not None:
            return
        self._main_task = TaskManager.create_task(self._run())

    async def _run(self):
        """Main event loop — manages relay connections, subscriptions, event routing, and NWC polling."""

        # Wait for NTP time sync before opening relay connections.
        if not TimeZone.time_is_set():
            try:
                from mpos.net.connectivity_manager import ConnectivityManager
                online = ConnectivityManager.is_online()
            except Exception as e:
                if __debug__:
                    logger.debug(
                        "NostrManager: cannot check connectivity, skipping time-sync wait: %s", e
                    )
                online = False

            if online:
                logger.info("NostrManager: waiting for NTP time sync...")
                while (
                    self.keep_running
                    and online
                    and not TimeZone.time_is_set()
                ):
                    await TaskManager.sleep_ms(1000)
                    try:
                        online = ConnectivityManager.is_online()
                    except Exception:
                        online = False

                if not self.keep_running or not online:
                    return
                logger.info("NostrManager: time synced, continuing initialization")

        self.relay_manager = RelayManager()

        # Add all configured relays
        for relay in self._default_relays:
            self.relay_manager.add_relay(relay)
        for relay in self._nwc_relays:
            self.relay_manager.add_relay(relay)

        if not self.relay_manager.relays:
            logger.warning("NostrManager: no relays configured, waiting...")
            while self.keep_running and not self._relays_configured:
                await TaskManager.sleep(0.5)
                if self._default_relays or self._nwc_relays:
                    self._relays_configured = True
            if not self.keep_running:
                return
            for relay in self._default_relays:
                self.relay_manager.add_relay(relay)
            for relay in self._nwc_relays:
                self.relay_manager.add_relay(relay)
            if not self.relay_manager.relays:
                logger.warning("NostrManager: still no relays after wait, exiting")
                return

        await self.relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE})
        self.connected = False
        nrconnected = 0

        # Wait for at least one *actually* connected relay. On ESP32 the first
        # SSL handshake often fails and is retried, so counting errored relays
        # as connected makes us broadcast subscriptions while disconnected.
        for _ in range(300):
            await TaskManager.sleep(0.1)
            nrconnected = self.relay_manager.connected_relays()
            if nrconnected > 0 or not self.keep_running:
                break

        if nrconnected == 0:
            msg = "Could not connect to any Nostr relay."
            logger.info("NostrManager: %s", msg)
            if self._error_cb:
                self._error_cb(msg)
            # Reset lifecycle state so start() can be retried when we come
            # back online.
            self.connected = False
            self._main_task = None
            self.keep_running = False
            return

        if not self.keep_running:
            return

        connected, disconnected = self.relay_manager.connection_summary()
        logger.info("NostrManager: %s relay(s) connected", nrconnected)
        logger.info("NostrManager: connected relays: %s", connected)
        if disconnected:
            logger.info("NostrManager: disconnected relays: %s", disconnected)
        self.connected = True

        # Set up generic subscriptions
        self._subscription_ids = {}
        for sub in self._subscriptions:
            sub_id = _make_subscription_id("mpos_sub_")
            self._subscription_ids[sub.name] = sub_id
            self._publish_subscription(sub, sub_id)

        # Set up NWC subscription
        if self._nwc_configured:
            self._nwc_sub_id = _make_subscription_id("micropython_nwc_")
            self._nwc_filters = Filters([Filter(
                kinds=[23195, 23196],
                authors=[self._nwc_wallet_pubkey],
                pubkey_refs=[self._nwc_private_key.public_key.hex()]
            )])
            self.relay_manager.add_subscription(self._nwc_sub_id, self._nwc_filters)
            req = [ClientMessageType.REQUEST, self._nwc_sub_id]
            req.extend(self._nwc_filters.to_json_array())
            self.relay_manager.publish_message(json.dumps(req))
            logger.info("NostrManager: subscribed to NWC responses")
            if self._nwc_lud16 and "@" in self._nwc_lud16:
                # Don't use permissive ensure_lightning_prefix, only allow LUD-16
                self._handle_nwc_static_receive_code((self._nwc_lud16))

        self._relay_connected_state = {
            url: relay.connected for url, relay in self.relay_manager.relays.items()
        }

        if self._relay_list_pending:
            try:
                self.publish_relay_list()
            except Exception as e:
                logger.error("NostrManager: relay list publish error: %s", e)

        self._last_nwc_poll = time.time() - self.NWC_POLL_SECONDS

        # Main processing loop
        while self.keep_running:
            await TaskManager.sleep(0.1)

            if not self.keep_running:
                break

            if self._relays_dirty:
                try:
                    await self._sync_relays()
                except Exception as e:
                    logger.error("NostrManager: relay sync error: %s", e)
                    import sys
                    sys.print_exception(e)

            # Detect relays that (re)connected after the initial open and
            # re-send subscriptions. On ESP32 the websocket often reconnects
            # after the first SSL error, and subscriptions sent earlier while
            # disconnected are dropped by the relay.
            if self.relay_manager is not None:
                for url, relay in self.relay_manager.relays.items():
                    was = self._relay_connected_state.get(url, False)
                    if relay.connected and not was:
                        self._send_subscriptions_to_relays([url])
                    self._relay_connected_state[url] = relay.connected

            now = time.time()

            # --- Periodic NWC polling ---
            if self._nwc_configured and now - self._last_nwc_poll >= self.NWC_POLL_SECONDS:
                self._last_nwc_poll = now

                if self._polls_since_last_event >= self.RELAY_SILENT_RECONNECT_THRESHOLD:
                    await self._reconnect_relay()
                    if not self.keep_running:
                        break

                self._polls_since_last_event += 1

                try:
                    self.nwc_fetch_balance()
                except Exception as e:
                    logger.warning("NostrManager: fetch_balance error: %s", e)

                try:
                    self.nwc_fetch_payments()
                except Exception as e:
                    logger.warning("NostrManager: fetch_payments error: %s", e)

            # --- Process incoming events ---
            try:
                if self.relay_manager.message_pool.has_events():
                    event_msg = self.relay_manager.message_pool.get_event()
                    event = event_msg.event
                    logger.info("NostrManager: received event kind=%s from %s via %s",
                        event.kind, event.public_key[:16], event_msg.url)

                    try:
                        self._process_event(event, relay_url=event_msg.url)
                    except Exception as e:
                        logger.error("NostrManager: error processing event: %s", e)
                        import sys
                        sys.print_exception(e)

                if self.relay_manager.message_pool.has_notices():
                    notice = self.relay_manager.message_pool.get_notice()
                    logger.warning("NostrManager: relay notice: %s", notice)
                    if notice and hasattr(notice, 'content') and self._error_cb:
                        self._error_cb("Relay: {}".format(notice.content))

                if self.relay_manager.message_pool.has_closed_messages():
                    closed = self.relay_manager.message_pool.get_closed_message()
                    if __debug__:
                        logger.debug(
                            "NostrManager: CLOSED from %s sub=%s reason=%s",
                            closed.url,
                            closed.subscription_id[:16],
                            closed.reason,
                        )

                if self.relay_manager.message_pool.has_ok_messages():
                    ok = self.relay_manager.message_pool.get_ok_message()
                    if __debug__:
                        logger.debug(
                            "NostrManager: OK from %s event=%s status=%s message=%s",
                            ok.url,
                            ok.event_id[:16],
                            ok.status,
                            ok.message,
                        )
            except Exception as e:
                logger.error("NostrManager: message poll error: %s", e)
                import sys
                sys.print_exception(e)
                await TaskManager.sleep(1)

    def _decrypt_nip17_gift_wrap(self, event):
        """Unwrap a kind 1059/21059 gift-wrap into a kind 14 rumor event."""
        if decrypt_gift_wrap_to_rumor is None or self._nostr_private_key is None:
            return None
        try:
            rumor = decrypt_gift_wrap_to_rumor(event, self._nostr_private_key)
            if not rumor:
                return None
            return Event(
                content=rumor.get("content", ""),
                public_key=rumor.get("pubkey", ""),
                created_at=rumor.get("created_at", event.created_at),
                kind=rumor.get("kind", KIND_NIP17_CHAT),
                tags=rumor.get("tags", []),
                signature=None,
            )
        except Exception as e:
            logger.warning(
                "Failed to unwrap gift-wrap event %s: %s",
                getattr(event, "id", "?"),
                e,
            )
            return None

    def _process_event(self, event, relay_url=None):
        """Route a single event to all relevant handlers."""

        # NWC events are private and handled separately.
        if event.kind in (23195, 23196) and self._nwc_configured:
            self._process_nwc_event(event)
            return

        if event.kind in NIP17_KINDS or event.kind in (KIND_RELAY_LIST, KIND_DM_RELAY_LIST):
            logger.info(
                "NostrManager: received %s (kind=%s) from %s via %s",
                get_kind_name(event.kind), event.kind, event.public_key[:16], relay_url
            )

        if event.kind in (KIND_NIP17_GIFT_WRAP, KIND_NIP17_GIFT_WRAP_EPHEMERAL):
            decrypted_event = self._decrypt_nip17_gift_wrap(event)
            if decrypted_event is None:
                logger.warning(
                    "NostrManager: failed to unwrap NIP-17 message from %s via %s",
                    event.public_key[:16], relay_url
                )
                return
            # Preserve the original gift-wrap id so the same message deduplicates.
            # Event.id is a computed property; assign an instance attribute to
            # shadow it for downstream code that reads event.id.
            decrypted_event.id = event.id
            event = decrypted_event
            logger.info(
                "NostrManager: unwrapped NIP-17 message from %s: %s",
                event.public_key[:16], event.content
            )

        # Build the shared wrapper once; decrypt DMs if a private key is set.
        nostr_event = NostrEvent(event, self._nostr_private_key)

        # Log plaintext for DMs / NIP-17 chat messages so we can see what arrived.
        if event.kind in (4, KIND_NIP17_CHAT):
            logger.info(
                "NostrManager: plaintext message from %s via %s: %s",
                event.public_key[:16], relay_url, nostr_event.get_display_content()
            )

        # Route by kind to registered callbacks
        if event.kind in self._event_handlers:
            for cb in self._event_handlers[event.kind]:
                try:
                    cb(nostr_event)
                except Exception as e:
                    logger.error("NostrManager: event handler error: %s", e)

        # Store in events list for NostrApp
        self.events.append(nostr_event)
        if len(self.events) > self.EVENTS_TO_SHOW:
            self.events = self.events[-self.EVENTS_TO_SHOW:]

        # Per-subscription callbacks
        for sub in self._subscriptions:
            try:
                if sub.callback and sub.filters.match(event):
                    sub.callback(nostr_event)
            except Exception as e:
                logger.error("NostrManager: subscription callback error: %s", e)

        # Post-event background handlers (e.g. persistence) run after UI handlers.
        if event.kind in self._post_event_handlers:
            for cb in self._post_event_handlers[event.kind]:
                try:
                    cb(nostr_event)
                except Exception as e:
                    logger.error("NostrManager: post-event handler error: %s", e)

        if self._events_updated_cb:
            try:
                self._events_updated_cb()
            except Exception as e:
                logger.error("NostrManager: events_updated callback error: %s", e)

    def _process_nwc_event(self, event):
        """Decrypt and process an NWC response/notification event."""
        try:
            decrypted = self._nwc_private_key.decrypt_message(
                event.content,
                event.public_key,
            )
            if __debug__:
                logger.debug("NostrManager: decrypted NWC: %s", decrypted)
            response = json.loads(decrypted)
            result = response.get("result")
            if result:
                if result.get("balance") is not None:
                    new_balance = round(int(result["balance"]) / 1000)
                    logger.info("NostrManager: NWC balance: %s", new_balance)
                    if self._polls_since_last_event > 0:
                        if __debug__:
                            logger.debug("NostrManager: NWC watchdog counter reset (balance)")
                    self._polls_since_last_event = 0
                    if self._nwc_balance_cb:
                        self._nwc_balance_cb(new_balance)

                elif result.get("transactions") is not None:
                    logger.info("NostrManager: NWC transactions received")
                    if self._polls_since_last_event > 0:
                        if __debug__:
                            logger.debug("NostrManager: NWC watchdog counter reset (transactions)")
                    self._polls_since_last_event = 0
                    if self._nwc_payments_cb:
                        self._nwc_payments_cb(result["transactions"])

            notification = response.get("notification")
            if notification:
                if self._nwc_notification_cb:
                    self._nwc_notification_cb(notification)

        except Exception as e:
            logger.error("NostrManager: NWC event processing error: %s", e)
            import sys
            sys.print_exception(e)

    def _handle_nwc_static_receive_code(self, lud16):
        if self._nwc_notification_cb:
            self._nwc_notification_cb({"static_receive_code": lud16})

    async def _reconnect_relay(self):
        """Watchdog reconnect: close, wait, reopen, re-subscribe."""
        logger.warning("NostrManager: watchdog reconnecting relay (silent for %s polls)",
            self._polls_since_last_event)
        try:
            await self.relay_manager.close_connections()
        except Exception as e:
                    logger.warning("NostrManager: close during reconnect failed: %s", e)

        await TaskManager.sleep(2)

        old_relay_urls = list(self.relay_manager.relays.keys()) if hasattr(self.relay_manager, 'relays') else []
        self.relay_manager = RelayManager()
        self._relay_connected_state = {}
        for url in old_relay_urls:
            self.relay_manager.add_relay(url)

        try:
            await self.relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE})
        except Exception as e:
            logger.warning("NostrManager: open_connections during reconnect failed: %s", e)

        for _ in range(50):
            await TaskManager.sleep(0.1)
            if not self.keep_running:
                return
            if self.relay_manager.connected_relays() > 0:
                break

        connected = [url for url, relay in self.relay_manager.relays.items() if relay.connected]
        self._subscription_ids = {}
        if connected:
            self._send_subscriptions_to_relays(connected)
        self._relay_connected_state = {
            url: relay.connected for url, relay in self.relay_manager.relays.items()
        }

        self._polls_since_last_event = 0

    async def _sync_relays(self):
        """Hot-add relays configured after the manager started.

        Existing relays stay connected; new ones are opened and all current
        subscriptions are re-published so the new relays receive them too.
        """
        self._relays_dirty = False
        if self.relay_manager is None:
            return

        new_urls = []
        existing = set(self.relay_manager.relays.keys())
        for url in self._default_relays + self._nwc_relays:
            if url and url not in existing:
                self.relay_manager.add_relay(url)
                new_urls.append(url)
        if not new_urls:
            return

        logger.info("NostrManager: adding new relays: %s", new_urls)
        await self.relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE})

        new_relays = [self.relay_manager.relays[url] for url in new_urls]
        for _ in range(300):
            await TaskManager.sleep(0.1)
            if not self.keep_running:
                return
            if all(r.connected or r.error_counter > 0 for r in new_relays):
                break

        # Re-publish existing subscriptions so the new relays receive them.
        for sub in self._subscriptions:
            sub_id = self._subscription_ids.get(sub.name)
            if sub_id is None:
                sub_id = _make_subscription_id("mpos_sub_")
                self._subscription_ids[sub.name] = sub_id
            self._publish_subscription(sub, sub_id)

        if self._nwc_configured and self._nwc_sub_id:
            self._nwc_filters = Filters([Filter(
                kinds=[23195, 23196],
                authors=[self._nwc_wallet_pubkey],
                pubkey_refs=[self._nwc_private_key.public_key.hex()]
            )])
            self.relay_manager.add_subscription(self._nwc_sub_id, self._nwc_filters)
            self.relay_manager.publish_message(json.dumps(
                [ClientMessageType.REQUEST, self._nwc_sub_id] + self._nwc_filters.to_json_array()))

        self._relay_connected_state.update({
            url: relay.connected for url, relay in self.relay_manager.relays.items()
        })

        if self._relay_list_pending:
            try:
                self.publish_relay_list()
            except Exception as e:
                logger.error("NostrManager: relay list publish error: %s", e)

    # --- NWC request methods ---

    def nwc_fetch_balance(self):
        if not self._nwc_configured:
            return
        balance_request = {"method": "get_balance", "params": {}}
        self._publish_signed_dm(
            self._nwc_private_key,
            self._nwc_wallet_pubkey,
            json.dumps(balance_request),
            kind=23194,
        )

    def nwc_fetch_payments(self):
        if not self._nwc_configured:
            return
        list_transactions = {
            "method": "list_transactions",
            "params": {"limit": self._nwc_list_limit}
        }
        self._publish_signed_dm(
            self._nwc_private_key,
            self._nwc_wallet_pubkey,
            json.dumps(list_transactions),
            kind=23194,
        )


class NostrClientService(Service):
    """Generic boot-time starter for the shared NostrManager.

    This service intentionally does no app-specific setup: no shared
    preferences, no default relays, no persistence. Apps that need a
    particular relay set or behavior should provide their own boot service
    and call NostrManager's configuration methods directly.
    """

    def onStart(self, intent):
        if __debug__:
            logger.debug("NostrClientService: starting NostrManager")
        NostrManager.get_instance().start()

    def onDestroy(self):
        if __debug__:
            logger.debug("NostrClientService: stopping NostrManager")
        NostrManager.get_instance().stop()
