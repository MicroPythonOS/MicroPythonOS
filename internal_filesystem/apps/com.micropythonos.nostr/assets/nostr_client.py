# nostr_client.py — Nostr event formatting utilities.
# NostrClient has been superseded by NostrManager in nostr_service.py.
# This module keeps NostrEvent and formatting helpers for backward compat;
# new code should import from nostr_service directly.

from nostr_service import (
    EVENT_KIND_NAMES,
    get_kind_name,
    format_timestamp,
    format_tags,
    NostrEvent,
    NostrManager,
)
