import logging

from .chat_model import KIND_CHANNEL_MESSAGE, KIND_DM, KIND_NIP17_CHAT
from .event_store import _current_nostr_ts

logger = logging.getLogger(__name__)

# Default relays used when the user has not configured one.
DEFAULT_RELAYS = [
    "wss://relay.0xchat.com",
    "wss://relay.damus.io",
    "wss://relay.primal.net",
]
DEFAULT_RELAY = DEFAULT_RELAYS[0]

# Subscription tuning.
LOOKBACK_WINDOW_SECONDS = 24 * 60 * 60  # 24 hours
# NIP-17 gift-wraps randomize created_at within a 2-day window, so the
# subscription window must be wider than the chat-history-driven window.
NIP17_LOOKBACK_WINDOW_SECONDS = 3 * 24 * 60 * 60  # 3 days
OVERLAP_SECONDS = 60  # margin when using since=last_known_ts
SUBSCRIPTION_LIMIT_INITIAL = 200
SUBSCRIPTION_LIMIT_NIP17 = 50


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


def _dm_subscription_since(now, chats):
    """Return the since= value for the global DM subscription.

    We want the latest safe timestamp that still covers possible new
    messages: the newest DM/NIP-17 activity minus a small overlap, but
    never older than the configured lookback window.
    """
    dm_since = now - LOOKBACK_WINDOW_SECONDS
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
        default lookback window.
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

    now = _current_nostr_ts()

    if dm_since is None:
        chats = store.get_chats() if store is not None else []
        dm_since = _dm_subscription_since(now, chats)

    # NIP-17 gift-wraps use randomized created_at timestamps, so they may be
    # older than the newest chat activity. Use a fixed 3-day window instead of
    # the chat-history-driven dm_since.
    nip17_since = now - NIP17_LOOKBACK_WINDOW_SECONDS
    logger.info(
        "Nostr subscriptions: dm_since=%s nip17_since=%s (now=%s)",
        dm_since,
        nip17_since,
        now,
    )

    try:
        manager.subscribe_dms(since=dm_since, limit=SUBSCRIPTION_LIMIT_INITIAL)
    except Exception as e:
        logger.error("DM subscription failed: %s", e)

    try:
        manager.subscribe_nip17_dms(
            since=nip17_since, limit=SUBSCRIPTION_LIMIT_NIP17
        )
    except Exception as e:
        logger.error("NIP-17 subscription failed: %s", e)

    if store is not None:
        for chat in store.get_chats():
            if chat.kind == KIND_CHANNEL_MESSAGE and chat.channel_id:
                since = chat.last_ts - OVERLAP_SECONDS if chat.last_ts else now - LOOKBACK_WINDOW_SECONDS
                try:
                    manager.subscribe_channel(
                        chat.channel_id,
                        name=chat.chat_id,
                        since=since,
                        limit=SUBSCRIPTION_LIMIT_INITIAL,
                    )
                except Exception as e:
                    logger.error("Channel subscription failed: %s", e)
