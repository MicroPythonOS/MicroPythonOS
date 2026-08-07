"""
Graphical test for the ScanBluetooth app.

This test verifies that the ScanBluetooth app can start and render its
simulation-mode UI on platforms without a real bluetooth module.

Usage:
"""

import unittest
from mpos import AppManager, wait_for_text
from mpos.testing.mocks import MockBluetooth


class TestGraphicalScanBluetooth(unittest.TestCase):
    """Test suite for ScanBluetooth app."""

    def test_starts_in_simulation_mode(self):
        """Test that the app starts and shows simulation mode status."""
        from mpos import BLEManager
        BLEManager.deactivate()
        result = AppManager.start_app("com.micropythonos.scan_bluetooth")
        self.assertTrue(result, "Failed to start ScanBluetooth app")
        self.assertTrue(
            wait_for_text("Simulation mode", timeout=10),
            "Simulation mode text did not appear",
        )


class TestMockBluetooth(unittest.TestCase):
    """Test suite for the BLE mock."""

    def test_mock_triggers_scan_results(self):
        """Test that MockBluetooth fires scan-result and scan-done events."""
        received = []
        ble = MockBluetooth().BLE()
        ble.irq(lambda event, data: received.append((event, data)))
        ble.active(True)
        ble.gap_scan(5000)

        self.assertTrue(len(received) > 0, "No IRQ events received")
        events = [event for event, _ in received]
        self.assertTrue(ble.IRQ_SCAN_DONE in events)

    def test_z_blemanager_scan_returns_results(self):
        """Test that BLEManager scan pipeline works on desktop."""
        from mpos import BLEManager

        BLEManager.clear_scan_results()
        BLEManager.clear_scan_filters()
        BLEManager.activate()
        BLEManager.register_irq(lambda e, d: None)
        BLEManager.start_scan(duration_ms=0)

        results = BLEManager.get_scan_results()
        self.assertTrue(len(results) > 0, "No scan results from BLEManager")
        self.assertIsInstance(results[0].parsed_ad, dict)

        BLEManager.stop_scan()
        BLEManager.deactivate()
        BLEManager.clear_scan_results()
        BLEManager.clear_scan_filters()


