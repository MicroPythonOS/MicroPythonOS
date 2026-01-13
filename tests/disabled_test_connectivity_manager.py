import unittest
import sys

# Add parent directory to path so we can import network_test_helper
# When running from unittest.sh, we're in internal_filesystem/, so tests/ is ../tests/
sys.path.insert(0, '../tests')

# Import our network test helpers
from network_test_helper import MockNetwork, MockTimer, MockTime, MockRequests, MockSocket

# Mock machine module with Timer
class MockMachine:
    """Mock machine module."""
    Timer = MockTimer

# Mock usocket module
class MockUsocket:
    """Mock usocket module."""
    AF_INET = MockSocket.AF_INET
    SOCK_STREAM = MockSocket.SOCK_STREAM

    @staticmethod
    def socket(af, sock_type):
        return MockSocket(af, sock_type)

# Inject mocks into sys.modules BEFORE importing connectivity_manager
sys.modules['machine'] = MockMachine
sys.modules['usocket'] = MockUsocket

# Mock requests module
mock_requests = MockRequests()
sys.modules['requests'] = mock_requests


class TestConnectivityManagerWithNetwork(unittest.TestCase):
    """Test ConnectivityManager with network module available."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a mock network module
        self.mock_network = MockNetwork(connected=True)

        # Mock the network module globally BEFORE importing
        sys.modules['network'] = self.mock_network

        # Now import after network is mocked
        # Need to reload the module to pick up the new network module
        if 'mpos.net.connectivity_manager' in sys.modules:
            del sys.modules['mpos.net.connectivity_manager'] # Maybe this doesn't suffic now that it's imported through mpos

        # Import fresh
        from mpos import ConnectivityManager
        self.ConnectivityManager = ConnectivityManager

        # Reset the singleton instance
        ConnectivityManager._instance = None

        # Reset all mock timers
        MockTimer.reset_all()

    def tearDown(self):
        """Clean up after test."""
        # Reset singleton
        if hasattr(self, 'ConnectivityManager'):
            self.ConnectivityManager._instance = None

        # Clean up mocks
        if 'network' in sys.modules:
            del sys.modules['network']
        if 'mpos.net.connectivity_manager' in sys.modules:
            del sys.modules['mpos.net.connectivity_manager']
        MockTimer.reset_all()

    def test_singleton_pattern(self):
        """Test that ConnectivityManager is a singleton via get()."""
        # Using get() should return the same instance
        cm1 = self.ConnectivityManager.get()
        cm2 = self.ConnectivityManager.get()
        cm3 = self.ConnectivityManager.get()

        # All should be the same instance
        self.assertEqual(id(cm1), id(cm2))
        self.assertEqual(id(cm2), id(cm3))

    def test_initialization_with_network_module(self):
        """Test initialization when network module is available."""
        cm = self.ConnectivityManager()

        # Should have network checking capability
        self.assertTrue(cm.can_check_network, "a")

        # Should have created WLAN instance
        self.assertIsNotNone(cm.wlan, "b")

        # Should have created timer
        timer = MockTimer.get_timer(1)
        self.assertIsNotNone(timer)
        self.assertTrue(timer.active, "c")
        self.assertEqual(timer.period, 8000)
        self.assertEqual(timer.mode, MockTimer.PERIODIC)

    def test_initial_connection_state_when_connected(self):
        """Test initial state when network is connected."""
        self.mock_network.set_connected(True)
        cm = self.ConnectivityManager()

        # Should detect connection during initialization
        self.assertTrue(cm.is_online())

    def test_initial_connection_state_when_disconnected(self):
        """Test initial state when network is disconnected."""
        self.mock_network.set_connected(False)
        cm = self.ConnectivityManager()

        # Should detect disconnection during initialization
        self.assertFalse(cm.is_online())

    def test_callback_registration(self):
        """Test registering callbacks."""
        cm = self.ConnectivityManager()

        callback_called = []
        def my_callback(online):
            callback_called.append(online)

        cm.register_callback(my_callback)

        # Callback should be in the list
        self.assertTrue(my_callback in cm.callbacks)

        # Registering again should not duplicate
        cm.register_callback(my_callback)
        self.assertEqual(cm.callbacks.count(my_callback), 1)

    def test_callback_unregistration(self):
        """Test unregistering callbacks."""
        cm = self.ConnectivityManager()

        def callback1(online):
            pass

        def callback2(online):
            pass

        cm.register_callback(callback1)
        cm.register_callback(callback2)

        # Both should be registered
        self.assertTrue(callback1 in cm.callbacks)
        self.assertTrue(callback2 in cm.callbacks)

        # Unregister callback1
        cm.unregister_callback(callback1)

        # Only callback2 should remain
        self.assertFalse(callback1 in cm.callbacks)
        self.assertTrue(callback2 in cm.callbacks)

    def test_callback_notification_on_state_change(self):
        """Test that callbacks are notified when state changes."""
        self.mock_network.set_connected(True)
        cm = self.ConnectivityManager()

        notifications = []
        def my_callback(online):
            notifications.append(online)

        cm.register_callback(my_callback)

        # Simulate going offline
        self.mock_network.set_connected(False)

        # Trigger periodic check (timer passes itself as first arg)
        timer = MockTimer.get_timer(1)
        timer.callback(timer)

        # Should have been notified of offline state
        self.assertEqual(len(notifications), 1)
        self.assertFalse(notifications[0])

        # Simulate going back online
        self.mock_network.set_connected(True)
        timer.callback(timer)

        # Should have been notified of online state
        self.assertEqual(len(notifications), 2)
        self.assertTrue(notifications[1])

    def test_callback_notification_not_sent_when_state_unchanged(self):
        """Test that callbacks are not notified when state doesn't change."""
        self.mock_network.set_connected(True)
        cm = self.ConnectivityManager()

        notifications = []
        def my_callback(online):
            notifications.append(online)

        cm.register_callback(my_callback)

        # Trigger periodic check while still connected
        timer = MockTimer.get_timer(1)
        timer.callback(timer)

        # Should not have been notified (state didn't change)
        self.assertEqual(len(notifications), 0)

    def test_periodic_check_detects_connection_change(self):
        """Test that periodic check detects connection state changes."""
        self.mock_network.set_connected(True)
        cm = self.ConnectivityManager()

        # Should be online initially
        self.assertTrue(cm.is_online())

        # Simulate disconnection
        self.mock_network.set_connected(False)

        # Trigger periodic check
        timer = MockTimer.get_timer(1)
        timer.callback(timer)

        # Should now be offline
        self.assertFalse(cm.is_online())

        # Reconnect
        self.mock_network.set_connected(True)
        timer.callback(timer)

        # Should be online again
        self.assertTrue(cm.is_online())

    def test_callback_exception_handling(self):
        """Test that exceptions in callbacks don't break the manager."""
        cm = self.ConnectivityManager()

        notifications = []

        def bad_callback(online):
            raise Exception("Callback error!")

        def good_callback(online):
            notifications.append(online)

        cm.register_callback(bad_callback)
        cm.register_callback(good_callback)

        # Trigger state change
        self.mock_network.set_connected(False)
        timer = MockTimer.get_timer(1)
        timer.callback(timer)

        # Good callback should still have been called despite bad callback
        self.assertEqual(len(notifications), 1)
        self.assertFalse(notifications[0])

    def test_multiple_callbacks(self):
        """Test multiple callbacks are all notified."""
        cm = self.ConnectivityManager()

        notifications1 = []
        notifications2 = []
        notifications3 = []

        cm.register_callback(lambda online: notifications1.append(online))
        cm.register_callback(lambda online: notifications2.append(online))
        cm.register_callback(lambda online: notifications3.append(online))

        # Trigger state change
        self.mock_network.set_connected(False)
        timer = MockTimer.get_timer(1)
        timer.callback(timer)

        # All callbacks should have been notified
        self.assertEqual(len(notifications1), 1)
        self.assertEqual(len(notifications2), 1)
        self.assertEqual(len(notifications3), 1)

        self.assertFalse(notifications1[0])
        self.assertFalse(notifications2[0])
        self.assertFalse(notifications3[0])

    def test_is_wifi_connected(self):
        """Test is_wifi_connected() method."""
        cm = self.ConnectivityManager()

        # is_connected is set to False during init for platforms with network module
        # It's only set to True for platforms without network module (desktop)
        self.assertFalse(cm.is_wifi_connected())


class TestConnectivityManagerWithoutNetwork(unittest.TestCase):
    """Test ConnectivityManager without network module (desktop mode)."""

    def setUp(self):
        """Set up test fixtures."""
        # Remove network module to simulate desktop environment
        if 'network' in sys.modules:
            del sys.modules['network']

        # Reload the module without network
        if 'mpos.net.connectivity_manager' in sys.modules:
            del sys.modules['mpos.net.connectivity_manager']

        from mpos import ConnectivityManager
        self.ConnectivityManager = ConnectivityManager

        # Reset the singleton instance
        ConnectivityManager._instance = None

        # Reset timers
        MockTimer.reset_all()

    def tearDown(self):
        """Clean up after test."""
        if hasattr(self, 'ConnectivityManager'):
            self.ConnectivityManager._instance = None
        if 'mpos.net.connectivity_manager' in sys.modules:
            del sys.modules['mpos.net.connectivity_manager']
        MockTimer.reset_all()

    def test_initialization_without_network_module(self):
        """Test initialization when network module is not available."""
        cm = self.ConnectivityManager()

        # Should NOT have network checking capability
        self.assertFalse(cm.can_check_network)

        # Should not have WLAN instance
        self.assertIsNone(cm.wlan)

        # Should still create timer
        timer = MockTimer.get_timer(1)
        self.assertIsNotNone(timer)

    def test_always_online_without_network_module(self):
        """Test that manager assumes always online without network module."""
        cm = self.ConnectivityManager()

        # Should assume connected
        self.assertTrue(cm.is_connected)

        # Should assume online
        self.assertTrue(cm.is_online())

    def test_periodic_check_without_network_module(self):
        """Test periodic check when there's no network module."""
        cm = self.ConnectivityManager()

        # Trigger periodic check
        timer = MockTimer.get_timer(1)
        timer.callback(timer)

        # Should still be online
        self.assertTrue(cm.is_online())

    def test_callbacks_not_triggered_without_network(self):
        """Test that callbacks aren't triggered when always online."""
        cm = self.ConnectivityManager()

        notifications = []
        cm.register_callback(lambda online: notifications.append(online))

        # Trigger periodic checks
        timer = MockTimer.get_timer(1)
        for _ in range(5):
            timer.callback(timer)

        # No notifications should have been sent (state never changed)
        self.assertEqual(len(notifications), 0)


class TestConnectivityManagerWaitUntilOnline(unittest.TestCase):
    """Test wait_until_online functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock network
        self.mock_network = MockNetwork(connected=False)
        sys.modules['network'] = self.mock_network

        # Reload module
        if 'mpos.net.connectivity_manager' in sys.modules:
            del sys.modules['mpos.net.connectivity_manager']

        from mpos import ConnectivityManager
        self.ConnectivityManager = ConnectivityManager

        ConnectivityManager._instance = None
        MockTimer.reset_all()

    def tearDown(self):
        """Clean up after test."""
        if hasattr(self, 'ConnectivityManager'):
            self.ConnectivityManager._instance = None
        MockTimer.reset_all()
        if 'network' in sys.modules:
            del sys.modules['network']
        if 'mpos.net.connectivity_manager' in sys.modules:
            del sys.modules['mpos.net.connectivity_manager']

    def test_wait_until_online_already_online(self):
        """Test wait_until_online when already online."""
        self.mock_network.set_connected(True)
        cm = self.ConnectivityManager()

        # Should return immediately
        result = cm.wait_until_online(timeout=5)
        self.assertTrue(result)

    def test_wait_until_online_without_network_module(self):
        """Test wait_until_online without network module (desktop)."""
        # Remove network module
        if 'network' in sys.modules:
            del sys.modules['network']

        # Reload module
        if 'mpos.net.connectivity_manager' in sys.modules:
            del sys.modules['mpos.net.connectivity_manager']

        from mpos import ConnectivityManager
        self.ConnectivityManager = ConnectivityManager
        ConnectivityManager._instance = None

        cm = self.ConnectivityManager()

        # Should return True immediately (always online)
        result = cm.wait_until_online(timeout=5)
        self.assertTrue(result)


class TestConnectivityManagerEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_network = MockNetwork(connected=True)
        sys.modules['network'] = self.mock_network

        if 'mpos.net.connectivity_manager' in sys.modules:
            del sys.modules['mpos.net.connectivity_manager']

        from mpos import ConnectivityManager
        self.ConnectivityManager = ConnectivityManager

        ConnectivityManager._instance = None
        MockTimer.reset_all()

    def tearDown(self):
        """Clean up after test."""
        if hasattr(self, 'ConnectivityManager'):
            self.ConnectivityManager._instance = None
        MockTimer.reset_all()
        if 'network' in sys.modules:
            del sys.modules['network']
        if 'mpos.net.connectivity_manager' in sys.modules:
            del sys.modules['mpos.net.connectivity_manager']

    def test_initialization_creates_timer(self):
        """Test that initialization creates periodic timer."""
        cm = self.ConnectivityManager()

        # Timer should exist
        timer = MockTimer.get_timer(1)
        self.assertIsNotNone(timer)

        # Timer should be configured correctly
        self.assertEqual(timer.period, 8000)  # 8 seconds
        self.assertEqual(timer.mode, MockTimer.PERIODIC)
        self.assertTrue(timer.active)

    def test_get_creates_instance_if_not_exists(self):
        """Test that get() creates instance if it doesn't exist."""
        # Ensure no instance exists
        self.assertIsNone(self.ConnectivityManager._instance)

        # get() should create one
        cm = self.ConnectivityManager.get()
        self.assertIsNotNone(cm)

        # Subsequent get() should return same instance
        cm2 = self.ConnectivityManager.get()
        self.assertEqual(id(cm), id(cm2))

    def test_periodic_check_does_not_notify_on_init(self):
        """Test periodic check doesn't notify during initialization."""
        self.mock_network.set_connected(False)

        # Register callback AFTER creating instance to observe later notifications
        cm = self.ConnectivityManager()

        notifications = []
        cm.register_callback(lambda online: notifications.append(online))

        # No notifications yet (initial check had notify=False)
        self.assertEqual(len(notifications), 0)

    def test_unregister_nonexistent_callback(self):
        """Test unregistering a callback that was never registered."""
        cm = self.ConnectivityManager()

        def my_callback(online):
            pass

        # Should not raise an exception
        cm.unregister_callback(my_callback)

        # Callbacks should be empty
        self.assertEqual(len(cm.callbacks), 0)

    def test_online_offline_online_transitions(self):
        """Test multiple state transitions."""
        self.mock_network.set_connected(True)
        cm = self.ConnectivityManager()

        notifications = []
        cm.register_callback(lambda online: notifications.append(online))

        timer = MockTimer.get_timer(1)

        # Go offline
        self.mock_network.set_connected(False)
        timer.callback(timer)
        self.assertFalse(cm.is_online())
        self.assertEqual(notifications[-1], False)

        # Go online
        self.mock_network.set_connected(True)
        timer.callback(timer)
        self.assertTrue(cm.is_online())
        self.assertEqual(notifications[-1], True)

        # Go offline again
        self.mock_network.set_connected(False)
        timer.callback(timer)
        self.assertFalse(cm.is_online())
        self.assertEqual(notifications[-1], False)

        # Should have 3 notifications
        self.assertEqual(len(notifications), 3)


class TestConnectivityManagerIntegration(unittest.TestCase):
    """Integration tests for ConnectivityManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_network = MockNetwork(connected=True)
        sys.modules['network'] = self.mock_network

        if 'mpos.net.connectivity_manager' in sys.modules:
            del sys.modules['mpos.net.connectivity_manager']

        from mpos import ConnectivityManager
        self.ConnectivityManager = ConnectivityManager

        ConnectivityManager._instance = None
        MockTimer.reset_all()

    def tearDown(self):
        """Clean up after test."""
        if hasattr(self, 'ConnectivityManager'):
            self.ConnectivityManager._instance = None
        MockTimer.reset_all()
        if 'network' in sys.modules:
            del sys.modules['network']
        if 'mpos.net.connectivity_manager' in sys.modules:
            del sys.modules['mpos.net.connectivity_manager']

    def test_realistic_usage_scenario(self):
        """Test a realistic usage scenario."""
        # App starts, creates connectivity manager
        cm = self.ConnectivityManager.get()

        # App registers callback to update UI
        ui_state = {'online': True}
        def update_ui(online):
            ui_state['online'] = online

        cm.register_callback(update_ui)

        # Initially online
        self.assertTrue(cm.is_online())
        self.assertTrue(ui_state['online'])

        # User moves out of WiFi range
        self.mock_network.set_connected(False)
        timer = MockTimer.get_timer(1)
        timer.callback(timer)

        # UI should reflect offline state
        self.assertFalse(cm.is_online())
        self.assertFalse(ui_state['online'])

        # User returns to WiFi range
        self.mock_network.set_connected(True)
        timer.callback(timer)

        # UI should reflect online state
        self.assertTrue(cm.is_online())
        self.assertTrue(ui_state['online'])

        # App closes, unregisters callback
        cm.unregister_callback(update_ui)

        # Callback should be removed
        self.assertFalse(update_ui in cm.callbacks)

    def test_multiple_apps_using_connectivity_manager(self):
        """Test multiple apps/components using the same manager."""
        cm = self.ConnectivityManager.get()

        # Three different apps register callbacks
        app1_state = []
        app2_state = []
        app3_state = []

        cm.register_callback(lambda online: app1_state.append(online))
        cm.register_callback(lambda online: app2_state.append(online))
        cm.register_callback(lambda online: app3_state.append(online))

        # Network goes offline
        self.mock_network.set_connected(False)
        timer = MockTimer.get_timer(1)
        timer.callback(timer)

        # All apps should be notified
        self.assertEqual(len(app1_state), 1)
        self.assertEqual(len(app2_state), 1)
        self.assertEqual(len(app3_state), 1)

        # All should see offline state
        self.assertFalse(app1_state[0])
        self.assertFalse(app2_state[0])
        self.assertFalse(app3_state[0])


