import unittest
import sys

# Add tests directory to path for network_test_helper
sys.path.insert(0, "../tests")

# Import network test helpers
from network_test_helper import MockNetwork, MockTime

from mocks import HotspotMockNetwork, MockMpos, MockSharedPreferences

# Inject mocks before importing WifiService
sys.modules["mpos"] = MockMpos
sys.modules["mpos.config"] = MockMpos.config
sys.modules["mpos.time"] = MockMpos.time

# Add path to wifi_service.py
sys.path.append("lib/mpos/net")

# Import WifiService
from wifi_service import WifiService


class TestWifiServiceConnect(unittest.TestCase):
    """Test WifiService.connect() method."""

    def setUp(self):
        """Set up test fixtures."""
        MockSharedPreferences.reset_all()
        WifiService.access_points = {}
        WifiService.wifi_busy = False

    def tearDown(self):
        """Clean up after test."""
        WifiService.access_points = {}
        WifiService.wifi_busy = False

    def test_connect_to_saved_network(self):
        """Test connecting to a saved network."""
        mock_network = MockNetwork(connected=False)
        WifiService.access_points = {
            "TestNetwork": {"password": "testpass123"}
        }

        # Configure mock scan results
        mock_wlan = mock_network.WLAN(mock_network.STA_IF)
        mock_wlan._scan_results = [(b"TestNetwork", -50, 1, 3, b"", 0)]

        # Mock connect to succeed immediately
        def mock_connect(ssid, password):
            mock_wlan._connected = True

        mock_wlan.connect = mock_connect

        result = WifiService.connect(network_module=mock_network, time_module=MockTime())

        self.assertTrue(result)

    def test_connect_with_no_saved_networks(self):
        """Test connecting when no networks are saved."""
        mock_network = MockNetwork(connected=False)
        WifiService.access_points = {}

        mock_wlan = mock_network.WLAN(mock_network.STA_IF)
        mock_wlan._scan_results = [(b"UnsavedNetwork", -50, 1, 3, b"", 0)]

        result = WifiService.connect(network_module=mock_network, time_module=MockTime())

        self.assertFalse(result)

    def test_connect_when_no_saved_networks_available(self):
        """Test connecting when saved networks aren't in range."""
        mock_network = MockNetwork(connected=False)
        WifiService.access_points = {
            "SavedNetwork": {"password": "password123"}
        }

        mock_wlan = mock_network.WLAN(mock_network.STA_IF)
        mock_wlan._scan_results = [(b"DifferentNetwork", -50, 1, 3, b"", 0)]

        result = WifiService.connect(network_module=mock_network, time_module=MockTime())

        self.assertFalse(result)


class TestWifiServiceAttemptConnecting(unittest.TestCase):
    """Test WifiService.attempt_connecting() method."""

    def test_successful_connection(self):
        """Test successful WiFi connection."""
        mock_network = MockNetwork(connected=False)
        mock_time = MockTime()

        mock_wlan = mock_network.WLAN(mock_network.STA_IF)

        # Mock connect to succeed immediately
        call_count = [0]

        def mock_connect(ssid, password):
            pass  # Don't set connected yet

        def mock_isconnected():
            call_count[0] += 1
            if call_count[0] >= 1:
                return True
            return False

        mock_wlan.connect = mock_connect
        mock_wlan.isconnected = mock_isconnected

        result = WifiService.attempt_connecting(
            "TestSSID",
            "testpass",
            network_module=mock_network,
            time_module=mock_time
        )

        self.assertTrue(result)
        # Should not sleep once connected immediately
        self.assertEqual(len(mock_time.get_sleep_calls()), 0)

    def test_connection_timeout(self):
        """Test connection timeout after 10 attempts."""
        mock_network = MockNetwork(connected=False)
        mock_time = MockTime()

        mock_wlan = mock_network.WLAN(mock_network.STA_IF)

        # Connection never succeeds
        def mock_isconnected():
            return False

        mock_wlan.isconnected = mock_isconnected

        result = WifiService.attempt_connecting(
            "TestSSID",
            "testpass",
            network_module=mock_network,
            time_module=mock_time
        )

        self.assertFalse(result)
        # Should have slept 10 times
        self.assertEqual(len(mock_time.get_sleep_calls()), 10)

    def test_connection_aborted_when_wifi_disabled(self):
        """Test connection aborts if WiFi is disabled during attempt."""
        mock_network = MockNetwork(connected=False)
        mock_time = MockTime()

        mock_wlan = mock_network.WLAN(mock_network.STA_IF)

        # Never connected
        def mock_isconnected():
            return False

        # WiFi becomes inactive on 3rd check
        check_count = [0]

        def mock_active(state=None):
            if state is not None:
                mock_wlan._active = state
                return None
            check_count[0] += 1
            if check_count[0] >= 3:
                return False
            return True

        mock_wlan.isconnected = mock_isconnected
        mock_wlan.active = mock_active

        result = WifiService.attempt_connecting(
            "TestSSID",
            "testpass",
            network_module=mock_network,
            time_module=mock_time
        )

        self.assertFalse(result)
        # Should have checked less than 10 times (aborted early)
        self.assertTrue(check_count[0] < 10)
        # Should have slept only until abort
        self.assertEqual(len(mock_time.get_sleep_calls()), 2)

    def test_connection_error_handling(self):
        """Test handling of connection errors."""
        mock_network = MockNetwork(connected=False)
        mock_time = MockTime()

        mock_wlan = mock_network.WLAN(mock_network.STA_IF)

        def raise_error(ssid, password):
            raise Exception("Connection failed")

        mock_wlan.connect = raise_error

        result = WifiService.attempt_connecting(
            "TestSSID",
            "testpass",
            network_module=mock_network,
            time_module=mock_time
        )

        self.assertFalse(result)


class TestWifiServiceAutoConnect(unittest.TestCase):
    """Test WifiService.auto_connect() method."""

    def setUp(self):
        """Set up test fixtures."""
        MockSharedPreferences.reset_all()
        WifiService.access_points = {}
        WifiService.wifi_busy = False

    def tearDown(self):
        """Clean up after test."""
        WifiService.access_points = {}
        WifiService.wifi_busy = False
        MockSharedPreferences.reset_all()

    def test_auto_connect_with_no_saved_networks(self):
        """Test auto_connect when no networks are saved."""
        WifiService.auto_connect()

        # Should exit early
        self.assertEqual(len(WifiService.access_points), 0)

    def test_auto_connect_when_wifi_busy(self):
        """Test auto_connect aborts when WiFi is busy."""
        # Save a network
        prefs = MockSharedPreferences("com.micropythonos.system.wifiservice")
        editor = prefs.edit()
        editor.put_dict("access_points", {"TestNet": {"password": "pass"}})
        editor.commit()

        # Set WiFi as busy
        WifiService.wifi_busy = True

        WifiService.auto_connect()

        # Should still be busy (not changed)
        self.assertTrue(WifiService.wifi_busy)

    def test_auto_connect_desktop_mode(self):
        """Test auto_connect in desktop mode (no network module)."""
        mock_time = MockTime()

        # Save a network
        prefs = MockSharedPreferences("com.micropythonos.system.wifiservice")
        editor = prefs.edit()
        editor.put_dict("access_points", {"TestNet": {"password": "pass"}})
        editor.commit()

        WifiService.auto_connect(network_module=None, time_module=mock_time)

        # Should have "slept" to simulate connection
        self.assertTrue(len(mock_time.get_sleep_calls()) > 0)
        # Should clear wifi_busy flag
        self.assertFalse(WifiService.wifi_busy)


class TestWifiServiceIsConnected(unittest.TestCase):
    """Test WifiService.is_connected() method."""

    def setUp(self):
        """Set up test fixtures."""
        WifiService.wifi_busy = False

    def tearDown(self):
        """Clean up after test."""
        WifiService.wifi_busy = False

    def test_is_connected_when_connected(self):
        """Test is_connected returns True when WiFi is connected."""
        mock_network = MockNetwork(connected=True)

        result = WifiService.is_connected(network_module=mock_network)

        self.assertTrue(result)

    def test_is_connected_when_disconnected(self):
        """Test is_connected returns False when WiFi is disconnected."""
        mock_network = HotspotMockNetwork()
        ap_wlan = mock_network.WLAN(mock_network.AP_IF)
        ap_wlan.active(False)

        result = WifiService.is_connected(network_module=mock_network)

        self.assertFalse(result)

    def test_is_connected_when_wifi_busy(self):
        """Test is_connected returns False when WiFi is busy."""
        mock_network = MockNetwork(connected=True)
        WifiService.wifi_busy = True

        result = WifiService.is_connected(network_module=mock_network)

        # Should return False even though connected
        self.assertFalse(result)

    def test_is_connected_when_hotspot_enabled(self):
        """Test is_connected checks AP state when hotspot is enabled."""
        mock_network = HotspotMockNetwork()
        ap_wlan = mock_network.WLAN(mock_network.AP_IF)
        ap_wlan.active(True)
        WifiService.hotspot_enabled = True

        result = WifiService.is_connected(network_module=mock_network)

        self.assertTrue(result)

    def test_is_connected_desktop_mode(self):
        """Test is_connected in desktop mode."""
        result = WifiService.is_connected(network_module=None)

        # Desktop mode always returns True
        self.assertTrue(result)


class TestWifiServiceNetworkManagement(unittest.TestCase):
    """Test network save/forget functionality."""

    def setUp(self):
        """Set up test fixtures."""
        MockSharedPreferences.reset_all()
        WifiService.access_points = {}

    def tearDown(self):
        """Clean up after test."""
        WifiService.access_points = {}
        MockSharedPreferences.reset_all()

    def test_save_network(self):
        """Test saving a network."""
        WifiService.save_network("MyNetwork", "mypassword123")

        # Should be in class-level cache
        self.assertTrue("MyNetwork" in WifiService.access_points)
        self.assertEqual(WifiService.access_points["MyNetwork"]["password"], "mypassword123")

        # Should be persisted
        prefs = MockSharedPreferences("com.micropythonos.system.wifiservice")
        saved = prefs.get_dict("access_points")
        self.assertTrue("MyNetwork" in saved)

    def test_save_network_updates_existing(self):
        """Test updating an existing saved network."""
        WifiService.save_network("MyNetwork", "oldpassword")
        WifiService.save_network("MyNetwork", "newpassword")

        # Should have new password
        self.assertEqual(WifiService.access_points["MyNetwork"]["password"], "newpassword")

    def test_forget_network(self):
        """Test forgetting a saved network."""
        WifiService.save_network("MyNetwork", "mypassword")

        result = WifiService.forget_network("MyNetwork")

        self.assertTrue(result)
        self.assertFalse("MyNetwork" in WifiService.access_points)

    def test_forget_nonexistent_network(self):
        """Test forgetting a network that doesn't exist."""
        result = WifiService.forget_network("NonExistent")

        self.assertFalse(result)

    def test_get_saved_networks(self):
        """Test getting list of saved networks."""
        WifiService.save_network("Network1", "pass1")
        WifiService.save_network("Network2", "pass2")
        WifiService.save_network("Network3", "pass3")

        saved = WifiService.get_saved_networks()

        self.assertEqual(len(saved), 3)
        self.assertTrue("Network1" in saved)
        self.assertTrue("Network2" in saved)
        self.assertTrue("Network3" in saved)

    def test_get_saved_networks_empty(self):
        """Test getting saved networks when none exist."""
        saved = WifiService.get_saved_networks()

        self.assertEqual(len(saved), 0)


class TestWifiServiceHotspot(unittest.TestCase):
    """Test hotspot configuration and mode switching."""

    def setUp(self):
        """Set up test fixtures."""
        MockSharedPreferences.reset_all()
        WifiService.hotspot_enabled = False
        WifiService.wifi_busy = False
        WifiService._needs_hotspot_restore = False

    def tearDown(self):
        """Clean up after test."""
        WifiService.hotspot_enabled = False
        WifiService.wifi_busy = False
        WifiService._needs_hotspot_restore = False
        MockSharedPreferences.reset_all()

    def test_enable_hotspot_applies_config(self):
        """Test enable_hotspot reads config and configures AP."""
        prefs = MockSharedPreferences("com.micropythonos.settings.hotspot")
        editor = prefs.edit()
        editor.put_bool("enabled", True)
        editor.put_string("ssid", "MyAP")
        editor.put_string("password", "ap-pass")
        editor.put_string("authmode", "wpa2")
        editor.commit()

        mock_network = HotspotMockNetwork()
        ap_wlan = mock_network.WLAN(mock_network.AP_IF)
        sta_wlan = mock_network.WLAN(mock_network.STA_IF)
        sta_wlan.active(True)
        sta_wlan._connected = True

        result = WifiService.enable_hotspot(network_module=mock_network)

        self.assertTrue(result)
        self.assertTrue(WifiService.hotspot_enabled)
        self.assertTrue(ap_wlan.active())
        self.assertFalse(sta_wlan.active())
        self.assertEqual(ap_wlan._config.get("essid"), "MyAP")
        self.assertEqual(ap_wlan._config.get("authmode"), mock_network.AUTH_WPA2_PSK)
        self.assertEqual(ap_wlan._config.get("password"), "ap-pass")

    def test_enable_hotspot_respects_busy_flag(self):
        """Test enable_hotspot returns False when WiFi is busy."""
        WifiService.wifi_busy = True
        mock_network = HotspotMockNetwork()

        result = WifiService.enable_hotspot(network_module=mock_network)

        self.assertFalse(result)
        self.assertFalse(WifiService.hotspot_enabled)

    def test_disable_hotspot_deactivates_ap(self):
        """Test disable_hotspot turns off AP and updates flag."""
        mock_network = HotspotMockNetwork()
        ap_wlan = mock_network.WLAN(mock_network.AP_IF)
        ap_wlan.active(True)
        WifiService.hotspot_enabled = True

        WifiService.disable_hotspot(network_module=mock_network)

        self.assertFalse(ap_wlan.active())
        self.assertFalse(WifiService.hotspot_enabled)

    def test_enable_hotspot_desktop_mode(self):
        """Test enable_hotspot in desktop mode uses simulated flag."""
        result = WifiService.enable_hotspot(network_module=None)

        self.assertTrue(result)
        self.assertTrue(WifiService.hotspot_enabled)

    def test_disable_hotspot_desktop_mode(self):
        """Test disable_hotspot in desktop mode uses simulated flag."""
        WifiService.hotspot_enabled = True

        WifiService.disable_hotspot(network_module=None)

        self.assertFalse(WifiService.hotspot_enabled)

    def test_auto_connect_with_hotspot_enabled_prefers_ap_mode(self):
        """Test auto_connect uses hotspot mode when enabled in config."""
        prefs = MockSharedPreferences("com.micropythonos.settings.hotspot")
        editor = prefs.edit()
        editor.put_bool("enabled", True)
        editor.commit()

        mock_network = HotspotMockNetwork()

        WifiService.auto_connect(network_module=mock_network, time_module=MockTime())

        ap_wlan = mock_network.WLAN(mock_network.AP_IF)
        self.assertTrue(ap_wlan.active())
        self.assertTrue(WifiService.hotspot_enabled)

    def test_attempt_connecting_temporarily_disables_hotspot(self):
        """Test STA connect disables hotspot and leaves it off on success."""
        mock_network = HotspotMockNetwork()
        ap_wlan = mock_network.WLAN(mock_network.AP_IF)
        ap_wlan.active(True)
        WifiService.hotspot_enabled = True

        sta_wlan = mock_network.WLAN(mock_network.STA_IF)
        call_count = [0]

        def mock_isconnected():
            call_count[0] += 1
            return call_count[0] >= 1

        sta_wlan.isconnected = mock_isconnected

        result = WifiService.attempt_connecting(
            "TestSSID",
            "pass",
            network_module=mock_network,
            time_module=MockTime(),
        )

        self.assertTrue(result)
        self.assertFalse(WifiService.hotspot_enabled)
        self.assertFalse(ap_wlan.active())

    def test_attempt_connecting_restores_hotspot_on_timeout(self):
        """Test STA connect restores hotspot when connection times out."""
        mock_network = HotspotMockNetwork()
        ap_wlan = mock_network.WLAN(mock_network.AP_IF)
        ap_wlan.active(True)
        WifiService.hotspot_enabled = True

        sta_wlan = mock_network.WLAN(mock_network.STA_IF)

        def mock_isconnected():
            return False

        sta_wlan.isconnected = mock_isconnected

        result = WifiService.attempt_connecting(
            "TestSSID",
            "pass",
            network_module=mock_network,
            time_module=MockTime(),
        )

        self.assertFalse(result)
        self.assertTrue(WifiService.hotspot_enabled)
        self.assertTrue(ap_wlan.active())

    def test_attempt_connecting_restores_hotspot_on_abort(self):
        """Test STA connect restores hotspot if WiFi is disabled mid-try."""
        mock_network = HotspotMockNetwork()
        ap_wlan = mock_network.WLAN(mock_network.AP_IF)
        ap_wlan.active(True)
        WifiService.hotspot_enabled = True

        sta_wlan = mock_network.WLAN(mock_network.STA_IF)

        def mock_isconnected():
            return False

        def mock_active(state=None):
            if state is not None:
                sta_wlan._active = state
                return None
            return False

        sta_wlan.isconnected = mock_isconnected
        sta_wlan.active = mock_active

        result = WifiService.attempt_connecting(
            "TestSSID",
            "pass",
            network_module=mock_network,
            time_module=MockTime(),
        )

        self.assertFalse(result)
        self.assertTrue(WifiService.hotspot_enabled)
        self.assertTrue(ap_wlan.active())


class TestWifiServiceTemporaryDisable(unittest.TestCase):
    """Test temporarily_disable/temporarily_enable behavior."""

    def setUp(self):
        """Set up test fixtures."""
        WifiService.wifi_busy = False
        WifiService._temp_disable_state = None
        WifiService.hotspot_enabled = False

    def tearDown(self):
        """Clean up after test."""
        WifiService.wifi_busy = False
        WifiService._temp_disable_state = None
        WifiService.hotspot_enabled = False

    def test_temporarily_disable_raises_when_busy(self):
        """Test temporarily_disable raises if wifi_busy is set."""
        WifiService.wifi_busy = True

        with self.assertRaises(RuntimeError):
            WifiService.temporarily_disable(network_module=HotspotMockNetwork())

    def test_temporarily_disable_disconnects_and_tracks_state(self):
        """Test temporarily_disable stores state and disconnects."""
        mock_network = HotspotMockNetwork()
        sta_wlan = mock_network.WLAN(mock_network.STA_IF)
        ap_wlan = mock_network.WLAN(mock_network.AP_IF)
        sta_wlan._connected = True
        ap_wlan.active(True)
        WifiService.hotspot_enabled = True

        disconnect_called = [False]

        def mock_disconnect(network_module=None):
            disconnect_called[0] = True

        original_disconnect = WifiService.disconnect
        WifiService.disconnect = mock_disconnect
        try:
            was_connected = WifiService.temporarily_disable(network_module=mock_network)
        finally:
            WifiService.disconnect = original_disconnect

        self.assertTrue(was_connected)
        self.assertTrue(WifiService.wifi_busy)
        self.assertEqual(
            WifiService._temp_disable_state,
            {"was_connected": True, "hotspot_was_enabled": True},
        )
        self.assertTrue(disconnect_called[0])

    def test_temporarily_enable_restores_hotspot_and_reconnects(self):
        """Test temporarily_enable restores hotspot and triggers reconnect."""
        mock_network = HotspotMockNetwork()
        WifiService._temp_disable_state = {"was_connected": True, "hotspot_was_enabled": True}
        WifiService.wifi_busy = True

        thread_calls = []

        class MockThreadModule:
            @staticmethod
            def start_new_thread(func, args):
                thread_calls.append((func, args))

        original_thread = sys.modules.get("_thread")
        sys.modules["_thread"] = MockThreadModule

        try:
            WifiService.temporarily_enable(True, network_module=mock_network)
        finally:
            if original_thread is not None:
                sys.modules["_thread"] = original_thread
            else:
                sys.modules.pop("_thread", None)

        ap_wlan = mock_network.WLAN(mock_network.AP_IF)
        self.assertFalse(WifiService.wifi_busy)
        self.assertIsNone(WifiService._temp_disable_state)
        self.assertTrue(ap_wlan.active())
        self.assertTrue(WifiService.hotspot_enabled)
        self.assertEqual(thread_calls[0][0], WifiService.auto_connect)


class TestWifiServiceIPv4Info(unittest.TestCase):
    """Test IPv4 info accessors for AP/STA modes."""

    def setUp(self):
        """Set up test fixtures."""
        WifiService.wifi_busy = False
        WifiService.hotspot_enabled = False

    def tearDown(self):
        """Clean up after test."""
        WifiService.wifi_busy = False
        WifiService.hotspot_enabled = False

    def test_get_ipv4_info_from_ap_when_hotspot_enabled(self):
        """Test IPv4 getters use AP info when hotspot is enabled."""
        mock_network = HotspotMockNetwork()
        ap_wlan = mock_network.WLAN(mock_network.AP_IF)
        ap_wlan.active(True)
        ap_wlan.ifconfig(("192.168.4.1", "255.255.255.0", "192.168.4.1", "8.8.4.4"))
        WifiService.hotspot_enabled = True

        address = WifiService.get_ipv4_address(network_module=mock_network)
        gateway = WifiService.get_ipv4_gateway(network_module=mock_network)

        self.assertEqual(address, "192.168.4.1")
        self.assertEqual(gateway, "192.168.4.1")

    def test_get_ipv4_info_returns_none_when_busy(self):
        """Test IPv4 getters return None when wifi_busy is set."""
        WifiService.wifi_busy = True

        address = WifiService.get_ipv4_address(network_module=HotspotMockNetwork())
        gateway = WifiService.get_ipv4_gateway(network_module=HotspotMockNetwork())

        self.assertIsNone(address)
        self.assertIsNone(gateway)

    def test_get_ipv4_info_desktop_mode(self):
        """Test IPv4 getters return simulated values in desktop mode."""
        address = WifiService.get_ipv4_address(network_module=None)
        gateway = WifiService.get_ipv4_gateway(network_module=None)

        self.assertEqual(address, "123.456.789.000")
        self.assertEqual(gateway, "000.123.456.789")


class TestWifiServiceDisconnect(unittest.TestCase):
    """Test WifiService.disconnect() method."""

    def test_disconnect(self):
        """Test disconnecting from WiFi."""
        mock_network = MockNetwork(connected=True)
        mock_wlan = mock_network.WLAN(mock_network.STA_IF)

        # Track calls
        disconnect_called = [False]
        active_false_called = [False]

        def mock_disconnect():
            disconnect_called[0] = True

        def mock_active(state=None):
            if state is False:
                active_false_called[0] = True
            return True if state is None else None

        mock_wlan.disconnect = mock_disconnect
        mock_wlan.active = mock_active

        WifiService.disconnect(network_module=mock_network)

        # Should have called both
        self.assertTrue(disconnect_called[0])
        self.assertTrue(active_false_called[0])

    def test_disconnect_disables_ap(self):
        """Test disconnect also disables AP and clears hotspot flag."""
        mock_network = HotspotMockNetwork()
        ap_wlan = mock_network.WLAN(mock_network.AP_IF)
        sta_wlan = mock_network.WLAN(mock_network.STA_IF)
        ap_wlan.active(True)
        sta_wlan._connected = True

        WifiService.hotspot_enabled = True

        WifiService.disconnect(network_module=mock_network)

        self.assertFalse(ap_wlan.active())
        self.assertFalse(WifiService.hotspot_enabled)

    def test_disconnect_desktop_mode(self):
        """Test disconnect in desktop mode."""
        # Should not raise an error
        WifiService.disconnect(network_module=None)


class TestWifiServiceRSSISorting(unittest.TestCase):
    """Test RSSI-based network prioritization."""

    def setUp(self):
        """Set up test fixtures."""
        MockSharedPreferences.reset_all()
        WifiService.access_points = {}
        WifiService.wifi_busy = False

    def tearDown(self):
        """Clean up after tests."""
        WifiService.access_points = {}
        WifiService.wifi_busy = False
        MockSharedPreferences.reset_all()

    def test_networks_sorted_by_rssi_strongest_first(self):
        """Test that networks are sorted by RSSI with strongest first."""
        # Create mock networks with different RSSI values
        # Format: (ssid, bssid, channel, rssi, security, hidden)
        mock_network = MockNetwork(connected=False)
        mock_wlan = mock_network.WLAN(mock_network.STA_IF)

        # Unsorted networks (weak, strong, medium)
        mock_wlan._scan_results = [
            (b'WeakNetwork', b'\xaa\xbb\xcc\xdd\xee\xff', 6, -85, 3, False),
            (b'StrongNetwork', b'\x11\x22\x33\x44\x55\x66', 1, -45, 3, False),
            (b'MediumNetwork', b'\x77\x88\x99\xaa\xbb\xcc', 11, -65, 3, False),
        ]

        # Configure all as saved networks
        WifiService.access_points = {
            'WeakNetwork': {'password': 'weak123'},
            'StrongNetwork': {'password': 'strong123'},
            'MediumNetwork': {'password': 'medium123'}
        }

        # Track connection attempts
        connection_attempts = []

        def mock_connect(ssid, password):
            connection_attempts.append(ssid)
            # Succeed on first attempt
            mock_wlan._connected = True

        mock_wlan.connect = mock_connect

        result = WifiService.connect(network_module=mock_network, time_module=MockTime())

        self.assertTrue(result)
        # Should try strongest first (-45 dBm)
        self.assertEqual(connection_attempts[0], 'StrongNetwork')
        # Should only try one (first succeeds)
        self.assertEqual(len(connection_attempts), 1)

    def test_multiple_networks_tried_in_rssi_order(self):
        """Test that multiple networks are tried in RSSI order when first fails."""
        mock_network = MockNetwork(connected=False)
        mock_wlan = mock_network.WLAN(mock_network.STA_IF)

        # Three networks with different signal strengths
        mock_wlan._scan_results = [
            (b'BadNetwork1', b'\xaa\xbb\xcc\xdd\xee\xff', 1, -40, 3, False),
            (b'BadNetwork2', b'\x11\x22\x33\x44\x55\x66', 6, -50, 3, False),
            (b'GoodNetwork', b'\x77\x88\x99\xaa\xbb\xcc', 11, -60, 3, False),
        ]

        WifiService.access_points = {
            'BadNetwork1': {'password': 'pass1'},
            'BadNetwork2': {'password': 'pass2'},
            'GoodNetwork': {'password': 'pass3'}
        }

        # Track attempts and make first two fail
        connection_attempts = []

        def mock_connect(ssid, password):
            connection_attempts.append(ssid)
            # Only succeed on third attempt
            if len(connection_attempts) >= 3:
                mock_wlan._connected = True

        mock_wlan.connect = mock_connect

        result = WifiService.connect(network_module=mock_network, time_module=MockTime())

        self.assertTrue(result)
        # Verify order: strongest to weakest
        self.assertEqual(connection_attempts[0], 'BadNetwork1')  # RSSI -40
        self.assertEqual(connection_attempts[1], 'BadNetwork2')  # RSSI -50
        self.assertEqual(connection_attempts[2], 'GoodNetwork')  # RSSI -60
        self.assertEqual(len(connection_attempts), 3)

    def test_duplicate_ssid_strongest_tried_first(self):
        """Test that with duplicate SSIDs, strongest signal is tried first."""
        mock_network = MockNetwork(connected=False)
        mock_wlan = mock_network.WLAN(mock_network.STA_IF)

        # Real-world scenario: Multiple APs with same SSID
        mock_wlan._scan_results = [
            (b'MyNetwork', b'\xaa\xbb\xcc\xdd\xee\xff', 1, -70, 3, False),
            (b'MyNetwork', b'\x11\x22\x33\x44\x55\x66', 6, -50, 3, False),  # Strongest
            (b'MyNetwork', b'\x77\x88\x99\xaa\xbb\xcc', 11, -85, 3, False),
        ]

        WifiService.access_points = {
            'MyNetwork': {'password': 'mypass123'}
        }

        connection_attempts = []

        def mock_connect(ssid, password):
            connection_attempts.append(ssid)
            # Succeed on first
            mock_wlan._connected = True

        mock_wlan.connect = mock_connect

        result = WifiService.connect(network_module=mock_network, time_module=MockTime())

        self.assertTrue(result)
        # Should only try once (first is strongest and succeeds)
        self.assertEqual(len(connection_attempts), 1)
        self.assertEqual(connection_attempts[0], 'MyNetwork')

    def test_rssi_order_with_real_scan_data(self):
        """Test with real scan data from actual ESP32 device."""
        mock_network = MockNetwork(connected=False)
        mock_wlan = mock_network.WLAN(mock_network.STA_IF)

        # Real scan output from user's example
        mock_wlan._scan_results = [
            (b'Channel 8', b'\xde\xec^\x8f\x00A', 11, -47, 3, False),
            (b'Baptistus', b'\xd8\xec^\x8f\x00A', 11, -48, 7, False),
            (b'telenet-BD74DC9', b'TgQ>t\xe7', 11, -70, 3, False),
            (b'Galaxy S10+64bf', b'b\x19\xdf\xef\xb0\x8f', 11, -83, 3, False),
            (b'Najeeb\xe2\x80\x99s iPhone', b"F\x07'\xb8\x0b0", 6, -84, 7, False),
            (b'DIRECT-83-HP OfficeJet Pro 7740', b'\x1a`$dk\x83', 1, -87, 3, False),
            (b'Channel 8', b'\xde\xec^\xe1#w', 1, -91, 3, False),
            (b'Baptistus', b'\xd8\xec^\xe1#w', 1, -91, 7, False),
            (b'Proximus-Home-596457', b'\xf4\x05\x95\xf9A\xf1', 1, -93, 3, False),
            (b'Proximus-Home-596457', b'\xcc\x00\xf1j}\x94', 1, -93, 3, False),
            (b'BASE-9104320', b'4,\xc4\xe7\x01\xb7', 1, -94, 3, False),
        ]

        # Save several networks
        WifiService.access_points = {
            'Channel 8': {'password': 'pass1'},
            'Baptistus': {'password': 'pass2'},
            'telenet-BD74DC9': {'password': 'pass3'},
            'Galaxy S10+64bf': {'password': 'pass4'},
        }

        # Track attempts and fail first to see ordering
        connection_attempts = []

        def mock_connect(ssid, password):
            connection_attempts.append(ssid)
            # Succeed on second attempt
            if len(connection_attempts) >= 2:
                mock_wlan._connected = True

        mock_wlan.connect = mock_connect

        result = WifiService.connect(network_module=mock_network, time_module=MockTime())

        self.assertTrue(result)
        # Expected order: Channel 8 (-47), Baptistus (-48), telenet (-70), Galaxy (-83)
        self.assertEqual(connection_attempts[0], 'Channel 8')
        self.assertEqual(connection_attempts[1], 'Baptistus')
        self.assertEqual(len(connection_attempts), 2)

    def test_sorting_preserves_network_data_integrity(self):
        """Test that sorting doesn't corrupt or lose network data."""
        mock_network = MockNetwork(connected=False)
        mock_wlan = mock_network.WLAN(mock_network.STA_IF)

        # Networks with various attributes
        mock_wlan._scan_results = [
            (b'Net3', b'\xaa\xaa\xaa\xaa\xaa\xaa', 11, -90, 3, False),
            (b'Net1', b'\xbb\xbb\xbb\xbb\xbb\xbb', 1, -40, 7, True),  # Hidden
            (b'Net2', b'\xcc\xcc\xcc\xcc\xcc\xcc', 6, -60, 2, False),
        ]

        WifiService.access_points = {
            'Net1': {'password': 'p1'},
            'Net2': {'password': 'p2'},
            'Net3': {'password': 'p3'}
        }

        # Track attempts to verify all are tried
        connection_attempts = []

        def mock_connect(ssid, password):
            connection_attempts.append(ssid)
            # Never succeed, try all
            pass

        mock_wlan.connect = mock_connect

        result = WifiService.connect(network_module=mock_network, time_module=MockTime())

        self.assertFalse(result)  # No connection succeeded
        # Verify all 3 were attempted in RSSI order
        self.assertEqual(len(connection_attempts), 3)
        self.assertEqual(connection_attempts[0], 'Net1')  # RSSI -40
        self.assertEqual(connection_attempts[1], 'Net2')  # RSSI -60
        self.assertEqual(connection_attempts[2], 'Net3')  # RSSI -90

    def test_no_saved_networks_in_scan(self):
        """Test behavior when scan finds no saved networks."""
        mock_network = MockNetwork(connected=False)
        mock_wlan = mock_network.WLAN(mock_network.STA_IF)

        mock_wlan._scan_results = [
            (b'UnknownNet1', b'\xaa\xbb\xcc\xdd\xee\xff', 1, -50, 3, False),
            (b'UnknownNet2', b'\x11\x22\x33\x44\x55\x66', 6, -60, 3, False),
        ]

        WifiService.access_points = {
            'SavedNetwork': {'password': 'pass123'}
        }

        connection_attempts = []

        def mock_connect(ssid, password):
            connection_attempts.append(ssid)

        mock_wlan.connect = mock_connect

        result = WifiService.connect(network_module=mock_network, time_module=MockTime())

        self.assertFalse(result)
        # No attempts should be made
        self.assertEqual(len(connection_attempts), 0)

    def test_rssi_logging_shows_signal_strength(self):
        """Test that RSSI value is logged during scan (for debugging)."""
        # This is more of a documentation test to verify the log format
        mock_network = MockNetwork(connected=False)
        mock_wlan = mock_network.WLAN(mock_network.STA_IF)

        mock_wlan._scan_results = [
            (b'TestNet', b'\xaa\xbb\xcc\xdd\xee\xff', 1, -55, 3, False),
        ]

        WifiService.access_points = {
            'TestNet': {'password': 'pass'}
        }

        # The connect method now logs "Found network 'TestNet' (RSSI: -55 dBm)"
        # This test just verifies it doesn't crash
        result = WifiService.connect(network_module=mock_network, time_module=MockTime())
        # Since mock doesn't actually connect, this will likely be False
        # but the important part is the code runs without error


