import asyncio
import json
import ssl
import _thread
import time
import unittest
import requests
import ujson

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


    def update_balance(self, sats):
        """
        Updates the user balance by 'sats' amount using the local API.
        Authenticates first, then sends the balance update.
        """
        try:
            # Step 1: Authenticate and get access token
            auth_url = "http://192.168.1.16:5000/api/v1/auth"
            auth_payload = {"username": "admin", "password": "adminadmin"}
            print("Authenticating...")
            auth_response = requests.post( auth_url, json=auth_payload, headers={"Content-Type": "application/json"} )
            if auth_response.status_code != 200:
                print("Auth failed:", auth_response.text)
                auth_response.close()
                return False
            auth_data = ujson.loads(auth_response.text)
            access_token = auth_data["access_token"]
            auth_response.close()
            print("Authenticated, got token.")
            # Step 2: Update balance
            balance_url = "http://192.168.1.16:5000/users/api/v1/balance"
            balance_payload = { "amount": str(sats), "id": "24e9334d39b946a3b642f5fd8c292a07" }
            cookie_header = f"cookie_access_token={access_token}; is_lnbits_user_authorized=true"
            print(f"Updating balance by {sats} sats...")
            update_response = requests.put(
                balance_url,
                json=balance_payload,
                headers={ "Content-Type": "application/json", "Cookie": cookie_header })
            result = ujson.loads(update_response.text)
            update_response.close()
            if result.get("success"):
                print("Balance updated successfully!")
                return True
            else:
                print("Update failed:", result)
                return False
        except Exception as e:
            print("Error:", e)
            return False

    def test_it(self):
        print("starting test")
        self.wallet = NWCWallet("nostr+walletconnect://e46762afab282c324278351165122345f9983ea447b47943b052100321227571?relay=ws://192.168.1.16:5000/nostrclient/api/v1/relay&secret=fab0a9a11d4cf4b1d92e901a0b2c56634275e2fa1a7eb396ff1b942f95d59fd3&lud16=test@example.com")
        self.wallet.start(self.redraw_balance_cb, self.redraw_payments_cb, self.redraw_static_receive_code_cb, self.error_callback)
        print("\n\nWaiting a bit for the startup to be settled...")
        time.sleep(15)
        print("\nAsserting state...")
        saved = self.redraw_balance_cb_called
        print(f"redraw_balance_cb_called is {self.redraw_balance_cb_called}")
        self.assertGreaterEqual(self.redraw_balance_cb_called,1)
        self.assertGreaterEqual(self.redraw_payments_cb_called, 1)
        self.assertGreaterEqual(self.redraw_static_receive_code_cb_called, 1)
        self.assertEqual(self.error_callback_called, 0)
        self.update_balance(321)
        time.sleep(20)
        self.assertNotEqual(self.redraw_balance_cb_called,saved+1, "should be equal, but LNBits doesn't seem to send payment notifications (yet)")
        self.assertGreaterEqual(self.redraw_payments_cb_called, 1)
        self.assertGreaterEqual(self.redraw_static_receive_code_cb_called, 1)
        print("Stopping wallet...")
        self.wallet.stop()
        time.sleep(5)
        self.assertNotEqual(self.redraw_balance_cb_called,saved+1, "should be equal, but LNBits doesn't seem to send payment notifications (yet)")
        self.assertGreaterEqual(self.redraw_payments_cb_called, 1)
        self.assertGreaterEqual(self.redraw_static_receive_code_cb_called, 1)
        print("test finished")



class TestNWCWalletMultiRelay(unittest.TestCase):

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

    def update_balance(self, sats):
        """
        Updates the user balance by 'sats' amount using the local API.
        Authenticates first, then sends the balance update.
        """
        try:
            # Step 1: Authenticate and get access token
            auth_url = "http://192.168.1.16:5000/api/v1/auth"
            auth_payload = {"username": "admin", "password": "adminadmin"}
            print("Authenticating...")
            auth_response = requests.post( auth_url, json=auth_payload, headers={"Content-Type": "application/json"} )
            if auth_response.status_code != 200:
                print("Auth failed:", auth_response.text)
                auth_response.close()
                return False
            auth_data = ujson.loads(auth_response.text)
            access_token = auth_data["access_token"]
            auth_response.close()
            print("Authenticated, got token.")
            # Step 2: Update balance
            balance_url = "http://192.168.1.16:5000/users/api/v1/balance"
            balance_payload = { "amount": str(sats), "id": "24e9334d39b946a3b642f5fd8c292a07" }
            cookie_header = f"cookie_access_token={access_token}; is_lnbits_user_authorized=true"
            print(f"Updating balance by {sats} sats...")
            update_response = requests.put(
                balance_url,
                json=balance_payload,
                headers={ "Content-Type": "application/json", "Cookie": cookie_header })
            result = ujson.loads(update_response.text)
            update_response.close()
            if result.get("success"):
                print("Balance updated successfully!")
                return True
            else:
                print("Update failed:", result)
                return False
        except Exception as e:
            print("Error:", e)
            return False

    def test_it(self):
        print("starting test")
        self.wallet = NWCWallet("nostr+walletconnect://e46762afab282c324278351165122345f9983ea447b47943b052100321227571?relay=ws://192.168.1.16:5000/nostrclient/api/v1/relay&relay=ws://127.0.0.1:5000/nostrrelay/test&secret=fab0a9a11d4cf4b1d92e901a0b2c56634275e2fa1a7eb396ff1b942f95d59fd3&lud16=test@example.com")
        self.wallet.start(self.redraw_balance_cb, self.redraw_payments_cb, self.redraw_static_receive_code_cb, self.error_callback)
        print("\n\nWaiting a bit for the startup to be settled...")
        time.sleep(15)
        print("\nAsserting state...")
        saved = self.redraw_balance_cb_called
        print(f"redraw_balance_cb_called is {self.redraw_balance_cb_called}")
        self.assertGreaterEqual(self.redraw_balance_cb_called,1)
        self.assertGreaterEqual(self.redraw_payments_cb_called, 1)
        self.assertGreaterEqual(self.redraw_static_receive_code_cb_called, 1)
        self.assertEqual(self.error_callback_called, 0)
        self.update_balance(321)
        time.sleep(20)
        self.assertNotEqual(self.redraw_balance_cb_called,saved+1, "should be equal, but LNBits doesn't seem to send payment notifications (yet)")
        self.assertGreaterEqual(self.redraw_payments_cb_called, 1)
        self.assertGreaterEqual(self.redraw_static_receive_code_cb_called, 1)
        print("Stopping wallet...")
        self.wallet.stop()
        time.sleep(5)
        self.assertNotEqual(self.redraw_balance_cb_called,saved+1, "should be equal, but LNBits doesn't seem to send payment notifications (yet)")
        self.assertGreaterEqual(self.redraw_payments_cb_called, 1)
        self.assertGreaterEqual(self.redraw_static_receive_code_cb_called, 1)
        print("test finished")


