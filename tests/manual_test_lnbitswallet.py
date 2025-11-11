import asyncio
import json
import ssl
import _thread
import time
import unittest

import sys
sys.path.append("apps/com.lightningpiggy.displaywallet/assets/")
from wallet import LNBitsWallet

class TestLNBitsWallet(unittest.TestCase):

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
        self.wallet = LNBitsWallet("http://192.168.1.16:5000/", "5a2cf5d536ec45cb9a043071002e4449")
        self.wallet.start(self.redraw_balance_cb, self.redraw_payments_cb, self.redraw_static_receive_code_cb, self.error_callback)
        time.sleep(5)
        self.assertTrue(self.redraw_balance_cb_called > 0)
        self.assertTrue(self.redraw_payments_cb_called > 0)
        self.assertTrue(self.redraw_static_receive_code_cb_called == 0) # no static receive code so error 404
        self.assertTrue(self.error_callback_called == 1)
        print("test finished")


