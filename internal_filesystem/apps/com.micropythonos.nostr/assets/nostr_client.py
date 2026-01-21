import ssl
import json
import time

from mpos import TaskManager

from nostr.relay_manager import RelayManager
from nostr.message_type import ClientMessageType
from nostr.filter import Filter, Filters
from nostr.key import PrivateKey

class NostrEvent:
    """Simple wrapper for a Nostr event"""
    def __init__(self, event_obj):
        self.event = event_obj
        self.created_at = event_obj.created_at
        self.content = event_obj.content
        self.public_key = event_obj.public_key
    
    def __str__(self):
        return f"{self.content}"

class NostrClient():
    """Simple Nostr event subscriber that connects to a relay and subscribes to a public key's events"""

    EVENTS_TO_SHOW = 10
    
    relay = None
    nsec = None
    follow_npub = None
    private_key = None
    relay_manager = None

    def __init__(self, nsec, follow_npub, relay):
        super().__init__()
        self.nsec = nsec
        self.follow_npub = follow_npub
        self.relay = relay
        self.event_list = []
        
        if not nsec:
            raise ValueError('Nostr private key (nsec) is not set.')
        if not follow_npub:
            raise ValueError('Nostr follow public key (npub) is not set.')
        if not relay:
            raise ValueError('Nostr relay is not set.')
        
        self.connected = False

    async def async_event_manager_task(self):
        """Main event loop: connect to relay and subscribe to events"""
        try:
            # Initialize private key from nsec
            # nsec can be in bech32 format (nsec1...) or hex format
            if self.nsec.startswith("nsec1"):
                self.private_key = PrivateKey.from_nsec(self.nsec)
            else:
                self.private_key = PrivateKey(bytes.fromhex(self.nsec))
            
            # Initialize relay manager
            self.relay_manager = RelayManager()
            self.relay_manager.add_relay(self.relay)

            print(f"DEBUG: Opening relay connection to {self.relay}")
            await self.relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE})
            
            self.connected = False
            for _ in range(100):
                await TaskManager.sleep(0.1)
                nrconnected = self.relay_manager.connected_or_errored_relays()
                if nrconnected == 1 or not self.keep_running:
                    break
            
            if nrconnected == 0:
                self.handle_error("Could not connect to Nostr relay.")
                return
            
            if not self.keep_running:
                print(f"async_event_manager_task: not keep_running, returning...")
                return

            print(f"Relay connected")
            self.connected = True

            # Set up subscription to receive events from follow_npub
            self.subscription_id = "micropython_nostr_" + str(round(time.time()))
            print(f"DEBUG: Setting up subscription with ID: {self.subscription_id}")
            
            # Convert npub to hex if needed
            follow_npub_hex = self.follow_npub
            if self.follow_npub.startswith("npub1"):
                from nostr.key import PublicKey
                follow_npub_hex = PublicKey.from_npub(self.follow_npub).hex()
                print(f"DEBUG: Converted npub to hex: {follow_npub_hex}")
            
            # Create filter for events from follow_npub
            # Note: Some relays don't support filtering by both kinds and authors
            # So we just filter by authors
            self.filters = Filters([Filter(
                authors=[follow_npub_hex],
            )])
            print(f"DEBUG: Subscription filters: {self.filters.to_json_array()}")
            self.relay_manager.add_subscription(self.subscription_id, self.filters)
            
            print(f"DEBUG: Creating subscription request")
            request_message = [ClientMessageType.REQUEST, self.subscription_id]
            request_message.extend(self.filters.to_json_array())
            print(f"DEBUG: Publishing subscription request")
            self.relay_manager.publish_message(json.dumps(request_message))
            print(f"DEBUG: Published subscription request")

            # Main event loop
            while True:
                await TaskManager.sleep(0.1)
                if not self.keep_running:
                    print("NostrClient: not keep_running, closing connections...")
                    await self.relay_manager.close_connections()
                    break

                start_time = time.ticks_ms()
                if self.relay_manager.message_pool.has_events():
                    print(f"DEBUG: Event received from message pool after {time.ticks_ms()-start_time}ms")
                    event_msg = self.relay_manager.message_pool.get_event()
                    event_created_at = event_msg.event.created_at
                    print(f"Received at {time.localtime()} a message with timestamp {event_created_at} after {time.ticks_ms()-start_time}ms")
                    try:
                        # Create NostrEvent wrapper
                        nostr_event = NostrEvent(event_msg.event)
                        print(f"DEBUG: Event content: {nostr_event.content}")
                        
                        # Add to event list
                        self.handle_new_event(nostr_event)
                        
                    except Exception as e:
                        print(f"DEBUG: Error processing event: {e}")
                        import sys
                        sys.print_exception(e)
                
                # Check for relay notices (error messages)
                if self.relay_manager.message_pool.has_notices():
                    notice_msg = self.relay_manager.message_pool.get_notice()
                    print(f"DEBUG: Relay notice: {notice_msg}")
                    if notice_msg:
                        self.handle_error(f"Relay: {notice_msg.content}")

        except Exception as e:
            print(f"async_event_manager_task exception: {e}")
            import sys
            sys.print_exception(e)
            self.handle_error(f"Error in event manager: {e}")

    # Public variables
    last_known_balance = 0
    event_list = None

    # Variables
    keep_running = True
    
    # Callbacks:
    events_updated_cb = None
    error_cb = None

    def handle_new_event(self, new_event):
        """Handle a new event from the relay"""
        if not self.keep_running:
            return
        print("handle_new_event")
        self.event_list.append(new_event)
        # Keep only the most recent EVENTS_TO_SHOW events
        if len(self.event_list) > self.EVENTS_TO_SHOW:
            self.event_list = self.event_list[-self.EVENTS_TO_SHOW:]
        if self.events_updated_cb:
            self.events_updated_cb()

    def handle_error(self, e):
        if self.error_cb:
            self.error_cb(e)

    def start(self, events_updated_cb, error_cb=None):
        """Start the event manager task"""
        self.keep_running = True
        self.events_updated_cb = events_updated_cb
        self.error_cb = error_cb
        TaskManager.create_task(self.async_event_manager_task())

    def stop(self):
        """Stop the event manager task"""
        self.keep_running = False

    def is_running(self):
        return self.keep_running
