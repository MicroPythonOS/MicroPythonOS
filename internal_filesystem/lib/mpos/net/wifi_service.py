"""
WiFi Service for MicroPythonOS.

Manages WiFi connections including:
- Auto-connect to saved networks on boot
- Network scanning
- Connection management with saved credentials
- Concurrent access locking

This service works alongside ConnectivityManager which monitors connection status.
"""

import ujson
import os
import time

import mpos.config
import mpos.time

# Try to import network module (not available on desktop)
HAS_NETWORK_MODULE = False
try:
    import network
    HAS_NETWORK_MODULE = True
except ImportError:
    print("WifiService: network module not available (desktop mode)")


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

    @staticmethod
    def connect(network_module=None):
        """
        Scan for available networks and connect to the first saved network found.
        Networks are tried in order of signal strength (strongest first).

        Args:
            network_module: Network module for dependency injection (testing)

        Returns:
            bool: True if successfully connected, False otherwise
        """
        # Scan for available networks using internal method
        networks = WifiService._scan_networks_raw(network_module)

        # Sort networks by RSSI (signal strength) in descending order
        # RSSI is at index 3, higher values (less negative) = stronger signal
        networks = sorted(networks, key=lambda n: n[3], reverse=True)

        for n in networks:
            ssid = n[0].decode()
            rssi = n[3]
            print(f"WifiService: Found network '{ssid}' (RSSI: {rssi} dBm)")

            if ssid in WifiService.access_points:
                password = WifiService.access_points.get(ssid).get("password")
                print(f"WifiService: Attempting to connect to saved network '{ssid}'")

                if WifiService.attempt_connecting(ssid, password, network_module=network_module):
                    print(f"WifiService: Connected to '{ssid}'")
                    return True
                else:
                    print(f"WifiService: Failed to connect to '{ssid}'")
            else:
                print(f"WifiService: Skipping '{ssid}' (not configured)")

        print("WifiService: No saved networks found or connected")
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
        print(f"WifiService: Connecting to SSID: {ssid}")

        time_mod = time_module if time_module else time

        # Desktop mode - simulate successful connection
        if not HAS_NETWORK_MODULE and network_module is None:
            print("WifiService: Desktop mode, simulating connection...")
            time_mod.sleep(2)
            WifiService._desktop_connected_ssid = ssid
            print(f"WifiService: Simulated connection to '{ssid}' successful")
            return True

        net = network_module if network_module else network

        try:
            wlan = net.WLAN(net.STA_IF)
            wlan.connect(ssid, password)

            # Wait up to 10 seconds for connection
            for i in range(10):
                if wlan.isconnected():
                    print(f"WifiService: Connected to '{ssid}' after {i+1} seconds")

                    # Sync time from NTP server if possible
                    try:
                        mpos.time.sync_time()
                    except Exception as e:
                        print(f"WifiService: Could not sync time: {e}")

                    return True

                elif not wlan.active():
                    # WiFi was disabled during connection attempt
                    print("WifiService: WiFi disabled during connection, aborting")
                    return False

                print(f"WifiService: Waiting for connection, attempt {i+1}/10")
                time_mod.sleep(1)

            print(f"WifiService: Connection timeout for '{ssid}'")
            return False

        except Exception as e:
            print(f"WifiService: Connection error: {e}")
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
        print("WifiService: Auto-connect thread starting")

        # Load saved access points from config
        WifiService.access_points = mpos.config.SharedPreferences(
            "com.micropythonos.system.wifiservice"
        ).get_dict("access_points")

        if not len(WifiService.access_points):
            print("WifiService: No access points configured, exiting")
            return

        # Check if WiFi is busy (e.g., WiFi app is scanning)
        if WifiService.wifi_busy:
            print("WifiService: WiFi busy, auto-connect aborted")
            return

        WifiService.wifi_busy = True

        try:
            if not HAS_NETWORK_MODULE and network_module is None:
                # Desktop mode - simulate connection delay
                print("WifiService: Desktop mode, simulating connection...")
                time_mod = time_module if time_module else time
                time_mod.sleep(2)
                print("WifiService: Simulated connection complete")
            else:
                # Attempt to connect to saved networks
                if WifiService.connect(network_module=network_module):
                    print("WifiService: Auto-connect successful")
                else:
                    print("WifiService: Auto-connect failed")

                    # Disable WiFi to conserve power if connection failed
                    if network_module:
                        net = network_module
                    else:
                        net = network

                    wlan = net.WLAN(net.STA_IF)
                    wlan.active(False)
                    print("WifiService: WiFi disabled to conserve power")

        finally:
            WifiService.wifi_busy = False
            print("WifiService: Auto-connect thread finished")

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

        # Check actual connection status BEFORE setting wifi_busy
        was_connected = False
        if HAS_NETWORK_MODULE or network_module:
            try:
                net = network_module if network_module else network
                wlan = net.WLAN(net.STA_IF)
                was_connected = wlan.isconnected()
            except Exception as e:
                print(f"WifiService: Error checking connection: {e}")

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

        # Only reconnect if WiFi was connected before we disabled it
        if was_connected:
            try:
                import _thread
                _thread.start_new_thread(WifiService.auto_connect, ())
            except Exception as e:
                print(f"WifiService: Failed to start reconnect thread: {e}")

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
        if not HAS_NETWORK_MODULE and network_module is None:
            return True

        # Check actual connection status
        try:
            net = network_module if network_module else network
            wlan = net.WLAN(net.STA_IF)
            return wlan.isconnected()
        except Exception as e:
            print(f"WifiService: Error checking connection: {e}")
            return False

    @staticmethod
    def disconnect(network_module=None):
        """
        Disconnect from current WiFi network and disable WiFi.

        Args:
            network_module: Network module for dependency injection (testing)
        """
        if not HAS_NETWORK_MODULE and network_module is None:
            print("WifiService: Desktop mode, cannot disconnect")
            return

        try:
            net = network_module if network_module else network
            wlan = net.WLAN(net.STA_IF)
            wlan.disconnect()
            wlan.active(False)
            print("WifiService: Disconnected and WiFi disabled")
        except Exception as e:
            #print(f"WifiService: Error disconnecting: {e}") # probably "Wifi Not Started" so harmless
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
    def get_saved_networks():
        """
        Get list of saved network SSIDs.

        Returns:
            list: List of saved SSIDs
        """
        if not WifiService.access_points:
            WifiService.access_points = mpos.config.SharedPreferences(
                "com.micropythonos.system.wifiservice"
            ).get_dict("access_points")

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
        if not HAS_NETWORK_MODULE and network_module is None:
            # Desktop mode - return empty (no raw data available)
            return []

        net = network_module if network_module else network
        wlan = net.WLAN(net.STA_IF)

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
        if not HAS_NETWORK_MODULE and network_module is None:
            time.sleep(1)
            return ["Home WiFi", "Pretty Fly for a Wi Fi", "Winternet is coming", "The Promised LAN"]

        # Check if already busy
        if WifiService.wifi_busy:
            print("WifiService: scan_networks() - WiFi is busy, returning empty list")
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
        if not HAS_NETWORK_MODULE and network_module is None:
            # Desktop mode - return simulated connected SSID
            return WifiService._desktop_connected_ssid

        net = network_module if network_module else network
        try:
            wlan = net.WLAN(net.STA_IF)
            if wlan.isconnected():
                return wlan.config('essid')
        except Exception as e:
            print(f"WifiService: Error getting current SSID: {e}")
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
        if not WifiService.access_points:
            WifiService.access_points = mpos.config.SharedPreferences(
                "com.micropythonos.system.wifiservice"
            ).get_dict("access_points")

        ap = WifiService.access_points.get(ssid)
        if ap:
            return ap.get("password")
        return None

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
        prefs = mpos.config.SharedPreferences("com.micropythonos.system.wifiservice")
        access_points = prefs.get_dict("access_points")

        # Add or update the network
        network_config = {"password": password}
        if hidden:
            network_config["hidden"] = True
        access_points[ssid] = network_config

        # Save back to config
        editor = prefs.edit()
        editor.put_dict("access_points", access_points)
        editor.commit()

        # Update class-level cache
        WifiService.access_points = access_points

        print(f"WifiService: Saved network '{ssid}' (hidden={hidden})")

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
        prefs = mpos.config.SharedPreferences("com.micropythonos.system.wifiservice")
        access_points = prefs.get_dict("access_points")

        # Remove the network if it exists
        if ssid in access_points:
            del access_points[ssid]

            # Save back to config
            editor = prefs.edit()
            editor.put_dict("access_points", access_points)
            editor.commit()

            # Update class-level cache
            WifiService.access_points = access_points

            print(f"WifiService: Forgot network '{ssid}'")
            return True
        else:
            print(f"WifiService: Network '{ssid}' not found in saved networks")
            return False
