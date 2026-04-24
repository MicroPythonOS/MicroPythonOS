"""Tests for ConnectivityManager WiFi auto-reconnection.

Tests the reconnection logic added to handle the scenario where WiFi
is unavailable at boot (e.g. router off overnight) and comes back later.
"""
import unittest
import sys

# Add parent directory to path for shared mocks
sys.path.insert(0, "../tests")

from mpos.testing.mocks import make_machine_timer_module, make_usocket_module
from network_test_helper import MockNetwork, MockTimer, MockTime, MockRequests, MockSocket

# Inject machine/socket mocks
sys.modules["machine"] = make_machine_timer_module(MockTimer)
sys.modules["usocket"] = make_usocket_module(MockSocket)
sys.modules['requests'] = MockRequests()

# Mock _thread to run spawned threads synchronously
_thread_calls = []

class MockThreadModule:
    @staticmethod
    def start_new_thread(fn, args):
        _thread_calls.append((fn, args))
        fn()  # reconnect_thread takes no args

    @staticmethod
    def stack_size(s=0):
        return 0

sys.modules['_thread'] = MockThreadModule

# Mock WifiService
_auto_connect_calls = []

class MockWifiService:
    wifi_busy = False

    @staticmethod
    def auto_connect(network_module=None, time_module=None):
        _auto_connect_calls.append(True)

sys.modules['mpos.net.wifi_service'] = type('module', (), {'WifiService': MockWifiService})()


def fresh_cm_import(mock_network):
    """Helper: inject mock network and get a fresh ConnectivityManager class."""
    sys.modules['network'] = mock_network
    mod_key = 'mpos.net.connectivity_manager'
    if mod_key in sys.modules:
        del sys.modules[mod_key]
    from mpos.net.connectivity_manager import ConnectivityManager
    # Force HAS_NETWORK_MODULE in case the re-import didn't pick up the new mock
    import mpos.net.connectivity_manager as cm_mod
    cm_mod.HAS_NETWORK_MODULE = True
    ConnectivityManager._instance = None
    return ConnectivityManager


class TestReconnectOfflineCounter(unittest.TestCase):
    """Test that offline checks are counted correctly."""

    def setUp(self):
        self.mock_network = MockNetwork(connected=False)
        MockTimer.reset_all()
        _auto_connect_calls.clear()
        _thread_calls.clear()
        MockWifiService.wifi_busy = False
        self.ConnectivityManager = fresh_cm_import(self.mock_network)

    def tearDown(self):
        self.ConnectivityManager._instance = None
        MockTimer.reset_all()

    def test_offline_counter_increments(self):
        """Test that offline checks increment the counter."""
        cm = self.ConnectivityManager()
        timer = MockTimer.get_timer(1)

        for i in range(5):
            timer.callback(timer)

        # Init check + 5 timer checks = 6 offline checks
        self.assertTrue(cm._offline_checks > 0)

    def test_offline_counter_resets_on_connect(self):
        """Test that counter resets when WiFi reconnects."""
        cm = self.ConnectivityManager()
        timer = MockTimer.get_timer(1)

        for i in range(5):
            timer.callback(timer)
        self.assertTrue(cm._offline_checks > 0)

        # WiFi comes back
        self.mock_network.set_connected(True)
        timer.callback(timer)

        self.assertEqual(cm._offline_checks, 0)

    def test_no_counter_when_online(self):
        """Test that counter stays at 0 while online."""
        self.mock_network.set_connected(True)
        cm = self.ConnectivityManager()
        timer = MockTimer.get_timer(1)

        for i in range(10):
            timer.callback(timer)

        self.assertEqual(cm._offline_checks, 0)


class TestReconnectTrigger(unittest.TestCase):
    """Test that reconnection is triggered at the right time."""

    def setUp(self):
        self.mock_network = MockNetwork(connected=False)
        MockTimer.reset_all()
        _auto_connect_calls.clear()
        _thread_calls.clear()
        MockWifiService.wifi_busy = False
        self.ConnectivityManager = fresh_cm_import(self.mock_network)

    def tearDown(self):
        self.ConnectivityManager._instance = None
        MockTimer.reset_all()

    def test_reconnect_triggers_at_interval(self):
        """Test that auto_connect is called after RECONNECT_INTERVAL offline checks."""
        cm = self.ConnectivityManager()
        timer = MockTimer.get_timer(1)
        _auto_connect_calls.clear()

        # Init already did 1 offline check, so we need RECONNECT_INTERVAL - 1 more
        for i in range(cm._RECONNECT_INTERVAL - 1):
            timer.callback(timer)

        self.assertEqual(len(_auto_connect_calls), 1)

    def test_reconnect_triggers_periodically(self):
        """Test that reconnection repeats at each interval."""
        cm = self.ConnectivityManager()
        timer = MockTimer.get_timer(1)
        _auto_connect_calls.clear()

        # Run through two full intervals (minus the init check)
        for i in range(cm._RECONNECT_INTERVAL * 2 - 1):
            timer.callback(timer)

        self.assertEqual(len(_auto_connect_calls), 2)

    def test_no_reconnect_when_online(self):
        """Test that reconnection is not attempted while online."""
        self.mock_network.set_connected(True)
        self.ConnectivityManager._instance = None
        cm = self.ConnectivityManager()
        timer = MockTimer.get_timer(1)
        _auto_connect_calls.clear()

        for i in range(cm._RECONNECT_INTERVAL * 3):
            timer.callback(timer)

        self.assertEqual(len(_auto_connect_calls), 0)

    def test_no_reconnect_when_wifi_busy(self):
        """Test that reconnection is skipped when WiFi is busy."""
        cm = self.ConnectivityManager()
        timer = MockTimer.get_timer(1)
        _auto_connect_calls.clear()

        MockWifiService.wifi_busy = True

        for i in range(cm._RECONNECT_INTERVAL * 2):
            timer.callback(timer)

        self.assertEqual(len(_auto_connect_calls), 0)

    def test_no_overlapping_reconnects(self):
        """Test that a reconnect is not started if one is already in progress."""
        cm = self.ConnectivityManager()
        timer = MockTimer.get_timer(1)
        _auto_connect_calls.clear()

        cm._reconnect_in_progress = True

        for i in range(cm._RECONNECT_INTERVAL * 2):
            timer.callback(timer)

        self.assertEqual(len(_auto_connect_calls), 0)

    def test_reconnect_clears_in_progress_flag(self):
        """Test that _reconnect_in_progress is cleared after reconnect."""
        cm = self.ConnectivityManager()
        timer = MockTimer.get_timer(1)

        for i in range(cm._RECONNECT_INTERVAL - 1):
            timer.callback(timer)

        # Mock runs synchronously, so flag should be cleared
        self.assertFalse(cm._reconnect_in_progress)


class TestReconnectDesktopMode(unittest.TestCase):
    """Test that reconnection is not attempted on desktop."""

    def setUp(self):
        if 'network' in sys.modules:
            del sys.modules['network']
        if 'mpos.net.connectivity_manager' in sys.modules:
            del sys.modules['mpos.net.connectivity_manager']

        from mpos.net.connectivity_manager import ConnectivityManager
        self.ConnectivityManager = ConnectivityManager
        ConnectivityManager._instance = None
        MockTimer.reset_all()
        _auto_connect_calls.clear()

    def tearDown(self):
        self.ConnectivityManager._instance = None
        MockTimer.reset_all()

    def test_no_reconnect_on_desktop(self):
        """Test that desktop mode never triggers reconnect."""
        cm = self.ConnectivityManager()
        timer = MockTimer.get_timer(1)
        _auto_connect_calls.clear()

        for i in range(100):
            timer.callback(timer)

        self.assertEqual(len(_auto_connect_calls), 0)


class TestReconnectRouterScenario(unittest.TestCase):
    """Integration test: router off overnight, back on in the morning."""

    def setUp(self):
        self.mock_network = MockNetwork(connected=False)
        MockTimer.reset_all()
        _auto_connect_calls.clear()
        _thread_calls.clear()
        MockWifiService.wifi_busy = False
        self.ConnectivityManager = fresh_cm_import(self.mock_network)

    def tearDown(self):
        self.ConnectivityManager._instance = None
        MockTimer.reset_all()

    def test_router_off_at_boot_then_on(self):
        """Simulate: device boots with router off, router comes on later."""
        cm = self.ConnectivityManager()
        timer = MockTimer.get_timer(1)
        _auto_connect_calls.clear()

        notifications = []
        cm.register_callback(lambda online: notifications.append(online))

        self.assertFalse(cm.is_online())

        # Run checks until reconnect triggers (init already did 1)
        for i in range(cm._RECONNECT_INTERVAL - 1):
            timer.callback(timer)

        self.assertEqual(len(_auto_connect_calls), 1)

        # Router comes back — WiFi reconnects
        self.mock_network.set_connected(True)
        timer.callback(timer)

        self.assertTrue(cm.is_online())
        self.assertTrue(True in notifications)
        self.assertEqual(cm._offline_checks, 0)
