import json
import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_MAX_PROFILES = 350

MAINTAINER_HEX = "181137054fe60df5168976311f0bf44dbe4bd4d2e0af69325dfee9fa81a8cbda"
MAINTAINER_AVATAR_PATH = "M:apps/com_micropythonos_nostr/npub1rqgnwp2_64x64.png"

MAINTAINER_PROFILE = {
    "name": "ThomasFarstrike",
    "display_name": "Thomas Farstrike",
    "about": "Build it, create it, make it.",
    "picture_path": MAINTAINER_AVATAR_PATH,
}

PROFILES_FILENAME = "profiles.json"
CACHE_DIR = "cache"


class ProfileCache:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if getattr(self, "_inited", False):
            return
        self._profiles = {}
        self._max_profiles = DEFAULT_MAX_PROFILES
        self._cache_dir = None
        self._manager = None
        self._pending_subscriptions = set()
        self._loaded = False
        self._inited = True

    def init(self, app_fullname, manager, max_profiles=None):
        if self._loaded:
            return
        self._cache_dir = f"prefs/{app_fullname}/{CACHE_DIR}"
        self._manager = manager
        if max_profiles is not None:
            self._max_profiles = max_profiles
        self._ensure_dirs()
        self._load()
        self._ensure_maintainer()
        self._register_handler()
        self._loaded = True
        if __debug__:
            logger.debug("ProfileCache initialised (%s profiles)", len(self._profiles))

    def _ensure_dirs(self):
        parts = self._cache_dir.split("/")
        path = ""
        for part in parts:
            if not part:
                continue
            path = f"{path}/{part}" if path else part
            try:
                os.mkdir(path)
            except OSError:
                pass

    def _load(self):
        path = f"{self._cache_dir}/{PROFILES_FILENAME}"
        try:
            with open(path, "r") as f:
                data = json.load(f)
            self._profiles = data.get("profiles", {})
            self._max_profiles = data.get("max_profiles", self._max_profiles)
        except (OSError, ValueError):
            self._profiles = {}

    def _save(self):
        path = f"{self._cache_dir}/{PROFILES_FILENAME}"
        self._ensure_dirs()
        data = {"profiles": self._profiles, "max_profiles": self._max_profiles}
        try:
            with open(path, "w") as f:
                json.dump(data, f)
        except OSError as e:
            logger.error("Failed to save profiles: %s", e)

    def _ensure_maintainer(self):
        if MAINTAINER_HEX not in self._profiles:
            profile = dict(MAINTAINER_PROFILE)
            profile["added_at"] = 0
            self._profiles[MAINTAINER_HEX] = profile
            self._save()

    def _register_handler(self):
        self._manager.register_event_handler(0, self._on_metadata_event)

    def _on_metadata_event(self, nostr_event):
        try:
            content = json.loads(nostr_event.content)
        except (ValueError, TypeError):
            return
        pubkey = nostr_event.public_key
        profile = {}
        if "display_name" in content:
            profile["display_name"] = content["display_name"]
        if "name" in content:
            profile["name"] = content["name"]
        if "about" in content:
            profile["about"] = content["about"]
        if "picture" in content:
            profile["picture_url"] = content["picture"]
        if not profile:
            return
        profile["added_at"] = nostr_event.created_at
        self._profiles[pubkey] = profile
        self._prune_if_needed()
        self._save()
        if __debug__:
            logger.debug("Profile updated for %s", pubkey[:16])

    def _prune_if_needed(self):
        while len(self._profiles) > self._max_profiles:
            oldest_key = min(self._profiles, key=lambda k: self._profiles[k].get("added_at", 0))
            if oldest_key == MAINTAINER_HEX:
                break
            del self._profiles[oldest_key]

    def get_display_name(self, pubkey):
        hex_pubkey = self._to_hex(pubkey)
        if not hex_pubkey:
            return None
        profile = self._profiles.get(hex_pubkey)
        if profile:
            return profile.get("display_name") or profile.get("name")
        self._maybe_subscribe(hex_pubkey)
        return None

    def get_profile(self, pubkey):
        hex_pubkey = self._to_hex(pubkey)
        if not hex_pubkey:
            return None
        profile = self._profiles.get(hex_pubkey)
        if profile:
            return profile
        self._maybe_subscribe(hex_pubkey)
        return None

    def _maybe_subscribe(self, hex_pubkey):
        if hex_pubkey in self._pending_subscriptions:
            return
        self._pending_subscriptions.add(hex_pubkey)
        try:
            self._manager.subscribe_metadata(hex_pubkey)
        except Exception as e:
            logger.warning("Failed to subscribe profile %s: %s", hex_pubkey[:16], e)

    def set_max_profiles(self, max_profiles):
        self._max_profiles = max_profiles
        if self._cache_dir is not None:
            self._prune_if_needed()
            self._save()

    def get_max_profiles(self):
        return self._max_profiles

    @staticmethod
    def _to_hex(pubkey):
        if not pubkey:
            return None
        if len(pubkey) == 64 and all(c in "0123456789abcdef" for c in pubkey):
            return pubkey
        if pubkey.lower().startswith("npub1"):
            try:
                from nostr.key import PublicKey

                return PublicKey.from_npub(pubkey).hex()
            except Exception:
                return None
        return None
