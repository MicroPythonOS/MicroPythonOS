import ssl
import json
import time

from mpos import Service, TaskManager

from nostr.relay_manager import RelayManager
from nostr.message_type import ClientMessageType
from nostr.filter import Filter, Filters
from nostr.event import EncryptedDirectMessage
from nostr.key import PrivateKey

EVENT_KIND_NAMES = {
    0: "SET_METADATA",
    1: "TEXT_NOTE",
    2: "RECOMMEND_RELAY",
    3: "CONTACTS",
    4: "ENCRYPTED_DM",
    5: "DELETE",
}


def get_kind_name(kind):
    return EVENT_KIND_NAMES.get(kind, f"UNKNOWN({kind})")


# Hard-coded FRI3D NIP-28 public channel.
# Channel event id and metadata from
# nevent1qqsvcrczlp9uxaaucqah67m6qp6l5kkhwfgs2j0ycq5g9wsaszlk3wcpzamhxue69uhhyetvv9ujucm0wfc82mfwvdhk6tczyqvpzdc9flnqmagk39mrz8ct73xmuj756ts276fjthlwn75p4r9a5qcyqqqqq2sfhuvhp
CHANNEL_ID = "fccd56d3ce0b43d48c55851a8024e398b7a33b92de64976e374df69913fd482f"
CHANNEL_PUBKEY = "181137054fe60df5168976311f0bf44dbe4bd4d2e0af69325dfee9fa81a8cbda"
CHANNEL_NAME = "fri3d"
CHANNEL_ABOUT = "Be excellent!"
DEFAULT_RELAY = "wss://relay.damus.io"


def format_timestamp(timestamp):
    try:
        import time as time_module
        time_tuple = time_module.localtime(timestamp)
        return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}".format(
            time_tuple[0], time_tuple[1], time_tuple[2],
            time_tuple[3], time_tuple[4]
        )
    except Exception:
        return str(timestamp)


def format_tags(tags):
    if not tags:
        return ""
    tag_strs = []
    for tag in tags:
        if len(tag) >= 2:
            tag_type = tag[0]
            tag_value = tag[1]
            if len(tag_value) > 16:
                tag_value = tag_value[:16] + "..."
            tag_strs.append(f"{tag_type}:{tag_value}")
    if tag_strs:
        return "Tags: " + ", ".join(tag_strs)
    return ""


class NostrEvent:
    def __init__(self, event_obj, private_key=None):
        self.event = event_obj
        self.created_at = event_obj.created_at
        self.content = event_obj.content
        self.public_key = event_obj.public_key
        self.kind = event_obj.kind
        self.tags = event_obj.tags if hasattr(event_obj, 'tags') else []
        self.private_key = private_key
        self.decrypted_content = None
        if self.kind == 4 and self.private_key:
            self._try_decrypt()

    def _try_decrypt(self):
        try:
            if self.kind == 4 and self.content:
                decrypted = self.private_key.decrypt_message(
                    self.content,
                    self.public_key
                )
                self.decrypted_content = decrypted
                print(f"DEBUG: Successfully decrypted DM: {decrypted}")
        except Exception as e:
            print(f"DEBUG: Failed to decrypt DM: {e}")

    def get_kind_name(self):
        return get_kind_name(self.kind)

    def get_formatted_timestamp(self):
        return format_timestamp(self.created_at)

    def get_formatted_tags(self):
        return format_tags(self.tags)

    def get_display_content(self):
        if self.decrypted_content is not None:
            return self.decrypted_content
        return self.content

    def __str__(self):
        if self.kind == 42:
            return self._format_channel_message()
        kind_name = self.get_kind_name()
        timestamp = self.get_formatted_timestamp()
        tags_str = self.get_formatted_tags()
        display_content = self.get_display_content()
        result = f"[{kind_name}] {timestamp}\n"
        if display_content:
            result += f"{display_content}"
        if tags_str:
            result += f"\n{tags_str}"
        return result

    def _format_channel_message(self):
        timestamp = self.get_formatted_timestamp()
        pubkey = (self.public_key[:16] + "...") if self.public_key else "?"
        content = self.get_display_content()
        return f"[{timestamp}] {pubkey}\n{content}"


def _make_subscription_id(prefix):
    return prefix + str(round(time.time()))


_orig_relay_on_error = None
try:
    import nostr.relay as _nostr_relay
    _orig_relay_on_error = _nostr_relay.Relay._on_error
    def _patched_relay_on_error(self, class_obj, error):
        try:
            print("relay.py got error for {}: {!r}".format(self.url, error))
        except Exception:
            pass
        return _orig_relay_on_error(self, class_obj, error)
    _nostr_relay.Relay._on_error = _patched_relay_on_error
except Exception as _e:
    print("Failed to patch Relay._on_error for diagnostics:", _e)


class NostrManager:

    _instance = None
    EVENTS_TO_SHOW = 50
    NWC_POLL_SECONDS = 120
    RELAY_SILENT_RECONNECT_THRESHOLD = 3

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.relay_manager = None
        self._main_task = None
        self.connected = False
        self._polls_since_last_event = 0
        self._last_nwc_poll = 0
        self._relays_configured = False
        # How many transactions list_transactions requests. Kept in sync
        # with the wallet's PAYMENTS_TO_SHOW (the per-slot "Transactions
        # Shown" slider, 1..21) via NWCWallet's PAYMENTS_TO_SHOW property —
        # without that link, NWC would always fetch the class default while
        # LNBits (limit=) and on-chain (pageSize=) honour the user setting.
        self._nwc_list_limit = 6

        # Nostr app state
        self.events = []
        self._nostr_private_key = None
        self._nostr_relay = None
        self._nostr_follow_hex = None
        self._nostr_sub_id = None
        self._nostr_configured = False

        # NWC state
        self._nwc_private_key = None
        self._nwc_wallet_pubkey = None
        self._nwc_relays = []
        self._nwc_sub_id = None
        self._nwc_lud16 = None
        self._nwc_configured = False
        self._nwc_nwc_url = None

        # Event callbacks: kind -> [callbacks]
        self._event_handlers = {}

        # NWC-specific callbacks (set by NWCWallet)
        self._nwc_balance_cb = None
        self._nwc_payments_cb = None
        self._nwc_notification_cb = None

        # Generic event update callback (called for every event)
        self._events_updated_cb = None

        # Error callback
        self._error_cb = None

        # Lifecycle
        self.keep_running = False
        self._cleanup_done = True

    # --- Public lifecycle ---

    def start(self):
        """Initialize the manager. Call before any configure_* methods."""
        if self.keep_running:
            return
        self.keep_running = True

    def stop(self):
        """Stop the manager and close all relay connections."""
        self.keep_running = False
        if self._main_task is not None and self._cleanup_done:
            self._cleanup_done = False
            TaskManager.create_task(self._do_close())

    async def _do_close(self):
        if self.relay_manager is not None:
            try:
                await self.relay_manager.close_connections()
            except Exception as e:
                print("NostrManager: error closing connections: {}".format(e))
        self._main_task = None
        self._nostr_configured = False
        self._nwc_configured = False
        self._relays_configured = False
        self._cleanup_done = True

    def is_running(self):
        return self.keep_running

    def is_connected(self):
        return self.connected

    # --- Event handler registration ---

    def register_event_handler(self, kind, callback):
        if kind not in self._event_handlers:
            self._event_handlers[kind] = []
        self._event_handlers[kind].append(callback)

    def unregister_event_handler(self, kind, callback):
        if kind in self._event_handlers:
            self._event_handlers[kind] = [
                cb for cb in self._event_handlers[kind] if cb != callback
            ]

    def set_nwc_callbacks(self, balance_cb=None, payments_cb=None, notification_cb=None):
        self._nwc_balance_cb = balance_cb
        self._nwc_payments_cb = payments_cb
        self._nwc_notification_cb = notification_cb

    def set_nwc_list_limit(self, n):
        """Set how many transactions list_transactions requests. Clamped
        defensively to 1..100 (matches the on-chain wallet's pageSize
        guard); the Settings slider only produces 1..21."""
        try:
            self._nwc_list_limit = max(1, min(int(n), 100))
        except (TypeError, ValueError):
            pass

    def set_events_updated_callback(self, cb):
        self._events_updated_cb = cb

    def set_error_callback(self, cb):
        self._error_cb = cb

    # --- Configuration ---

    def configure_nostr(self, nsec, relay, follow_npub):
        """Configure and start the nostr app subscription."""
        self._nostr_relay = relay
        if nsec.startswith("nsec1"):
            self._nostr_private_key = PrivateKey.from_nsec(nsec)
        else:
            self._nostr_private_key = PrivateKey(bytes.fromhex(nsec))
        follow_npub_hex = None
        if follow_npub:
            if follow_npub.startswith("npub1"):
                from nostr.key import PublicKey
                follow_npub_hex = PublicKey.from_npub(follow_npub).hex()
            else:
                follow_npub_hex = follow_npub
        self._nostr_follow_hex = follow_npub_hex
        self._nostr_configured = True
        self._ensure_main_task()

    def configure_nwc(self, nwc_url):
        """Configure and start NWC subscriptions."""
        if self._nwc_nwc_url == nwc_url:
            # Same URL — config unchanged, but the main task may have been
            # torn down by a stop()/start() cycle in between (e.g.
            # NostrClientService.onDestroy). Without this, reconfiguring
            # with an identical URL after a manager restart would leave NWC
            # permanently dead: no main task, nothing polling.
            self._ensure_main_task()
            return

        relays, wallet_pubkey, secret, lud16 = self._parse_nwc_url(nwc_url)
        self._nwc_relays = relays
        self._nwc_wallet_pubkey = wallet_pubkey
        self._nwc_private_key = PrivateKey(bytes.fromhex(secret))
        self._nwc_lud16 = lud16
        self._nwc_nwc_url = nwc_url
        self._nwc_configured = True
        self._ensure_main_task()

    def _parse_nwc_url(self, nwc_url):
        from mpos.util import urldecode
        print("DEBUG: Starting to parse NWC URL")
        try:
            if nwc_url.startswith('nostr+walletconnect://'):
                nwc_url = nwc_url[22:]
            elif nwc_url.startswith('nwc:'):
                nwc_url = nwc_url[4:]
            else:
                raise ValueError("Invalid NWC URL: missing 'nostr+walletconnect://' or 'nwc:' prefix")
            nwc_url = urldecode(nwc_url)
            parts = nwc_url.split('?')
            pubkey = parts[0]
            if len(pubkey) != 64 or not all(c in '0123456789abcdef' for c in pubkey):
                raise ValueError("Invalid NWC URL: pubkey must be 64 hex characters")
            relays = []
            lud16 = None
            secret = None
            if len(parts) > 1:
                params = parts[1].split('&')
                for param in params:
                    if param.startswith('relay='):
                        relay = param[6:]
                        relays.append(relay)
                    elif param.startswith('secret='):
                        secret = param[7:]
                    elif param.startswith('lud16='):
                        lud16 = param[6:]
            if not pubkey or not len(relays) > 0 or not secret:
                raise ValueError("Invalid NWC URL: missing required fields (pubkey, relay, or secret)")
            if len(secret) != 64 or not all(c in '0123456789abcdef' for c in secret):
                raise ValueError("Invalid NWC URL: secret must be 64 hex characters")
            print(f"DEBUG: Parsed NWC data - Relays: {relays}, lud16: {lud16}")
            return relays, pubkey, secret, lud16
        except Exception as e:
            raise RuntimeError(f"Exception parsing NWC URL: {e}")

    def _ensure_main_task(self):
        if self._main_task is not None:
            return
        self._main_task = TaskManager.create_task(self._run())

    async def _run(self):
        """Main event loop — manages relay connections, subscriptions, event routing, and NWC polling."""

        self.relay_manager = RelayManager()

        # Add all configured relays
        if self._nostr_configured and self._nostr_relay:
            self.relay_manager.add_relay(self._nostr_relay)
        for relay in self._nwc_relays:
            self.relay_manager.add_relay(relay)

        if not self.relay_manager.relays:
            print("NostrManager: no relays configured, waiting...")
            while self.keep_running and not self._relays_configured:
                await TaskManager.sleep(0.5)
                if self._nostr_relay or self._nwc_relays:
                    self._relays_configured = True
            if not self.keep_running:
                return
            # _nostr_relay is a single URL string, not a list — iterating
            # it (as this code once did) would add each CHARACTER as a
            # relay. Mirror the add at the top of _run().
            if self._nostr_configured and self._nostr_relay:
                self.relay_manager.add_relay(self._nostr_relay)
            for relay in self._nwc_relays:
                self.relay_manager.add_relay(relay)
            if not self.relay_manager.relays:
                print("NostrManager: still no relays after wait, exiting")
                return

        await self.relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE})
        self.connected = False
        nrconnected = 0

        for _ in range(300):
            await TaskManager.sleep(0.1)
            nrconnected = self.relay_manager.connected_or_errored_relays()
            if nrconnected == len(self.relay_manager.relays) or not self.keep_running:
                break

        if nrconnected == 0:
            msg = "Could not connect to any Nostr relay."
            print("NostrManager:", msg)
            if self._error_cb:
                self._error_cb(msg)
            return

        if not self.keep_running:
            return

        print("NostrManager: {} relay(s) connected".format(nrconnected))
        self.connected = True

        # Set up nostr app subscription
        if self._nostr_configured:
            self._nostr_sub_id = _make_subscription_id("micropython_nostr_")
            filter_list = [Filter(kinds=[42], event_refs=[CHANNEL_ID])]
            if self._nostr_follow_hex:
                filter_list.append(Filter(authors=[self._nostr_follow_hex]))
            filters = Filters(filter_list)
            self.relay_manager.add_subscription(self._nostr_sub_id, filters)
            req = [ClientMessageType.REQUEST, self._nostr_sub_id]
            req.extend(filters.to_json_array())
            self.relay_manager.publish_message(json.dumps(req))
            print("NostrManager: subscribed to channel #{}".format(CHANNEL_NAME))
            if self._nostr_follow_hex:
                print("NostrManager: also subscribed to events from {}".format(
                    self._nostr_follow_hex[:16]))

        # Set up NWC subscription
        if self._nwc_configured:
            self._nwc_sub_id = _make_subscription_id("micropython_nwc_")
            nwc_filters = Filters([Filter(
                kinds=[23195, 23196],
                authors=[self._nwc_wallet_pubkey],
                pubkey_refs=[self._nwc_private_key.public_key.hex()]
            )])
            self.relay_manager.add_subscription(self._nwc_sub_id, nwc_filters)
            req = [ClientMessageType.REQUEST, self._nwc_sub_id]
            req.extend(nwc_filters.to_json_array())
            self.relay_manager.publish_message(json.dumps(req))
            print("NostrManager: subscribed to NWC responses")
            if self._nwc_lud16 and "@" in self._nwc_lud16:
                # Don't use permissive ensure_lightning_prefix, only allow LUD-16
                self._handle_nwc_static_receive_code((self._nwc_lud16))

        self._last_nwc_poll = time.time() - self.NWC_POLL_SECONDS

        # Main processing loop
        while self.keep_running:
            await TaskManager.sleep(0.1)

            if not self.keep_running:
                break

            now = time.time()

            # --- Periodic NWC polling ---
            if self._nwc_configured and now - self._last_nwc_poll >= self.NWC_POLL_SECONDS:
                self._last_nwc_poll = now

                if self._polls_since_last_event >= self.RELAY_SILENT_RECONNECT_THRESHOLD:
                    await self._reconnect_relay()
                    if not self.keep_running:
                        break

                self._polls_since_last_event += 1

                try:
                    self.nwc_fetch_balance()
                except Exception as e:
                    print("NostrManager: fetch_balance error: {}".format(e))

                try:
                    self.nwc_fetch_payments()
                except Exception as e:
                    print("NostrManager: fetch_payments error: {}".format(e))

            # --- Process incoming events ---
            if self.relay_manager.message_pool.has_events():
                event_msg = self.relay_manager.message_pool.get_event()
                event = event_msg.event
                print("NostrManager: received event kind={} from {}".format(
                    event.kind, event.public_key[:16]))

                try:
                    self._process_event(event)
                except Exception as e:
                    print("NostrManager: error processing event: {}".format(e))
                    import sys
                    sys.print_exception(e)

            if self.relay_manager.message_pool.has_notices():
                notice = self.relay_manager.message_pool.get_notice()
                print("NostrManager: relay notice: {}".format(notice))
                if notice and hasattr(notice, 'content') and self._error_cb:
                    self._error_cb("Relay: {}".format(notice.content))

    def _process_event(self, event):
        """Route a single event to all relevant handlers."""

        # Route by kind to registered callbacks
        if event.kind in self._event_handlers:
            nostr_event = NostrEvent(event, self._nostr_private_key)
            for cb in self._event_handlers[event.kind]:
                try:
                    cb(nostr_event)
                except Exception as e:
                    print("NostrManager: event handler error: {}".format(e))

        # Store in events list for NostrApp
        nostr_event = NostrEvent(event, self._nostr_private_key)
        self.events.append(nostr_event)
        if len(self.events) > self.EVENTS_TO_SHOW:
            self.events = self.events[-self.EVENTS_TO_SHOW:]

        if self._events_updated_cb:
            try:
                self._events_updated_cb()
            except Exception as e:
                print("NostrManager: events_updated callback error: {}".format(e))

        # Handle NWC events (kinds 23195/23196)
        if event.kind in (23195, 23196) and self._nwc_configured:
            self._process_nwc_event(event)

    def _process_nwc_event(self, event):
        """Decrypt and process an NWC response/notification event."""
        try:
            decrypted = self._nwc_private_key.decrypt_message(
                event.content,
                event.public_key,
            )
            print("NostrManager: decrypted NWC: {}".format(decrypted))
            response = json.loads(decrypted)
            result = response.get("result")
            if result:
                if result.get("balance") is not None:
                    new_balance = round(int(result["balance"]) / 1000)
                    print("NostrManager: NWC balance: {}".format(new_balance))
                    if self._polls_since_last_event > 0:
                        print("NostrManager: NWC watchdog counter reset (balance)")
                    self._polls_since_last_event = 0
                    if self._nwc_balance_cb:
                        self._nwc_balance_cb(new_balance)

                elif result.get("transactions") is not None:
                    print("NostrManager: NWC transactions received")
                    if self._polls_since_last_event > 0:
                        print("NostrManager: NWC watchdog counter reset (transactions)")
                    self._polls_since_last_event = 0
                    if self._nwc_payments_cb:
                        self._nwc_payments_cb(result["transactions"])

            notification = response.get("notification")
            if notification:
                if self._nwc_notification_cb:
                    self._nwc_notification_cb(notification)

        except Exception as e:
            print("NostrManager: NWC event processing error: {}".format(e))
            import sys
            sys.print_exception(e)

    def _handle_nwc_static_receive_code(self, lud16):
        if self._nwc_notification_cb:
            self._nwc_notification_cb({"static_receive_code": lud16})

    async def _reconnect_relay(self):
        """Watchdog reconnect: close, wait, reopen, re-subscribe."""
        print("NostrManager: watchdog reconnecting relay (silent for {} polls)".format(
            self._polls_since_last_event))
        try:
            await self.relay_manager.close_connections()
        except Exception as e:
            print("NostrManager: close during reconnect failed: {}".format(e))

        await TaskManager.sleep(2)

        old_relay_urls = list(self.relay_manager.relays.keys()) if hasattr(self.relay_manager, 'relays') else []
        self.relay_manager = RelayManager()
        for url in old_relay_urls:
            self.relay_manager.add_relay(url)

        try:
            await self.relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE})
        except Exception as e:
            print("NostrManager: open_connections during reconnect failed: {}".format(e))

        for _ in range(50):
            await TaskManager.sleep(0.1)
            if not self.keep_running:
                return
            if self.relay_manager.connected_or_errored_relays() == len(old_relay_urls) if old_relay_urls else True:
                break

        # Re-subscribe
        if self._nostr_configured:
            self._nostr_sub_id = _make_subscription_id("micropython_nostr_")
            filter_list = [Filter(kinds=[42], event_refs=[CHANNEL_ID])]
            if self._nostr_follow_hex:
                filter_list.append(Filter(authors=[self._nostr_follow_hex]))
            filters = Filters(filter_list)
            self.relay_manager.add_subscription(self._nostr_sub_id, filters)
            self.relay_manager.publish_message(json.dumps(
                [ClientMessageType.REQUEST, self._nostr_sub_id] + filters.to_json_array()))
        if self._nwc_configured:
            self._nwc_sub_id = _make_subscription_id("micropython_nwc_")
            nwc_filters = Filters([Filter(
                kinds=[23195, 23196],
                authors=[self._nwc_wallet_pubkey],
                pubkey_refs=[self._nwc_private_key.public_key.hex()]
            )])
            self.relay_manager.add_subscription(self._nwc_sub_id, nwc_filters)
            self.relay_manager.publish_message(json.dumps(
                [ClientMessageType.REQUEST, self._nwc_sub_id] + nwc_filters.to_json_array()))

        self._polls_since_last_event = 0

    # --- NWC request methods ---

    def nwc_fetch_balance(self):
        if not self._nwc_configured:
            return
        balance_request = {"method": "get_balance", "params": {}}
        dm = EncryptedDirectMessage(
            recipient_pubkey=self._nwc_wallet_pubkey,
            cleartext_content=json.dumps(balance_request),
            kind=23194
        )
        self._nwc_private_key.sign_event(dm)
        self.relay_manager.publish_event(dm)

    def nwc_fetch_payments(self):
        if not self._nwc_configured:
            return
        list_transactions = {
            "method": "list_transactions",
            "params": {"limit": self._nwc_list_limit}
        }
        dm = EncryptedDirectMessage(
            recipient_pubkey=self._nwc_wallet_pubkey,
            cleartext_content=json.dumps(list_transactions),
            kind=23194
        )
        self._nwc_private_key.sign_event(dm)
        self.relay_manager.publish_event(dm)


class NostrClientService(Service):

    def onStart(self, intent):
        print("NostrClientService: starting NostrManager")
        NostrManager.get_instance().start()

    def onDestroy(self):
        print("NostrClientService: stopping NostrManager")
        NostrManager.get_instance().stop()
