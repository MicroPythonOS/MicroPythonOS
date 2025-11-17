import time
import unittest

import sys
sys.path.append("apps/com.lightningpiggy.displaywallet/assets/")
from wallet import NWCWallet

class TestNWCWalletMultiRelayStartStop(unittest.TestCase):

    def unused_callback(self, arg1=None, arg2=None):
        pass

    def test_quick_start_stop(self):
        self.wallet = NWCWallet("nostr+walletconnect://e46762afab282c324278351165122345f9983ea447b47943b052100321227571?relay=ws://192.168.1.16:5000/nostrclient/api/v1/relay&relay=ws://127.0.0.1:5000/nostrrelay/test&secret=fab0a9a11d4cf4b1d92e901a0b2c56634275e2fa1a7eb396ff1b942f95d59fd3&lud16=test@example.com")
        for iteration in range(20):
            print(f"\n\nITERATION {iteration}\n\n")
            self.wallet.start(self.unused_callback, self.unused_callback, self.unused_callback, self.unused_callback)
            time.sleep(max(15-iteration,1)) # not giving any time to connect causes a bad state
            self.wallet.stop()
            time.sleep(0.2) # 0.1 seems to be okay most of the time, 0.2 is super stable
