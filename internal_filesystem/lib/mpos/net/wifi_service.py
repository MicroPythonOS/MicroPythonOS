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
    # Used by WiFi app when scanning to avoid conflicts with connection attempts
    wifi_busy = False

    # Dictionary of saved access points {ssid: {password: "..."}}
    access_points = {}

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
        net = network_module if network_module else network
        wlan = net.WLAN(net.STA_IF)

        # Restart WiFi hardware in case it's in a bad state
        wlan.active(False)
        wlan.active(True)

        # Scan for available networks
        networks = wlan.scan()

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

        net = network_module if network_module else network
        time_mod = time_module if time_module else time

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
    def save_network(ssid, password):
        """
        Save a new WiFi network credential.

        Args:
            ssid: Network SSID
            password: Network password
        """
        # Load current saved networks
        prefs = mpos.config.SharedPreferences("com.micropythonos.system.wifiservice")
        access_points = prefs.get_dict("access_points")

        # Add or update the network
        access_points[ssid] = {"password": password}

        # Save back to config
        editor = prefs.edit()
        editor.put_dict("access_points", access_points)
        editor.commit()

        # Update class-level cache
        WifiService.access_points = access_points

        print(f"WifiService: Saved network '{ssid}'")

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
