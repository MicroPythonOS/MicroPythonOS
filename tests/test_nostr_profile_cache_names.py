"""ProfileCache name lookup used by the 'Group' mode of NewChatActivity."""

import sys
import unittest

sys.path.append("apps")

from com_micropythonos_nostr.profile_cache import MAINTAINER_HEX, ProfileCache


class TestFindPubkeysByName(unittest.TestCase):
    def _cache(self):
        cache = ProfileCache()
        cache._profiles = {
            "b" * 64: {"display_name": "Bob Builder", "name": "bob"},
            "c" * 64: {"name": "carol"},
            "d" * 64: {"display_name": "Carol", "name": "carol2"},
        }
        return cache

    def test_matches_display_name_or_name_case_insensitively(self):
        cache = self._cache()
        self.assertEqual(cache.find_pubkeys_by_name("bob builder"), ["b" * 64])
        self.assertEqual(cache.find_pubkeys_by_name("BOB"), ["b" * 64])
        self.assertEqual(cache.find_pubkeys_by_name("carol2"), ["d" * 64])

    def test_returns_every_match(self):
        cache = self._cache()
        self.assertEqual(sorted(cache.find_pubkeys_by_name("Carol")), ["c" * 64, "d" * 64])

    def test_unknown_name_and_blank_give_nothing(self):
        cache = self._cache()
        self.assertEqual(cache.find_pubkeys_by_name("nobody"), [])
        self.assertEqual(cache.find_pubkeys_by_name("  "), [])

    def test_maintainer_profile_is_known(self):
        cache = self._cache()
        self.assertEqual(cache.find_pubkeys_by_name("Thomas Farstrike"), [MAINTAINER_HEX])


if __name__ == "__main__":
    unittest.main()
