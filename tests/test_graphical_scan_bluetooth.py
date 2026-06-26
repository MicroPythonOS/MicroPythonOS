"""
Graphical test for the ScanBluetooth app.

This test verifies that the ScanBluetooth app can start and render its
simulation-mode UI on platforms without a real bluetooth module.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_scan_bluetooth.py
    Device:  ./tests/unittest.sh tests/test_graphical_scan_bluetooth.py --ondevice
"""

import unittest
from mpos import AppManager, wait_for_text
from mpos.testing.mocks import MockBluetooth


class TestGraphicalScanBluetooth(unittest.TestCase):
    """Test suite for ScanBluetooth app."""

    def test_starts_in_simulation_mode(self):
        """Test that the app starts and shows simulation mode status."""
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


