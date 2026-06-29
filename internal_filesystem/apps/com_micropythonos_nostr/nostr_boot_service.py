import logging

from mpos import Service, SharedPreferences

from .chat_model import (
    DEFAULT_CHANNEL_ID,
    KIND_CHANNEL_MESSAGE,
    KIND_DM,
    KIND_NIP17_CHAT,
    Message,
    channel_id_from_event,
    chat_id_for_event,
    participants_from_nip17_event,
    peer_from_dm_event,
    subject_from_nip17_event,
)
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
    """

    def __init__(self):
        super().__init__()
        self._store = None
        self._persist_cb = None

    def onStart(self, intent):
        prefs = SharedPreferences(self.appFullName)
        if prefs.get_int("connect_at_boot", 1) == 0:
            if __debug__:
                logger.debug("NostrBootService: connect_at_boot disabled, skipping")
            return

        if __debug__:
            logger.debug("NostrBootService: starting Nostr initialization")

        manager = NostrManager.get_instance()
        self._store = EventStore(self.appFullName)
        configure_nostr_manager(prefs, manager, store=self._store)

        self._persist_cb = lambda e: self._persist_event(e)
        manager.register_post_event_handler(KIND_DM, self._persist_cb)
        manager.register_post_event_handler(KIND_CHANNEL_MESSAGE, self._persist_cb)
        manager.register_post_event_handler(KIND_NIP17_CHAT, self._persist_cb)

    def onDestroy(self):
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
            chat_id = chat_id_for_event(nostr_event.event, own)
            if chat_id is None:
                return

            kind = nostr_event.kind
            if kind == KIND_DM:
                content = nostr_event.get_display_content()
            else:
                content = nostr_event.content

            chat = self._store.get_chat(chat_id)
            if chat is None:
                if kind == KIND_DM:
                    peer = peer_from_dm_event(nostr_event.event, own)
                    chat = self._store.get_or_create_dm(own or "", peer)
                elif kind == KIND_NIP17_CHAT:
                    participants = participants_from_nip17_event(
                        nostr_event.event, own
                    )
                    title = subject_from_nip17_event(nostr_event.event)
                    if len(participants) == 1:
                        chat = self._store.get_or_create_dm(own or "", participants[0])
                    else:
                        chat = self._store.get_or_create_nip17_group(
                            participants, title=title
                        )
                else:
                    channel_id = channel_id_from_event(nostr_event.event)
                    chat = self._store.get_or_create_channel(
                        channel_id or DEFAULT_CHANNEL_ID
                    )

            message = Message(
                event_id=nostr_event.event.id,
                ts=nostr_event.created_at,
                pubkey=nostr_event.public_key,
                content=content,
                kind=kind,
            )
            self._store.add_message(chat_id, message, mark_unread=True)
        except Exception as e:
            logger.error("Failed to persist Nostr event: %s", e)
            import sys

            sys.print_exception(e)
