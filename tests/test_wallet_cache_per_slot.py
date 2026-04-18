"""
Unit tests for the per-slot wallet_cache in the Lightning Piggy app.

Targets LightningPiggyApp PR #26 (multi-wallet). Slot 1 keeps the
unsuffixed cache keys for back-compat; slot 2 mirrors them with a `_2`
suffix so both wallets can be cached side-by-side and swapping between
them repaints instantly without waiting for the network.

Usage:
    Desktop: ./tests/unittest.sh tests/test_wallet_cache_per_slot.py
    Device:  ./tests/unittest.sh tests/test_wallet_cache_per_slot.py --ondevice
"""

import os
import sys
import unittest

sys.path.append("apps/com.lightningpiggy.displaywallet/assets/")

try:
    import wallet_cache
    from payment import Payment
    from unique_sorted_list import UniqueSortedList
    # Detect per-slot support by probing: pre-PR-#26 versions reject `slot=`.
    # MicroPython doesn't include inspect.signature, hence the direct probe.
    try:
        wallet_cache.save_cache(slot=1)  # no-op call — no fields provided
        _HAVE_PER_SLOT = True
    except TypeError:
        _HAVE_PER_SLOT = False
except ImportError:
    _HAVE_PER_SLOT = False


CACHE_FILE = "data/com.lightningpiggy.displaywallet/cache.json"


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


@unittest.skipUnless(_HAVE_PER_SLOT, "wallet_cache per-slot support not installed (PR #26 not landed)")
class TestWalletCachePerSlot(unittest.TestCase):

    def setUp(self):
        # Scrub any on-disk cache state from previous runs.
        _remove(CACHE_FILE)
        # The module-level _cache object loaded from disk at import; reset its
        # in-memory dict too so we start each test with a blank slate.
        wallet_cache._cache.data = {}

    def tearDown(self):
        _remove(CACHE_FILE)
        wallet_cache._cache.data = {}

    # ---- balance -----------------------------------------------------

    def test_slot_1_uses_unsuffixed_keys_back_compat(self):
        wallet_cache.save_cache(balance=3113, slot=1)
        self.assertEqual(wallet_cache._cache.data.get("balance"), 3113)
        self.assertFalse("balance_2" in wallet_cache._cache.data)

    def test_slot_2_uses_suffixed_keys(self):
        wallet_cache.save_cache(balance=6884, slot=2)
        self.assertEqual(wallet_cache._cache.data.get("balance_2"), 6884)
        self.assertFalse("balance" in wallet_cache._cache.data)

    def test_both_slots_coexist_without_clobbering(self):
        wallet_cache.save_cache(balance=3113, slot=1)
        wallet_cache.save_cache(balance=6884, slot=2)
        self.assertEqual(wallet_cache.load_cached_balance(slot=1), 3113)
        self.assertEqual(wallet_cache.load_cached_balance(slot=2), 6884)

    def test_slot_default_is_1(self):
        # Pre-PR-#26 callers passed no slot arg; they should still target slot 1.
        wallet_cache.save_cache(balance=42)
        self.assertEqual(wallet_cache.load_cached_balance(), 42)
        self.assertEqual(wallet_cache.load_cached_balance(slot=1), 42)
        self.assertIsNone(wallet_cache.load_cached_balance(slot=2))

    # ---- static_receive_code -----------------------------------------

    def test_static_receive_code_per_slot(self):
        wallet_cache.save_cache(static_receive_code="LNURL1...", slot=1)
        wallet_cache.save_cache(static_receive_code="bitcoin:bc1q...", slot=2)
        self.assertEqual(wallet_cache.load_cached_static_receive_code(slot=1), "LNURL1...")
        self.assertEqual(wallet_cache.load_cached_static_receive_code(slot=2), "bitcoin:bc1q...")

    # ---- payments ----------------------------------------------------

    def test_payments_round_trip_per_slot(self):
        p1 = Payment(1000, 199, "lnbits memo")
        p2 = Payment(2000, 6884, "Apr 9 confirmed")
        slot1_list = UniqueSortedList()
        slot1_list.add(p1)
        slot2_list = UniqueSortedList()
        slot2_list.add(p2)
        wallet_cache.save_cache(payments=slot1_list, slot=1)
        wallet_cache.save_cache(payments=slot2_list, slot=2)

        out1 = wallet_cache.load_cached_payments(slot=1)
        out2 = wallet_cache.load_cached_payments(slot=2)
        self.assertEqual(len(out1), 1)
        self.assertEqual(len(out2), 1)
        self.assertEqual(list(out1)[0].comment, "lnbits memo")
        self.assertEqual(list(out2)[0].comment, "Apr 9 confirmed")

    # ---- None-when-empty ---------------------------------------------

    def test_load_returns_none_when_not_set(self):
        self.assertIsNone(wallet_cache.load_cached_balance(slot=1))
        self.assertIsNone(wallet_cache.load_cached_balance(slot=2))
        self.assertIsNone(wallet_cache.load_cached_payments(slot=1))
        self.assertIsNone(wallet_cache.load_cached_payments(slot=2))


if __name__ == "__main__":
    unittest.main()
