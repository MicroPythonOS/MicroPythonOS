# Shared constants for the MicroPythonOS Nostr client.

APP_FULLNAME = "com.micropythonos.nostr"

# Default relays used when the user has not configured one.
DEFAULT_RELAYS = [
    "wss://nos.lol",
    "wss://relay.snort.social",
    "wss://relay.nostr.band",
    "wss://relay.damus.io",
    "wss://relay.primal.net"
]
DEFAULT_RELAY = DEFAULT_RELAYS[0]

# Auto-joined public channel (#MicroPythonOS, NIP-28).
DEFAULT_CHANNEL_ID = "cbf20cd9212aea3c7d399777b69cec750a0109edd831001a5011d892268a9481"
DEFAULT_CHANNEL_NAME = "MicroPythonOS"
DEFAULT_CHANNEL_ABOUT = "MicroPythonOS community chat"

# Kind codes used by this client.
KIND_DM = 4
KIND_CHANNEL_CREATE = 40
KIND_CHANNEL_META = 41
KIND_CHANNEL_MESSAGE = 42

# Subscription tuning.
LOOKBACK_WINDOW_SECONDS = 24 * 60 * 60  # 24 hours
OVERLAP_SECONDS = 60  # margin when using since=last_known_ts
SUBSCRIPTION_LIMIT_INITIAL = 200

# Storage tuning.
DEFAULT_MAX_MESSAGES_PER_CHAT = 200
MAX_MESSAGES_PER_CHAT_MIN = 10
MAX_MESSAGES_PER_CHAT_MAX = 2000

# Index flush period (milliseconds). Incoming events are appended to the
# per-chat JSONL immediately; the lightweight chat index is batched.
INDEX_FLUSH_MS = 5000

# Chat ID prefixes.
CHAT_ID_DM_PREFIX = "dm_"
CHAT_ID_CHANNEL_PREFIX = "channel_"

# JSONL/index file layout under prefs/<APP_FULLNAME>/cache/.
CACHE_DIR = "cache"
INDEX_FILENAME = "index.json"
OUTBOX_FILENAME = "outbox.jsonl"
CHAT_FILE_SUFFIX = ".jsonl"
STORE_VERSION = 1
