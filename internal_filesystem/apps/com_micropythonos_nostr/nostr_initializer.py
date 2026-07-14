import json
import logging
import time as _time

from .chat_model import (
    DEFAULT_CHANNEL_ID,
    DEFAULT_CHANNEL_NAME,
    KIND_CHANNEL_MESSAGE,
    KIND_DM,
    KIND_NIP17_CHAT,
    channel_chat_id,
)
from .event_store import _current_nostr_ts

logger = logging.getLogger(__name__)

# Default relays used when the user has not configured one.
DEFAULT_RELAYS = [
    "wss://relay.0xchat.com",
    "wss://relay.damus.io",
    "wss://relay.primal.net",
]
DEFAULT_RELAY = DEFAULT_RELAYS[0]

# Subscription tuning. These constants are the knobs for how much history is
# fetched when the device comes online and how many events are requested.
# DM chats are expected to be lower volume, so a longer lookback is fine.
# Group chats can be very high volume, so keep the window short and the limit
# low to avoid notification storms and wasted bandwidth.
DM_FETCH_SINCE_MINUTES = 2 * 24 * 60  # 2 days
DM_FETCH_LIMIT = 50

GROUP_FETCH_SINCE_MINUTES = 10  # 10 minutes
GROUP_FETCH_LIMIT = 10

# NIP-17 gift-wraps randomize created_at within a 2-day window, so the
# subscription window must be slightly wider than the DM window.
NIP17_FETCH_SINCE_MINUTES = DM_FETCH_SINCE_MINUTES + 24 * 60  # 3 days
NIP17_FETCH_LIMIT = 50

OVERLAP_SECONDS = 60  # margin when using since=last_known_ts

# When a subscription is first published we treat all messages received for
# an empty chat (last_ts == 0) as backfill. This grace window gives the batch
# a chance to land without making a sound for every message.
FIRST_FETCH_GRACE_SECONDS = 20

# Bounds for user-provided overrides from SharedPreferences.
_FETCH_SINCE_MIN_MINUTES = 1
_FETCH_SINCE_MAX_MINUTES = 7 * 24 * 60  # 1 week
_FETCH_LIMIT_MIN = 1
_FETCH_LIMIT_MAX = 500


def ensure_identity(prefs):
    """Return the user's nostr nsec from prefs, generating one if missing."""
    nsec = prefs.get_string("nostr_nsec")
    if not nsec:
        from nostr.key import PrivateKey

        nsec = PrivateKey().bech32()
        prefs.edit().put_string("nostr_nsec", nsec).commit()
        if __debug__:
            logger.debug("Generated new nostr nsec")
    return nsec


def _pref_minutes(prefs, key, default):
    """Return a user override for a since= value in minutes, clamped."""
    try:
        value = int(prefs.get_string(key, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(_FETCH_SINCE_MIN_MINUTES, min(value, _FETCH_SINCE_MAX_MINUTES))


def _pref_limit(prefs, key, default):
    """Return a user override for a limit= value, clamped."""
    try:
        value = int(prefs.get_string(key, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(_FETCH_LIMIT_MIN, min(value, _FETCH_LIMIT_MAX))


def _dm_fetch_settings(prefs):
    return {
        "since_minutes": _pref_minutes(prefs, "dm_fetch_since_min", DM_FETCH_SINCE_MINUTES),
        "limit": _pref_limit(prefs, "dm_fetch_limit", DM_FETCH_LIMIT),
    }


def _group_fetch_settings(prefs):
    return {
        "since_minutes": _pref_minutes(prefs, "group_fetch_since_min", GROUP_FETCH_SINCE_MINUTES),
        "limit": _pref_limit(prefs, "group_fetch_limit", GROUP_FETCH_LIMIT),
    }


def _nip17_fetch_settings(prefs):
    return {
        "since_minutes": _pref_minutes(prefs, "nip17_fetch_since_min", NIP17_FETCH_SINCE_MINUTES),
        "limit": _pref_limit(prefs, "nip17_fetch_limit", NIP17_FETCH_LIMIT),
    }


def _chat_lookback_seconds(prefs, kind):
    """Return the fallback lookback window in seconds for a chat kind."""
    if kind == KIND_CHANNEL_MESSAGE:
        return _group_fetch_settings(prefs)["since_minutes"] * 60
    return _dm_fetch_settings(prefs)["since_minutes"] * 60


def _dm_subscription_since(now, chats, since_minutes):
    """Return the since= value for the global DM subscription.

    We want the latest safe timestamp that still covers possible new
    messages: the newest DM/NIP-17 activity minus a small overlap, but
    never older than the configured lookback window.
    """
    fallback = now - (since_minutes * 60)
    dm_since = fallback
    for chat in chats:
        if chat.kind in (KIND_DM, KIND_NIP17_CHAT) and chat.last_ts:
            dm_since = max(dm_since, chat.last_ts - OVERLAP_SECONDS)
    return dm_since


def configure_nostr_manager(prefs, manager, store=None, dm_since=None):
    """Start/configure the shared NostrManager for the Nostr app.

    Ensures identity and default relays, then subscribes to DMs, NIP-17
    gift-wraps, and (when a store is supplied) all known public channels.

    Parameters
    ----------
    prefs : SharedPreferences
        The app's shared preferences.
    manager : NostrManager
        The singleton manager to configure.
    store : EventStore, optional
        When provided, channel subscriptions are also refreshed from the
        store's known chats.
    dm_since : int, optional
        Override the ``since`` timestamp used for DM/NIP-17 subscriptions.
        When omitted it is computed from the store's chat history or the
        default DM lookback window.
    """
    if not manager.is_running():
        manager.start()

    nsec = ensure_identity(prefs)
    relay = prefs.get_string("nostr_relay") or DEFAULT_RELAYS
    try:
        manager.configure_identity(nsec, relays=relay)
    except Exception as e:
        logger.error("Failed to configure identity: %s", e)
        return

    dm_settings = _dm_fetch_settings(prefs)
    group_settings = _group_fetch_settings(prefs)
    nip17_settings = _nip17_fetch_settings(prefs)

    now = _current_nostr_ts()

    if dm_since is None:
        chats = store.get_chats() if store is not None else []
        dm_since = _dm_subscription_since(now, chats, dm_settings["since_minutes"])

    nip17_since = now - (nip17_settings["since_minutes"] * 60)
    logger.info(
        "Nostr subscriptions: dm_since=%s nip17_since=%s (now=%s)",
        dm_since,
        nip17_since,
        now,
    )

    # Track the start of a fresh fetch window so empty chats can be filled
    # silently without making a sound for every historical message.
    manager._initial_fetch_deadline = _time.time() + FIRST_FETCH_GRACE_SECONDS
    manager._silent_initial_chats = set()

    try:
        manager.subscribe_dms(since=dm_since, limit=dm_settings["limit"])
    except Exception as e:
        logger.error("DM subscription failed: %s", e)

    try:
        manager.subscribe_nip17_dms(
            since=nip17_since, limit=nip17_settings["limit"]
        )
    except Exception as e:
        logger.error("NIP-17 subscription failed: %s", e)

    if store is not None:
        _load_channel_directory(store)
        # Migration (v0.15.1): fix stale "#MicroPythonOS" title leftover from
        # earlier versions that incorrectly prefixed the default channel name
        # with "#". Remove after 2026-08-20.
        chat_id = channel_chat_id(DEFAULT_CHANNEL_ID)
        chat = store.get_chat(chat_id)
        if chat is not None and chat.title == f"#{DEFAULT_CHANNEL_NAME}":
            store.update_chat_title(chat_id, DEFAULT_CHANNEL_NAME)

        # Ensure the default public channel exists so boot-time notifications
        # and messages are received even before the user opens the UI.
        store.get_or_create_channel(
            DEFAULT_CHANNEL_ID, title=DEFAULT_CHANNEL_NAME
        )
        for chat in store.get_chats():
            if chat.kind == KIND_CHANNEL_MESSAGE and chat.channel_id:
                since = chat.last_ts - OVERLAP_SECONDS if chat.last_ts else now - (group_settings["since_minutes"] * 60)
                try:
                    manager.subscribe_channel(
                        chat.channel_id,
                        name=chat.chat_id,
                        since=since,
                        limit=group_settings["limit"],
                    )
                except Exception as e:
                    logger.error("Channel subscription failed: %s", e)


_CHANNELS_CONFIG_PATH = "prefs/com_micropythonos_nostr/channels.json"


def _load_channel_directory(store):
    """Seed the store with channels from the local channels.json directory."""
    try:
        with open(_CHANNELS_CONFIG_PATH, "r") as f:
            channels = json.load(f)
    except (OSError, ValueError):
        return
    for entry in channels:
        cid = entry.get("id")
        name = entry.get("name")
        if cid and name:
            store.get_or_create_channel(cid, title=name)


def search_channel_directory(search_term):
    """Return matching channels from the local channels.json directory."""
    results = []
    try:
        with open(_CHANNELS_CONFIG_PATH, "r") as f:
            channels = json.load(f)
    except (OSError, ValueError):
        return results
    lower = search_term.lower()
    for entry in channels:
        name = entry.get("name", "")
        cid = entry.get("id", "")
        about = entry.get("about", "")
        if lower in name.lower():
            results.append((cid, name, about))
    return results
