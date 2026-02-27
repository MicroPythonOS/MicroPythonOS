import unittest
import sys

# Add tests directory to path for network_test_helper
sys.path.insert(0, '../tests')

# Import network test helpers
from network_test_helper import MockNetwork, MockTime

# Mock config classes
class MockSharedPreferences:
    """Mock SharedPreferences for testing."""
    _all_data = {}  # Class-level storage

    def __init__(self, app_id):
        self.app_id = app_id
        if app_id not in MockSharedPreferences._all_data:
            MockSharedPreferences._all_data[app_id] = {}

    def get_dict(self, key):
        return MockSharedPreferences._all_data.get(self.app_id, {}).get(key, {})

    def edit(self):
        return MockEditor(self)

    @classmethod
    def reset_all(cls):
        cls._all_data = {}


class MockEditor:
    """Mock editor for SharedPreferences."""

    def __init__(self, prefs):
        self.prefs = prefs
        self.pending = {}

    def put_dict(self, key, value):
        self.pending[key] = value

    def commit(self):
        if self.prefs.app_id not in MockSharedPreferences._all_data:
            MockSharedPreferences._all_data[self.prefs.app_id] = {}
        MockSharedPreferences._all_data[self.prefs.app_id].update(self.pending)


# Create mock mpos module
class MockMpos:
    """Mock mpos module with config and time."""

    class config:
        @staticmethod
        def SharedPreferences(app_id):
            return MockSharedPreferences(app_id)

    class time:
        @staticmethod
        def sync_time():
            pass  # No-op for testing


# Inject mocks before importing WifiService
sys.modules['mpos'] = MockMpos
sys.modules['mpos.config'] = MockMpos.config
sys.modules['mpos.time'] = MockMpos.time

# Add path to wifi_service.py
sys.path.append('lib/mpos/net')

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
        mock_network = MockNetwork(connected=False)

        result = WifiService.is_connected(network_module=mock_network)

        self.assertFalse(result)

    def test_is_connected_when_wifi_busy(self):
        """Test is_connected returns False when WiFi is busy."""
        mock_network = MockNetwork(connected=True)
        WifiService.wifi_busy = True

        result = WifiService.is_connected(network_module=mock_network)

        # Should return False even though connected
        self.assertFalse(result)

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


