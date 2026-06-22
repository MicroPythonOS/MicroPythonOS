"""
WiFi Service for MicroPythonOS.

Manages WiFi connections including:
- Auto-connect to saved networks on boot
- Network scanning
- Connection management with saved credentials
- Concurrent access locking

This service works alongside ConnectivityManager which monitors connection status.
"""

import logging
import time

import mpos.shared_preferences
import mpos.time

logger = logging.getLogger(__name__)

WIFI_SERVICE_PREFS_KEY = "com.micropythonos.system.wifiservice" # com.micropythonos.settings.wifi would make more sense but legacy devices use this
HOTSPOT_PREFS_KEY = "com.micropythonos.settings.hotspot"

# Try to import network module (not available on desktop)
HAS_NETWORK_MODULE = False
try:
    import network  # noqa: F401
    HAS_NETWORK_MODULE = True
except ImportError:
    pass


class WifiService:
    """
    Service for managing WiFi connections.

    This class handles connecting to saved WiFi networks and managing
    the WiFi hardware state. It's typically started in a background thread
    on boot to auto-connect to known networks.
    """

    # Class-level lock to prevent concurrent WiFi operations
    # Use is_busy() to check state; operations like scan_networks() manage this automatically
    wifi_busy = False

    # Dictionary of saved access points {ssid: {password: "..."}}
    access_points = {}

    # Desktop mode: simulated connected SSID (None = not connected)
    _desktop_connected_ssid = None

    # Hotspot state tracking
    hotspot_enabled = False
    _temp_disable_state = None
    _needs_hotspot_restore = False

    @staticmethod
    def _is_desktop_mode(network_module=None):
        return not HAS_NETWORK_MODULE and network_module is None

    @staticmethod
    def _get_network_module(network_module=None):
        return network_module if network_module else network

    @staticmethod
    def _get_sta_wlan(net):
        return net.WLAN(net.STA_IF)

    @staticmethod
    def _get_ap_wlan(net):
        return net.WLAN(net.AP_IF)

    @staticmethod
    def _restore_hotspot_if_needed(network_module=None):
        if WifiService._needs_hotspot_restore:
            WifiService._needs_hotspot_restore = False
            WifiService.enable_hotspot(network_module=network_module)

    @staticmethod
    def _get_hotspot_config():
        prefs = mpos.shared_preferences.SharedPreferences(HOTSPOT_PREFS_KEY)
        return {
            "enabled": prefs.get_bool("enabled", False),
            "ssid": prefs.get_string("ssid", "MicroPythonOS"),
            "password": prefs.get_string("password", ""),
            "authmode": prefs.get_string("authmode", None),
        }

    @staticmethod
    def _resolve_hotspot_authmode(net, password, authmode_value):
        if isinstance(authmode_value, int):
            return authmode_value
        if isinstance(authmode_value, str):
            authmode_key = authmode_value.lower().strip()
            if authmode_key == "none":
                return net.AUTH_OPEN
            return net.AUTH_WPA2_PSK
        if authmode_value is None:
            if password:
                return net.AUTH_WPA2_PSK
            return net.AUTH_OPEN
        return net.AUTH_WPA2_PSK

    @staticmethod
    def enable_hotspot(network_module=None):
        if WifiService.wifi_busy:
            if __debug__: logger.debug("Cannot enable hotspot, WiFi is busy")
            return False

        if WifiService._is_desktop_mode(network_module):
            WifiService.hotspot_enabled = True
            if __debug__: logger.debug("Desktop mode, hotspot enabled (simulated)")
            return True

        net = WifiService._get_network_module(network_module)
        config = WifiService._get_hotspot_config()

        try:
            sta = WifiService._get_sta_wlan(net)
            if sta.active() or sta.isconnected():
                sta.disconnect()
                sta.active(False)

            ap = WifiService._get_ap_wlan(net)
            ap.active(True)

            authmode = WifiService._resolve_hotspot_authmode(
                net, config.get("password"), config.get("authmode")
            )

            ap_config = {
                "essid": config.get("ssid"),
                "authmode": authmode,
            }
            if config.get("password"):
                ap_config["password"] = config.get("password")

            ap.config(**ap_config)
            ap.ifconfig(("192.168.4.1", "255.255.255.0", "192.168.4.1", "8.8.8.8"))

            WifiService.hotspot_enabled = True
            if __debug__: logger.debug("Hotspot enabled")
            return True
        except Exception as e:
            try:
                ap = WifiService._get_ap_wlan(net)
                ap.active(False)
            except Exception:
                pass
            WifiService.hotspot_enabled = False
            logger.error("Failed to enable hotspot: %s", e)
            return False

    @staticmethod
    def disable_hotspot(network_module=None):
        if WifiService._is_desktop_mode(network_module):
            WifiService.hotspot_enabled = False
            if __debug__: logger.debug("Desktop mode, hotspot disabled (simulated)")
            return

        try:
            net = WifiService._get_network_module(network_module)
            ap = WifiService._get_ap_wlan(net)
            ap.active(False)
            WifiService.hotspot_enabled = False
            if __debug__: logger.debug("Hotspot disabled")
        except Exception:
            WifiService.hotspot_enabled = False

    @staticmethod
    def is_hotspot_enabled(network_module=None):
        if WifiService._is_desktop_mode(network_module):
            return WifiService.hotspot_enabled
        try:
            net = WifiService._get_network_module(network_module)
            ap = WifiService._get_ap_wlan(net)
            WifiService.hotspot_enabled = ap.active()
            return WifiService.hotspot_enabled
        except Exception:
            return WifiService.hotspot_enabled

    @staticmethod
    def connect(network_module=None, time_module=None):
        """
        Scan for available networks and connect to the first saved network found.
        Networks are tried in order of signal strength (strongest first).
        Hidden networks are also tried even if they don't appear in the scan.

        Args:
            network_module: Network module for dependency injection (testing)
            time_module: Time module for dependency injection (testing)

        Returns:
            bool: True if successfully connected, False otherwise
        """
        # Scan for available networks using internal method
        networks = WifiService._scan_networks_raw(network_module)

        # Sort networks by RSSI (signal strength) in descending order
        # RSSI is at index 3, higher values (less negative) = stronger signal
        networks = sorted(networks, key=lambda n: n[3], reverse=True)

        # Track which SSIDs we've tried (to avoid retrying hidden networks)
        tried_ssids = set()

        for n in networks:
            ssid = n[0].decode()
            rssi = n[3]
            tried_ssids.add(ssid)
            if __debug__: logger.debug("Found network '%s' (RSSI: %s dBm)", ssid, rssi)

            if ssid in WifiService.access_points:
                password = WifiService.access_points.get(ssid).get("password")
                if __debug__: logger.debug("Attempting to connect to saved network '%s'", ssid)

                if WifiService.attempt_connecting(
                    ssid,
                    password,
                    network_module=network_module,
                    time_module=time_module,
                ):
                    if __debug__: logger.debug("Connected to '%s'", ssid)
                    return True
                else:
                    logger.error("Failed to connect to '%s'", ssid)
            else:
                if __debug__: logger.debug("Skipping '%s' (not configured)", ssid)

        # Try hidden networks that weren't in the scan results
        for ssid, config in WifiService.access_points.items():
            if config.get("hidden") and ssid not in tried_ssids:
                password = config.get("password")
                if __debug__: logger.debug("Attempting hidden network '%s'", ssid)

                if WifiService.attempt_connecting(
                    ssid,
                    password,
                    network_module=network_module,
                    time_module=time_module,
                ):
                    if __debug__: logger.debug("Connected to hidden network '%s'", ssid)
                    return True
                else:
                    logger.error("Failed to connect to hidden network '%s'", ssid)

        if __debug__: logger.debug("No saved networks found or connected")
        return False

    @staticmethod
    def attempt_connecting(ssid, password, network_module=None, time_module=None):
        """
        Attempt to connect to a specific WiFi network.

        Args:
            ssid: Network SSID to connect to
            password: Network password
            network_module: Network module for dependency injection (testing)
            time_module: Time module for dependency injection (testing)

        Returns:
            bool: True if successfully connected, False otherwise
        """
        if __debug__: logger.debug("Connecting to SSID: %s", ssid)

        time_mod = time_module if time_module else time

        if WifiService.is_hotspot_enabled(network_module=network_module):
            WifiService._needs_hotspot_restore = True
            WifiService.disable_hotspot(network_module=network_module)

        # Desktop mode - simulate successful connection
        if WifiService._is_desktop_mode(network_module):
            if __debug__: logger.debug("Desktop mode, simulating connection...")
            time_mod.sleep(2)
            WifiService._desktop_connected_ssid = ssid
            if __debug__: logger.debug("Simulated connection to '%s' successful", ssid)
            return True

        net = WifiService._get_network_module(network_module)

        try:
            wlan = WifiService._get_sta_wlan(net)
            wlan.connect(ssid, password)

            # Wait up to 10 seconds for connection
            for i in range(10):
                if wlan.isconnected():
                    if __debug__: logger.debug("Connected to '%s' after %s seconds with IP: %s", ssid, i+1, wlan.ipconfig('addr4'))

                    # Sync time from NTP server if possible
                    try:
                        mpos.time.sync_time()
                    except Exception as e:
                        logger.warning("Could not sync time: %s", e)

                    WifiService._needs_hotspot_restore = False
                    return True

                elif not wlan.active():
                    # WiFi was disabled during connection attempt
                    if __debug__: logger.debug("WiFi disabled during connection, aborting")
                    WifiService._restore_hotspot_if_needed(network_module=network_module)
                    return False

                if __debug__: logger.debug("Waiting for connection, attempt %s/10", i+1)
                time_mod.sleep(1)

            logger.warning("Connection timeout for '%s'", ssid)
            WifiService._restore_hotspot_if_needed(network_module=network_module)
            return False

        except Exception as e:
            logger.error("Connection error: %s", e)
            WifiService._restore_hotspot_if_needed(network_module=network_module)
            return False

    @staticmethod
    def auto_connect(network_module=None, time_module=None):
        """
        Auto-connect to a saved WiFi network on boot.

        This is typically called in a background thread from main.py.
        It loads saved networks and attempts to connect to the first one found.

        Args:
            network_module: Network module for dependency injection (testing)
            time_module: Time module for dependency injection (testing)
        """
        if __debug__: logger.debug("Auto-connect thread starting")

        hotspot_config = WifiService._get_hotspot_config()
        if hotspot_config.get("enabled"):
            if __debug__: logger.debug("Hotspot enabled, skipping STA auto-connect")
            WifiService.enable_hotspot(network_module=network_module)
            return
        if WifiService.is_hotspot_enabled(network_module=network_module):
            WifiService._needs_hotspot_restore = True
            WifiService.disable_hotspot(network_module=network_module)

        # Load saved access points from config
        WifiService.access_points = mpos.shared_preferences.SharedPreferences(
            WIFI_SERVICE_PREFS_KEY
        ).get_dict("access_points")

        if not len(WifiService.access_points):
            WifiService._restore_hotspot_if_needed(network_module=network_module)
            if __debug__: logger.debug("No access points configured, exiting")
            return

        # Check if WiFi is busy (e.g., WiFi app is scanning)
        if WifiService.wifi_busy:
            WifiService._restore_hotspot_if_needed(network_module=network_module)
            if __debug__: logger.debug("WiFi busy, auto-connect aborted")
            return

        WifiService.wifi_busy = True
        connected = False

        try:
            if WifiService._is_desktop_mode(network_module):
                # Desktop mode - simulate connection delay
                if __debug__: logger.debug("Desktop mode, simulating connection...")
                time_mod = time_module if time_module else time
                time_mod.sleep(2)
                connected = True
                if __debug__: logger.debug("Simulated connection complete")
            else:
                # Attempt to connect to saved networks
                if WifiService.connect(
                    network_module=network_module,
                    time_module=time_module,
                ):
                    connected = True
                    if __debug__: logger.debug("Auto-connect successful")
                else:
                    logger.error("Auto-connect failed")

                    # Disable WiFi to conserve power if connection failed
                    net = WifiService._get_network_module(network_module)
                    wlan = WifiService._get_sta_wlan(net)
                    wlan.active(False)
                    if __debug__: logger.debug("WiFi disabled to conserve power")

        finally:
            if not connected:
                WifiService._restore_hotspot_if_needed(network_module=network_module)
            WifiService.wifi_busy = False
            if __debug__: logger.debug("Auto-connect thread finished")

    @staticmethod
    def temporarily_disable(network_module=None):
        """
        Temporarily disable WiFi for operations that require it (e.g., ESP32-S3 ADC2).

        This method sets wifi_busy flag and disconnects WiFi if connected.
        Caller must call temporarily_enable() in a finally block.

        Args:
            network_module: Network module for dependency injection (testing)

        Returns:
            bool: True if WiFi was connected before disabling, False otherwise

        Raises:
            RuntimeError: If WiFi operations are already in progress
        """
        if WifiService.wifi_busy:
            raise RuntimeError("Cannot disable WiFi: WifiService is already busy")

        was_connected = False
        hotspot_was_enabled = False
        if HAS_NETWORK_MODULE or network_module:
            try:
                net = WifiService._get_network_module(network_module)
                wlan = WifiService._get_sta_wlan(net)
                was_connected = wlan.isconnected()
                ap = WifiService._get_ap_wlan(net)
                hotspot_was_enabled = ap.active()
            except Exception as e:
                logger.error("Error checking connection: %s", e)

        WifiService._temp_disable_state = {
            "was_connected": was_connected,
            "hotspot_was_enabled": hotspot_was_enabled,
        }

        # Now set busy flag and disconnect
        WifiService.wifi_busy = True
        WifiService.disconnect(network_module=network_module)

        return was_connected

    @staticmethod
    def temporarily_enable(was_connected, network_module=None):
        """
        Re-enable WiFi after temporary disable operation.

        Must be called in a finally block after temporarily_disable().

        Args:
            was_connected: Return value from temporarily_disable()
            network_module: Network module for dependency injection (testing)
        """
        WifiService.wifi_busy = False

        state = WifiService._temp_disable_state or {}
        WifiService._temp_disable_state = None

        if state.get("hotspot_was_enabled"):
            WifiService.enable_hotspot(network_module=network_module)

        # Only reconnect if WiFi was connected before we disabled it
        if was_connected:
            try:
                import _thread
                _thread.start_new_thread(WifiService.auto_connect, ())
            except Exception as e:
                logger.error("Failed to start reconnect thread: %s", e)

    @staticmethod
    def is_connected(network_module=None):
        """
        Check if WiFi is currently connected.

        This is a simple connection check. For comprehensive connectivity
        monitoring with callbacks, use ConnectivityManager instead.

        Args:
            network_module: Network module for dependency injection (testing)

        Returns:
            bool: True if connected, False otherwise
        """
        # If WiFi operations are in progress, report not connected
        if WifiService.wifi_busy:
            return False

        # Desktop mode - always report connected
        if WifiService._is_desktop_mode(network_module):
            return True

        try:
            net = WifiService._get_network_module(network_module)
            if WifiService.is_hotspot_enabled(network_module=network_module):
                ap = WifiService._get_ap_wlan(net)
                return ap.active()
            wlan = WifiService._get_sta_wlan(net)
            return wlan.isconnected()
        except Exception as e:
            logger.error("Error checking connection: %s", e)
            return False


    @staticmethod
    def _get_ipv4_value(network_module, ap_index, sta_key, desktop_value, label):
        if WifiService.wifi_busy:
            return None

        if WifiService._is_desktop_mode(network_module):
            return desktop_value

        try:
            net = WifiService._get_network_module(network_module)
            if WifiService.is_hotspot_enabled(network_module=network_module):
                ap = WifiService._get_ap_wlan(net)
                return ap.ifconfig()[ap_index]
            wlan = WifiService._get_sta_wlan(net)
            value = wlan.ipconfig(sta_key)
            if isinstance(value, tuple):
                return value[0] if value else None
            return value
        except Exception as e:
            logger.error("Error retrieving ipv4 %s: %s", label, e)
            return None

    @staticmethod
    def get_ipv4_address(network_module=None):
        return WifiService._get_ipv4_value(
            network_module=network_module,
            ap_index=0,
            sta_key="addr4",
            desktop_value="127.0.0.1",
            label="address",
        )

    @staticmethod
    def get_ipv4_netmask(network_module=None):
        return WifiService._get_ipv4_value(
            network_module=network_module,
            ap_index=1,
            sta_key="addr4",
            desktop_value="255.255.255.0",
            label="netmask",
        )

    @staticmethod
    def get_ipv4_gateway(network_module=None):
        return WifiService._get_ipv4_value(
            network_module=network_module,
            ap_index=2,
            sta_key="gw4",
            desktop_value="",
            label="gateway",
        )

    @staticmethod
    def disconnect(network_module=None):
        """
        Disconnect from current WiFi network and disable WiFi.

        Args:
            network_module: Network module for dependency injection (testing)
        """
        if WifiService._is_desktop_mode(network_module):
            if __debug__: logger.debug("Desktop mode, cannot disconnect")
            return

        try:
            net = WifiService._get_network_module(network_module)
            wlan = WifiService._get_sta_wlan(net)
            wlan.disconnect()
            wlan.active(False)
            ap = WifiService._get_ap_wlan(net)
            ap.active(False)
            WifiService.hotspot_enabled = False
            if __debug__: logger.debug("Disconnected and WiFi disabled")
        except Exception as e:
            pass

    @staticmethod
    def is_busy():
        """
        Check if WiFi operations are currently in progress.

        Use this to check if scanning or other WiFi operations can be started.
        Operations like scan_networks() manage the busy flag automatically.

        Returns:
            bool: True if WiFi is busy, False if available
        """
        return WifiService.wifi_busy

    @staticmethod
    def _ensure_access_points_loaded():
        if not WifiService.access_points:
            WifiService.access_points = mpos.shared_preferences.SharedPreferences(
                WIFI_SERVICE_PREFS_KEY
            ).get_dict("access_points")

    @staticmethod
    def get_saved_networks():
        """
        Get list of saved network SSIDs.

        Returns:
            list: List of saved SSIDs
        """
        WifiService._ensure_access_points_loaded()
        return list(WifiService.access_points.keys())

    @staticmethod
    def _scan_networks_raw(network_module=None):
        """
        Internal method to scan for available WiFi networks and return raw data.

        Args:
            network_module: Network module for dependency injection (testing)

        Returns:
            list: Raw network tuples from wlan.scan(), or empty list on desktop
        """
        if WifiService._is_desktop_mode(network_module):
            # Desktop mode - return empty (no raw data available)
            return []

        net = WifiService._get_network_module(network_module)
        wlan = WifiService._get_sta_wlan(net)

        # Restart WiFi hardware in case it is in a bad state (only if not connected)
        if not wlan.isconnected():
            wlan.active(False)
            wlan.active(True)

        return wlan.scan()

    @staticmethod
    def scan_networks(network_module=None):
        """
        Scan for available WiFi networks.

        This method manages the wifi_busy flag internally. If WiFi is already busy,
        returns an empty list. The busy flag is automatically cleared when scanning
        completes (even on error).

        Args:
            network_module: Network module for dependency injection (testing)

        Returns:
            list: List of SSIDs found, empty list if busy, or mock data on desktop
        """
        # Desktop mode - return mock SSIDs (no busy flag needed)
        if WifiService._is_desktop_mode(network_module):
            time.sleep(1)
            return ["Home WiFi", "Pretty Fly for a Wi Fi", "Winternet is coming", "The Promised LAN"]

        # Check if already busy
        if WifiService.wifi_busy:
            if __debug__: logger.debug("scan_networks() - WiFi is busy, returning empty list")
            return []

        WifiService.wifi_busy = True
        try:
            networks = WifiService._scan_networks_raw(network_module)
            # Return unique SSIDs, filtering out empty ones and invalid lengths
            ssids = list(set(n[0].decode() for n in networks if n[0]))
            return [s for s in ssids if 0 < len(s) <= 32]
        finally:
            WifiService.wifi_busy = False

    @staticmethod
    def get_current_ssid(network_module=None):
        """
        Get the SSID of the currently connected network.

        Args:
            network_module: Network module for dependency injection (testing)

        Returns:
            str or None: Current SSID if connected, None otherwise
        """
        if WifiService._is_desktop_mode(network_module):
            # Desktop mode - return simulated connected SSID
            return WifiService._desktop_connected_ssid

        net = WifiService._get_network_module(network_module)
        try:
            wlan = WifiService._get_sta_wlan(net)
            if wlan.isconnected():
                return wlan.config("essid")
        except Exception as e:
            logger.error("Error getting current SSID: %s", e)
        return None

    @staticmethod
    def get_network_password(ssid):
        """
        Get the saved password for a network.

        Args:
            ssid: Network SSID

        Returns:
            str or None: Password if found, None otherwise
        """
        WifiService._ensure_access_points_loaded()

        ap = WifiService.access_points.get(ssid)
        if ap:
            return ap.get("password")
        return None

    @staticmethod
    def get_network_hidden(ssid):
        """
        Get the hidden flag for a network.

        Args:
            ssid: Network SSID

        Returns:
            bool: True if network is hidden, False otherwise
        """
        WifiService._ensure_access_points_loaded()

        ap = WifiService.access_points.get(ssid)
        if ap:
            return ap.get("hidden", False)
        return False

    @staticmethod
    def save_network(ssid, password, hidden=False):
        """
        Save a new WiFi network credential.

        Args:
            ssid: Network SSID
            password: Network password
            hidden: Whether this is a hidden network (always try connecting)
        """
        # Load current saved networks
        prefs = mpos.shared_preferences.SharedPreferences(WIFI_SERVICE_PREFS_KEY)

        # Build the network config
        network_config = {"password": password}
        if hidden:
            network_config["hidden"] = True

        # Modify the deep copy inside the editor, not prefs.data directly,
        # otherwise the no-op guard in commit() sees no change and skips writing.
        editor = prefs.edit()
        editor.put_dict_item("access_points", ssid, network_config)
        editor.commit()

        # Update class-level cache
        WifiService.access_points = prefs.get_dict("access_points")

        if __debug__: logger.debug("Saved network '%s' (hidden=%s)", ssid, hidden)

    @staticmethod
    def forget_network(ssid):
        """
        Remove a saved WiFi network.

        Args:
            ssid: Network SSID to forget

        Returns:
            bool: True if network was found and removed, False otherwise
        """
        # Load current saved networks
        prefs = mpos.shared_preferences.SharedPreferences(WIFI_SERVICE_PREFS_KEY)

        # Check if the network exists without mutating prefs.data
        if ssid not in prefs.get_dict("access_points"):
            return False

        # Modify the deep copy inside the editor, not prefs.data directly,
        # otherwise the no-op guard in commit() sees no change and skips writing.
        editor = prefs.edit()
        editor.remove_dict_item("access_points", ssid)
        editor.commit()

        # Update class-level cache
        WifiService.access_points = prefs.get_dict("access_points")

        if __debug__: logger.debug("Forgot network '%s'", ssid)
        return True
