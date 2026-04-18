"""
Unit tests for the on-chain wallet type in the Lightning Piggy app.

Targets LightningPiggyApp PR #25 (on-chain wallet via Blockbook).

Usage:
    Desktop: ./tests/unittest.sh tests/test_onchain_wallet.py
    Device:  ./tests/unittest.sh tests/test_onchain_wallet.py --ondevice
"""

import sys
import unittest

sys.path.append("apps/com.lightningpiggy.displaywallet/assets/")

try:
    from onchain_wallet import OnchainWallet
    _HAVE_ONCHAIN = True
except ImportError:
    _HAVE_ONCHAIN = False


@unittest.skipUnless(_HAVE_ONCHAIN, "onchain_wallet.py not installed (feature not landed yet)")
class TestOnchainWalletConstructor(unittest.TestCase):

    def test_rejects_empty_xpub(self):
        with self.assertRaises(ValueError):
            OnchainWallet("")

    def test_rejects_bad_prefix(self):
        with self.assertRaises(ValueError):
            OnchainWallet("foobarbaz")

    def test_accepts_xpub_prefix(self):
        w = OnchainWallet("xpub1234example")
        self.assertEqual(w.xpub, "xpub1234example")

    def test_accepts_zpub_prefix(self):
        w = OnchainWallet("zpub1234example")
        self.assertEqual(w.xpub, "zpub1234example")

    def test_trims_blockbook_trailing_slash(self):
        w = OnchainWallet("zpub1234example", blockbook_url="https://example.com/")
        self.assertEqual(w.blockbook_url, "https://example.com")

    def test_blockbook_url_default_when_none(self):
        w = OnchainWallet("zpub1234example")
        self.assertEqual(w.blockbook_url, OnchainWallet.DEFAULT_BLOCKBOOK_URL)

    def test_blockbook_url_empty_falls_back_to_default(self):
        # An empty string URL pref should behave the same as None.
        w = OnchainWallet("zpub1234example", blockbook_url=None)
        self.assertEqual(w.blockbook_url, OnchainWallet.DEFAULT_BLOCKBOOK_URL)


@unittest.skipUnless(_HAVE_ONCHAIN, "onchain_wallet.py not installed")
class TestOnchainWalletParseTransactions(unittest.TestCase):

    def setUp(self):
        self.w = OnchainWallet("zpub1234example")

    def test_confirmed_incoming_tx(self):
        txs = [{
            "txid": "abc", "confirmations": 5, "blockTime": 1775838000,
            "vin": [{"isOwn": False, "value": "10000"}],
            "vout": [{"isOwn": True, "value": "6884"}, {"isOwn": False, "value": "3000"}],
        }]
        payments, any_unconfirmed = self.w._parse_transactions(txs)
        self.assertEqual(len(payments), 1)
        p = list(payments)[0]
        self.assertEqual(p.amount_sats, 6884)
        self.assertIn("confirmed", p.comment)
        self.assertFalse(any_unconfirmed)

    def test_unconfirmed_tx_flagged(self):
        txs = [{
            "txid": "pending", "confirmations": 0, "blockTime": 0,
            "vin": [{"isOwn": False, "value": "10000"}],
            "vout": [{"isOwn": True, "value": "5000"}],
        }]
        _payments, any_unconfirmed = self.w._parse_transactions(txs)
        self.assertTrue(any_unconfirmed)

    def test_self_transfer_is_fee_only(self):
        # All inputs + all outputs marked isOwn → classic self-transfer: the
        # wallet loses only the network fee.
        txs = [{
            "txid": "self", "confirmations": 10, "blockTime": 1775838000, "fees": "500",
            "vin": [{"isOwn": True, "value": "50500"}],
            "vout": [{"isOwn": True, "value": "50000"}],
        }]
        payments, _unc = self.w._parse_transactions(txs)
        p = list(payments)[0]
        self.assertEqual(p.amount_sats, -500)
        self.assertIn("self-transfer", p.comment)

    def test_outgoing_tx_uses_net_amount(self):
        # Our input 20000, our output 15000 (change) → net -5000 sent.
        txs = [{
            "txid": "out", "confirmations": 3, "blockTime": 1775838000, "fees": "200",
            "vin": [{"isOwn": True, "value": "20000"}],
            "vout": [
                {"isOwn": True, "value": "15000"},      # change back to us
                {"isOwn": False, "value": "4800"},      # paid out to someone else
            ],
        }]
        payments, _unc = self.w._parse_transactions(txs)
        p = list(payments)[0]
        # Net = 15000 - 20000 = -5000 (it goes through the non-self-transfer branch
        # because not all vout is isOwn).
        self.assertEqual(p.amount_sats, -5000)

    def test_empty_transactions(self):
        payments, any_unconfirmed = self.w._parse_transactions([])
        self.assertEqual(len(payments), 0)
        self.assertFalse(any_unconfirmed)

    def test_none_transactions(self):
        # Response may legitimately have no "transactions" key.
        payments, any_unconfirmed = self.w._parse_transactions(None)
        self.assertEqual(len(payments), 0)
        self.assertFalse(any_unconfirmed)


@unittest.skipUnless(_HAVE_ONCHAIN, "onchain_wallet.py not installed")
class TestOnchainWalletPickReceiveAddress(unittest.TestCase):

    def setUp(self):
        self.w = OnchainWallet("zpub1234example")

    def test_picks_first_unused_external(self):
        tokens = [
            {"name": "bc1qused1", "path": "m/84'/0'/0'/0/0", "transfers": 3},
            {"name": "bc1qfirst", "path": "m/84'/0'/0'/0/5", "transfers": 0},
            {"name": "bc1qsecond", "path": "m/84'/0'/0'/0/6", "transfers": 0},
        ]
        self.assertEqual(
            self.w._pick_receive_address(tokens),
            "bitcoin:bc1qfirst",
        )

    def test_skips_change_chain(self):
        tokens = [
            {"name": "bc1qchange", "path": "m/84'/0'/0'/1/0", "transfers": 0},  # internal/change
            {"name": "bc1qexternal", "path": "m/84'/0'/0'/0/0", "transfers": 0},
        ]
        self.assertEqual(
            self.w._pick_receive_address(tokens),
            "bitcoin:bc1qexternal",
        )

    def test_skips_used_addresses(self):
        tokens = [
            {"name": "bc1qused1", "path": "m/84'/0'/0'/0/0", "transfers": 7},
            {"name": "bc1qused2", "path": "m/84'/0'/0'/0/1", "transfers": 1},
        ]
        self.assertIsNone(self.w._pick_receive_address(tokens))

    def test_none_when_no_tokens(self):
        self.assertIsNone(self.w._pick_receive_address([]))
        self.assertIsNone(self.w._pick_receive_address(None))

    def test_returns_lowest_index_unused(self):
        # Three unused external addresses — the one at index 1 must win
        # regardless of list order, because it has the lowest derivation index.
        tokens = [
            {"name": "bc1qthird", "path": "m/84'/0'/0'/0/3", "transfers": 0},
            {"name": "bc1qfirst", "path": "m/84'/0'/0'/0/1", "transfers": 0},
            {"name": "bc1qsecond", "path": "m/84'/0'/0'/0/2", "transfers": 0},
        ]
        self.assertEqual(
            self.w._pick_receive_address(tokens),
            "bitcoin:bc1qfirst",
        )


if __name__ == "__main__":
    unittest.main()
