import logging

from mpos import (
    Intent,
    Notification,
    NotificationManager,
    SharedPreferences,
    get_foreground_app,
)

from .chat_model import KIND_CHANNEL_MESSAGE

logger = logging.getLogger(__name__)


def post_chat_notification(app_fullname, chat, message):
    """Post a notification for a new chat message, unless the app is in the
    foreground, notifications are disabled for this chat, or the chat is
    already open.
    """
    # Standard mobile-style behavior: don't notify while the app is visible.
    if get_foreground_app() == app_fullname:
        return

    # Honor the per-chat notification toggle (default enabled).
    prefs = SharedPreferences(app_fullname)
    key = f"notifications:{chat.chat_id}"
    if prefs.get_int(key, 1) == 0:
        return

    try:
        from .chat_activity import ChatActivity
    except Exception as e:
        logger.error("Could not import ChatActivity for notification: %s", e)
        return

    # Don't ping the user while they are already reading this chat.
    if ChatActivity.currently_open_chat_id == chat.chat_id:
        return

    try:
        intent = Intent(activity_class=ChatActivity)
        intent.putExtra("chat_id", chat.chat_id)
        intent.putExtra("kind", chat.kind)
        if chat.kind == KIND_CHANNEL_MESSAGE:
            intent.putExtra("channel_id", chat.channel_id)
        else:
            intent.putExtra("peer_pubkey", chat.peer_pubkey)
        NotificationManager.notify(
            Notification(
                notification_id=f"nostr:{chat.chat_id}",
                title=chat.title,
                text=message.short_preview(40),
                intent=intent,
                app_fullname=app_fullname,
            )
        )
    except Exception as e:
        logger.error("Failed to post chat notification: %s", e)
