import asyncio
import json
import ssl
import _thread
import time
import unittest

from mpos import App, PackageManager
import mpos.apps

import sys
sys.path.append("apps/com.lightningpiggy.displaywallet/assets/")
from wallet import NWCWallet

class TestNWCWallet(unittest.TestCase):

    redraw_balance_cb_called = 0
    redraw_payments_cb_called = 0
    redraw_static_receive_code_cb_called = 0
    error_callback_called = 0

    def redraw_balance_cb(self, balance=0):
        print(f"redraw_callback called, balance: {balance}")
        self.redraw_balance_cb_called += 1

    def redraw_payments_cb(self):
        print(f"redraw_payments_cb called")
        self.redraw_payments_cb_called += 1
        
    def redraw_static_receive_code_cb(self):
        print(f"redraw_static_receive_code_cb called")
        self.redraw_static_receive_code_cb_called += 1

    def error_callback(self, error):
        print(f"error_callback called, error: {error}")
        self.error_callback_called += 1

    def test_it(self):
        print("starting test")
        self.wallet = NWCWallet("nostr+walletconnect://e46762afab282c324278351165122345f9983ea447b47943b052100321227571?relay=ws://192.168.1.16:5000/nostrclient/api/v1/relay&secret=fab0a9a11d4cf4b1d92e901a0b2c56634275e2fa1a7eb396ff1b942f95d59fd3&lud16=test@example.com")
        self.wallet.start(self.redraw_balance_cb, self.redraw_payments_cb, self.redraw_static_receive_code_cb, self.error_callback)
        time.sleep(15)
        self.assertTrue(self.redraw_balance_cb_called > 0)
        self.assertTrue(self.redraw_payments_cb_called > 0)
        self.assertTrue(self.redraw_static_receive_code_cb_called > 0)
        self.assertTrue(self.error_callback_called == 0)
        print("test finished")


