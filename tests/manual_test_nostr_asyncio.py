import asyncio
import json
import ssl
import _thread
import time
import unittest

from mpos import App, AppManager

from nostr.relay_manager import RelayManager
from nostr.message_type import ClientMessageType
from nostr.filter import Filter, Filters
from nostr.event import EncryptedDirectMessage
from nostr.key import PrivateKey


# keeps a list of items
# The .add() method ensures the list remains unique (via __eq__)
# and sorted (via __lt__) by inserting new items in the correct position.
class UniqueSortedList:
    def __init__(self):
        self._items = []

    def add(self, item):
        #print(f"before add: {str(self)}")
        # Check if item already exists (using __eq__)
        if item not in self._items:
            # Insert item in sorted position for descending order (using __gt__)
            for i, existing_item in enumerate(self._items):
                if item > existing_item:
                    self._items.insert(i, item)
                    return
            # If item is smaller than all existing items, append it
            self._items.append(item)
        #print(f"after add: {str(self)}")

    def __iter__(self):
        # Return iterator for the internal list
        return iter(self._items)

    def get(self, index_nr):
        # Retrieve item at given index, raise IndexError if invalid
        try:
            return self._items[index_nr]
        except IndexError:
            raise IndexError("Index out of range")

    def __len__(self):
        # Return the number of items for len() calls
        return len(self._items)

    def __str__(self):
        #print("UniqueSortedList tostring called")
        return "\n".join(str(item) for item in self._items)

    def __eq__(self, other):
        if len(self._items) != len(other):
            return False
        return all(p1 == p2 for p1, p2 in zip(self._items, other))

# Payment class remains unchanged
class Payment:
    def __init__(self, epoch_time, amount_sats, comment):
        self.epoch_time = epoch_time
        self.amount_sats = amount_sats
        self.comment = comment

    def __str__(self):
        sattext = "sats"
        if self.amount_sats == 1:
            sattext = "sat"
        #return f"{self.amount_sats} {sattext} @ {self.epoch_time}: {self.comment}"
        return f"{self.amount_sats} {sattext}: {self.comment}"

    def __eq__(self, other):
        if not isinstance(other, Payment):
            return False
        return self.epoch_time == other.epoch_time and self.amount_sats == other.amount_sats and self.comment == other.comment

    def __lt__(self, other):
        if not isinstance(other, Payment):
            return NotImplemented
        return (self.epoch_time, self.amount_sats, self.comment) < (other.epoch_time, other.amount_sats, other.comment)

    def __le__(self, other):
        if not isinstance(other, Payment):
            return NotImplemented
        return (self.epoch_time, self.amount_sats, self.comment) <= (other.epoch_time, other.amount_sats, other.comment)

    def __gt__(self, other):
        if not isinstance(other, Payment):
            return NotImplemented
        return (self.epoch_time, self.amount_sats, self.comment) > (other.epoch_time, other.amount_sats, other.comment)

    def __ge__(self, other):
        if not isinstance(other, Payment):
            return NotImplemented
        return (self.epoch_time, self.amount_sats, self.comment) >= (other.epoch_time, other.amount_sats, other.comment)



class TestNostr(unittest.TestCase):

    PAYMENTS_TO_SHOW = 5

    keep_running = None
    connected = None
    balance = -1
    payment_list = []
    transactions_welcome = False

    relays = [ "ws://192.168.1.16:5000/nostrrelay/test", "ws://192.168.1.16:5000/nostrclient/api/v1/relay" ]
    #relays = [ "ws://127.0.0.1:5000/nostrrelay/test", "ws://127.0.0.1:5000/nostrclient/api/v1/relay" ]
    #relays = [ "wss://relay.damus.io", "wss://nostr-pub.wellorder.net" ]
    #relays = [ "ws://127.0.0.1:5000/nostrrelay/test", "ws://127.0.0.1:5000/nostrclient/api/v1/relay", "wss://relay.damus.io", "wss://nostr-pub.wellorder.net" ]
    #relays = [ "ws://127.0.0.1:5000/nostrclient/api/v1/relay", "wss://relay.damus.io", "wss://nostr-pub.wellorder.net" ]
    secret = "fab0a9a11d4cf4b1d92e901a0b2c56634275e2fa1a7eb396ff1b942f95d59fd3" # not really a secret, just from a local fake wallet
    wallet_pubkey = "e46762afab282c324278351165122345f9983ea447b47943b052100321227571"

    async def fetch_balance(self):
        if not self.keep_running:
            return
        # Create get_balance request
        balance_request = {
            "method": "get_balance",
            "params": {}
        }
        print(f"DEBUG: Created balance request: {balance_request}")
        print(f"DEBUG: Creating encrypted DM to wallet pubkey: {self.wallet_pubkey}")
        dm = EncryptedDirectMessage(
            recipient_pubkey=self.wallet_pubkey,
            cleartext_content=json.dumps(balance_request),
            kind=23194
        )
        print(f"DEBUG: Signing DM {json.dumps(dm)} with private key")
        self.private_key.sign_event(dm) # sign also does encryption if it's a encrypted dm
        print(f"DEBUG: Publishing encrypted DM")
        self.relay_manager.publish_event(dm)

    def handle_new_balance(self, new_balance, fetchPaymentsIfChanged=True):
        if not self.keep_running or new_balance is None:
            return
        if fetchPaymentsIfChanged: # Fetching *all* payments isn't necessary if balance was changed by a payment notification
            print("Refreshing payments...")
            self.fetch_payments() # if the balance changed, then re-list transactions

    def fetch_payments(self):
        if not self.keep_running:
            return
        # Create get_balance request
        list_transactions = {
            "method": "list_transactions",
            "params": {
                "limit": self.PAYMENTS_TO_SHOW
            }
        }
        dm = EncryptedDirectMessage(
            recipient_pubkey=self.wallet_pubkey,
            cleartext_content=json.dumps(list_transactions),
            kind=23194
        )
        self.private_key.sign_event(dm) # sign also does encryption if it's a encrypted dm
        print("\nPublishing DM to fetch payments...")
        self.relay_manager.publish_event(dm)
        self.transactions_welcome = True

    def handle_new_payments(self, new_payments):
        if not self.keep_running or not self.transactions_welcome:
            return
        print("handle_new_payments")
        if self.payment_list != new_payments:
            print("new list of payments")
            self.payment_list = new_payments
            self.payments_updated_cb()
            
    def payments_updated_cb(self):
        print("payments_updated_cb called, now closing everything!")
        self.keep_running = False

    def getCommentFromTransaction(self, transaction):
        comment = ""
        try:
            comment = transaction["description"]
            json_comment = json.loads(comment)
            for field in json_comment:
                if field[0] == "text/plain":
                    comment = field[1]
                    break
            else:
                print("text/plain field is missing from JSON description")
        except Exception as e:
            print(f"Info: could not parse comment as JSON, this is fine, using as-is ({e})")
        return comment


    async def NOmainHERE(self):
        self.keep_running = True
        self.private_key = PrivateKey(bytes.fromhex(self.secret))
        self.relay_manager = RelayManager()
        for relay in self.relays:
            self.relay_manager.add_relay(relay)

        print(f"DEBUG: Opening relay connections")
        await self.relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE})
        self.allconnected = False
        for _ in range(20):
            print("Waiting for relay connection...")
            await asyncio.sleep(0.5)
            nrconnected = 0
            for index, relay in enumerate(self.relays):
                try:
                    relay = self.relay_manager.relays[self.relays[index]]
                    if relay.connected is True:
                        print(f"connected: {self.relays[index]}")
                        nrconnected += 1
                    else:
                        print(f"not connected: {self.relays[index]}")
                except Exception as e:
                    print(f"could not find relay: {e}")
                    break # not all of them have been initialized, skip...
            self.allconnected = ( nrconnected == len(self.relays) )
            if self.allconnected:
                print("All relays connected!")
                break
        if not self.allconnected or not self.keep_running:
            print(f"ERROR: could not connect to relay or not self.keep_running, aborting...")
            return

        # Set up subscription to receive response
        self.subscription_id = "micropython_nwc_" + str(round(time.time()))
        print(f"DEBUG: Setting up subscription with ID: {self.subscription_id}")
        self.filters = Filters([Filter(
            #event_ids=[self.subscription_id], # would be nice to filter, but not like this
            kinds=[23195, 23196],  # NWC reponses and notifications
            authors=[self.wallet_pubkey],
            pubkey_refs=[self.private_key.public_key.hex()]
        )])
        print(f"DEBUG: Subscription filters: {self.filters.to_json_array()}")
        self.relay_manager.add_subscription(self.subscription_id, self.filters)
        print(f"DEBUG: Creating subscription request")
        request_message = [ClientMessageType.REQUEST, self.subscription_id]
        request_message.extend(self.filters.to_json_array())
        print(f"DEBUG: Publishing subscription request")
        self.relay_manager.publish_message(json.dumps(request_message))
        print(f"DEBUG: Published subscription request")
        for _ in range(4):
            if not self.keep_running:
                return
            print("Waiting a bit before self.fetch_balance()")
            await asyncio.sleep(0.5)

        await self.fetch_balance()

        while True:
            print(f"checking for incoming events...")
            await asyncio.sleep(1)
            if not self.keep_running:
                print("NWCWallet: not keep_running, closing connections...")
                await self.relay_manager.close_connections()
                break

            start_time = time.ticks_ms()
            if self.relay_manager.message_pool.has_events():
                print(f"DEBUG: Event received from message pool after {time.ticks_ms()-start_time}ms")
                event_msg = self.relay_manager.message_pool.get_event()
                event_created_at = event_msg.event.created_at
                print(f"Received at {time.localtime()} a message with timestamp {event_created_at} after {time.ticks_ms()-start_time}ms")
                try:
                    # This takes a very long time, even for short messages:
                    decrypted_content = self.private_key.decrypt_message(
                        event_msg.event.content,
                        event_msg.event.public_key,
                    )
                    print(f"DEBUG: Decrypted content: {decrypted_content} after {time.ticks_ms()-start_time}ms")
                    response = json.loads(decrypted_content)
                    print(f"DEBUG: Parsed response: {response}")
                    result = response.get("result")
                    if result:
                        if result.get("balance") is not None:
                            new_balance = round(int(result["balance"]) / 1000)
                            print(f"Got balance: {new_balance}")
                            self.handle_new_balance(new_balance)
                        elif result.get("transactions") is not None:
                            print("Response contains transactions!")
                            new_payment_list = UniqueSortedList()
                            for transaction in result["transactions"]:
                                amount = transaction["amount"]
                                amount = round(amount / 1000)
                                comment = self.getCommentFromTransaction(transaction)
                                epoch_time = transaction["created_at"]
                                paymentObj = Payment(epoch_time, amount, comment)
                                new_payment_list.add(paymentObj)
                            if len(new_payment_list) > 0:
                                # do them all in one shot instead of one-by-one because the lv_async() isn't always chronological,
                                # so when a long list of payments is added, it may be overwritten by a short list
                                self.handle_new_payments(new_payment_list)
                    else:
                        notification = response.get("notification")
                        if notification:
                            amount = notification["amount"]
                            amount = round(amount / 1000)
                            type = notification["type"]
                            if type == "outgoing":
                                amount = -amount
                            elif type == "incoming":
                                new_balance = self.last_known_balance + amount
                                self.handle_new_balance(new_balance, False) # don't trigger full fetch because payment info is in notification
                                epoch_time = notification["created_at"]
                                comment = self.getCommentFromTransaction(notification)
                                paymentObj = Payment(epoch_time, amount, comment)
                                self.handle_new_payment(paymentObj)
                            else:
                                print(f"WARNING: invalid notification type {type}, ignoring.")
                        else:
                            print("Unsupported response, ignoring.")
                except Exception as e:
                    print(f"DEBUG: Error processing response: {e}")
            else:
                #print(f"pool has no events after {time.ticks_ms()-start_time}ms") # completes in 0-1ms
                pass

    def test_it(self):
        print("before do_two")
        asyncio.run(self.do_two())
        print("after do_two")

    def do_two(self):
        print("before await self.NOmainHERE()")
        await self.NOmainHERE()
        print("after await self.NOmainHERE()")

