import ssl
import json
import time

from mpos.util import urldecode
from mpos import TaskManager

from nostr.relay_manager import RelayManager
from nostr.message_type import ClientMessageType
from nostr.filter import Filter, Filters
from nostr.event import EncryptedDirectMessage
from nostr.key import PrivateKey

from payment import Payment
from unique_sorted_list import UniqueSortedList

class NWCWallet():

    PAYMENTS_TO_SHOW = 6
    PERIODIC_FETCH_BALANCE_SECONDS = 60 # seconds
    
    relays = []
    secret = None
    wallet_pubkey = None

    def __init__(self, nwc_url):
        super().__init__()
        self.nwc_url = nwc_url
        if not nwc_url:
            raise ValueError('NWC URL is not set.')
        self.connected = False
        self.relays, self.wallet_pubkey, self.secret, self.lud16 = self.parse_nwc_url(self.nwc_url)
        if not self.relays:
            raise ValueError('Missing relay in NWC URL.')
        if not self.wallet_pubkey:
            raise ValueError('Missing public key in NWC URL.')
        if not self.secret:
            raise ValueError('Missing "secret" in NWC URL.')
        #if not self.lud16:
        #    raise ValueError('Missing lud16 (= lightning address) in NWC URL.')

    def getCommentFromTransaction(self, transaction):
        comment = ""
        try:
            comment = transaction["description"]
            if comment is None:
                return comment
            json_comment = json.loads(comment)
            for field in json_comment:
                if field[0] == "text/plain":
                    comment = field[1]
                    break
            else:
                print("text/plain field is missing from JSON description")
        except Exception as e:
            print(f"Info: comment {comment} is not JSON, this is fine, using as-is ({e})")
        comment = super().try_parse_as_zap(comment)
        return comment

    async def async_wallet_manager_task(self):
        if self.lud16:
            self.handle_new_static_receive_code(self.lud16)

        self.private_key = PrivateKey(bytes.fromhex(self.secret))
        self.relay_manager = RelayManager()
        for relay in self.relays:
            self.relay_manager.add_relay(relay)

        print(f"DEBUG: Opening relay connections")
        await self.relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE})
        self.connected = False
        nrconnected = 0
        for _ in range(100):
            await TaskManager.sleep(0.1)
            nrconnected = self.relay_manager.connected_or_errored_relays()
            #print(f"Waiting for relay connections, currently: {nrconnected}/{len(self.relays)}")
            if nrconnected == len(self.relays) or not self.keep_running:
                break
        if nrconnected == 0:
            self.handle_error("Could not connect to any Nostr Wallet Connect relays.")
            return
        if not self.keep_running:
            print(f"async_wallet_manager_task does not have self.keep_running, returning...")
            return

        print(f"{nrconnected} relays connected")

        # Set up subscription to receive response
        self.subscription_id = "micropython_nwc_" + str(round(time.time()))
        print(f"DEBUG: Setting up subscription with ID: {self.subscription_id}")
        self.filters = Filters([Filter(
            #event_ids=[self.subscription_id], would be nice to filter, but not like this
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

        last_fetch_balance = time.time() - self.PERIODIC_FETCH_BALANCE_SECONDS
        while True: # handle incoming events and do periodic fetch_balance
            #print(f"checking for incoming events...")
            await TaskManager.sleep(0.1)
            if not self.keep_running:
                print("NWCWallet: not keep_running, closing connections...")
                await self.relay_manager.close_connections()
                break

            if time.time() - last_fetch_balance >= self.PERIODIC_FETCH_BALANCE_SECONDS:
                last_fetch_balance = time.time()
                try:
                    await self.fetch_balance()
                except Exception as e:
                    print(f"fetch_balance got exception {e}") # fetch_balance got exception 'NoneType' object isn't iterable?!

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
                    import sys
                    sys.print_exception(e)  # Full traceback on MicroPython
            else:
                #print(f"pool has no events after {time.ticks_ms()-start_time}ms") # completes in 0-1ms
                pass

    def fetch_balance(self):
        try:
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
        except Exception as e:
            print(f"inside fetch_balance exception: {e}")

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

    def parse_nwc_url(self, nwc_url):
        """Parse Nostr Wallet Connect URL to extract pubkey, relays, secret, and lud16."""
        print(f"DEBUG: Starting to parse NWC URL: {nwc_url}")
        try:
            # Remove 'nostr+walletconnect://' or 'nwc:' prefix
            if nwc_url.startswith('nostr+walletconnect://'):
                print(f"DEBUG: Removing 'nostr+walletconnect://' prefix")
                nwc_url = nwc_url[22:]
            elif nwc_url.startswith('nwc:'):
                print(f"DEBUG: Removing 'nwc:' prefix")
                nwc_url = nwc_url[4:]
            else:
                print(f"DEBUG: No recognized prefix found in URL")
                raise ValueError("Invalid NWC URL: missing 'nostr+walletconnect://' or 'nwc:' prefix")
            print(f"DEBUG: URL after prefix removal: {nwc_url}")
            # urldecode because the relay might have %3A%2F%2F etc
            nwc_url = urldecode(nwc_url)
            print(f"after urldecode: {nwc_url}")
            # Split into pubkey and query params
            parts = nwc_url.split('?')
            pubkey = parts[0]
            print(f"DEBUG: Extracted pubkey: {pubkey}")
            # Validate pubkey (should be 64 hex characters)
            if len(pubkey) != 64 or not all(c in '0123456789abcdef' for c in pubkey):
                raise ValueError("Invalid NWC URL: pubkey must be 64 hex characters")
            # Extract relay, secret, and lud16 from query params
            relays = []
            lud16 = None
            secret = None
            if len(parts) > 1:
                print(f"DEBUG: Query parameters found: {parts[1]}")
                params = parts[1].split('&')
                for param in params:
                    if param.startswith('relay='):
                        relay = param[6:]
                        print(f"DEBUG: Extracted relay: {relay}")
                        relays.append(relay)
                    elif param.startswith('secret='):
                        secret = param[7:]
                        print(f"DEBUG: Extracted secret: {secret}")
                    elif param.startswith('lud16='):
                        lud16 = param[6:]
                        print(f"DEBUG: Extracted lud16: {lud16}")
            else:
                print(f"DEBUG: No query parameters found")
            if not pubkey or not len(relays) > 0 or not secret:
                raise ValueError("Invalid NWC URL: missing required fields (pubkey, relay, or secret)")
            # Validate secret (should be 64 hex characters)
            if len(secret) != 64 or not all(c in '0123456789abcdef' for c in secret):
                raise ValueError("Invalid NWC URL: secret must be 64 hex characters")
            print(f"DEBUG: Parsed NWC data - Relay: {relays}, Pubkey: {pubkey}, Secret: {secret}, lud16: {lud16}")
            return relays, pubkey, secret, lud16
        except Exception as e:
            raise RuntimeError(f"Exception parsing NWC URL {nwc_url}: {e}")


