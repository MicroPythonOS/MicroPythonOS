import logging

from mpos import Service, SharedPreferences, TaskManager

from .chat_model import (
    KIND_CHANNEL_MESSAGE,
    KIND_DM,
    KIND_NIP17_CHAT,
    Message,
    content_from_event,
    get_or_create_chat_for_event,
)
from .chat_notifications import post_chat_notification
from .event_store import EventStore
from .nostr_initializer import configure_nostr_manager
from .nostr_service import NostrManager

logger = logging.getLogger(__name__)


class NostrBootService(Service):
    """Boot-time service for the Nostr app.

    When ``connect_at_boot`` is enabled in SharedPreferences, this service
    initializes the shared NostrManager, connects to the configured relays,
    and starts the DM / channel subscriptions so messages can arrive before
    the user has opened the app. It also registers a post-event handler that
    persists incoming events to the app's EventStore.

    With ``connect_at_boot`` disabled, the service exits immediately and all
    initialization is deferred until the user manually starts the app.

    On a real device the relay handshake is deferred by 30 seconds so Wi-Fi
    and system services have time to settle first. In test harnesses that run
    without a live event loop, initialization happens synchronously so other
    tests are not affected.
    """

    # Delay before connecting at boot so Wi-Fi / system services have time to
    # settle before the network-heavy relay handshake starts.
    STARTUP_DELAY_MS = 30 * 1000

    def __init__(self):
        super().__init__()
        self._store = None
        self._persist_cb = None
        self._running = True

    def onStart(self, intent):
        prefs = SharedPreferences(self.appFullName)
        if prefs.get_int("connect_at_boot", 1) == 0:
            if __debug__:
                logger.debug("NostrBootService: connect_at_boot disabled, skipping")
            return

        if TaskManager.disabled:
            # Test harness without a live asyncio loop: initialize now.
            self._start_now(prefs)
        else:
            if __debug__:
                logger.debug("NostrBootService: scheduling delayed start")
            TaskManager.create_task(self._delayed_start(prefs))

    def _start_now(self, prefs):
        if __debug__:
            logger.debug("NostrBootService: starting Nostr initialization")

        manager = NostrManager.get_instance()
        self._store = EventStore(self.appFullName)
        self._persist_cb = lambda e: self._persist_event(e)
        manager.register_post_event_handler(KIND_DM, self._persist_cb)
        manager.register_post_event_handler(KIND_CHANNEL_MESSAGE, self._persist_cb)
        manager.register_post_event_handler(KIND_NIP17_CHAT, self._persist_cb)
        configure_nostr_manager(prefs, manager, store=self._store)

    async def _delayed_start(self, prefs):
        await TaskManager.sleep_ms(self.STARTUP_DELAY_MS)
        if not self._running:
            return
        if prefs.get_int("connect_at_boot", 1) == 0:
            return
        self._start_now(prefs)

    def onDestroy(self):
        self._running = False
        if self._persist_cb is not None:
            manager = NostrManager.get_instance()
            manager.unregister_post_event_handler(KIND_DM, self._persist_cb)
            manager.unregister_post_event_handler(
                KIND_CHANNEL_MESSAGE, self._persist_cb
            )
            manager.unregister_post_event_handler(KIND_NIP17_CHAT, self._persist_cb)
            self._persist_cb = None
        if self._store is not None:
            self._store.flush_index()

    def _persist_event(self, nostr_event):
        """Persist an event that made it past the normal UI handlers."""
        if self._store is None:
            return
        try:
            manager = NostrManager.get_instance()
            own = manager.get_own_pubkey_hex()
            chat = get_or_create_chat_for_event(self._store, nostr_event, own)
            if chat is None:
                return

            message = Message(
                event_id=nostr_event.event.id,
                ts=nostr_event.created_at,
                pubkey=nostr_event.public_key,
                content=content_from_event(nostr_event),
                kind=nostr_event.kind,
            )
            is_new = self._store.add_message(chat.chat_id, message, mark_unread=True)
            if is_new:
                post_chat_notification(self.appFullName, chat, message)
        except Exception as e:
            logger.error("Failed to persist Nostr event: %s", e)
            import sys

            sys.print_exception(e)
