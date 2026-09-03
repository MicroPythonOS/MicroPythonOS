"""
Unit tests for BLEManager (desktop, using MockBLE).
"""

import unittest
from mpos import BLEManager
from mpos.testing.mocks import MockBluetooth


class TestBLEManagerActivation(unittest.TestCase):

    def setUp(self):
        BLEManager.deactivate()
        BLEManager.clear_scan_results()
        BLEManager.clear_scan_filters()

    def test_get_ble(self):
        ble = BLEManager.get_ble()
        self.assertIsNotNone(ble)

    def test_is_simulation(self):
        self.assertTrue(BLEManager.is_simulation())

    def test_is_available(self):
        self.assertTrue(BLEManager.is_available())

    def test_activate_deactivate(self):
        BLEManager.activate()
        self.assertTrue(BLEManager.is_active())
        BLEManager.deactivate()
        self.assertFalse(BLEManager.is_active())


class TestADUtilities(unittest.TestCase):

    def test_ad_field(self):
        field = BLEManager.ad_field(0x09, b"Hello")
        self.assertEqual(field[0], 6)  # length: 5 data + 1 type
        self.assertEqual(field[1], 0x09)  # type
        self.assertEqual(field[2:], b"Hello")

    def test_ad_parse_empty(self):
        self.assertEqual(BLEManager.ad_parse(b""), {})

    def test_ad_parse_name(self):
        adv = bytearray([5, 0x09, ord("T"), ord("e"), ord("s"), ord("t")])
        parsed = BLEManager.ad_parse(bytes(adv))
        self.assertIn(0x09, parsed)
        self.assertEqual(parsed[0x09], b"Test")

    def test_ad_parse_multiple_fields(self):
        adv = bytearray(
            [5, 0x09, ord("T"), ord("e"), ord("s"), ord("t")]
            + [3, 0x03, 0x34, 0x12]
        )
        parsed = BLEManager.ad_parse(bytes(adv))
        self.assertIn(0x09, parsed)
        self.assertIn(0x03, parsed)
        self.assertEqual(parsed[0x09], b"Test")

    def test_ad_build(self):
        fields = [(0x09, b"Hi"), (0x03, b"\x34\x12")]
        result = BLEManager.ad_build(fields)
        parsed = BLEManager.ad_parse(result)
        self.assertEqual(parsed[0x09], b"Hi")
        self.assertIn(0x03, parsed)

    def test_ad_build_31_byte_limit(self):
        fields = [(0x09, b"A" * 30)]
        result = BLEManager.ad_build(fields)
        self.assertLessEqual(len(result), 31)

    def test_ad_name(self):
        field = BLEManager.ad_name("Test", short=False)
        self.assertEqual(field[1], 0x09)
        self.assertIn(b"Test", field)


class TestMACUtilities(unittest.TestCase):

    def test_mac_str(self):
        addr = b"\xaa\xbb\xcc\xdd\xee\xff"
        self.assertEqual(BLEManager.mac_str(addr), "aa:bb:cc:dd:ee:ff")

    def test_mac_bytes_roundtrip(self):
        addr_str = "aa:bb:cc:dd:ee:ff"
        addr = BLEManager.mac_bytes(addr_str)
        self.assertEqual(BLEManager.mac_str(addr), addr_str)


class TestScan(unittest.TestCase):

    def _clean(self):
        BLEManager.clear_scan_filters()
        BLEManager.clear_scan_results()
        BLEManager.deactivate()

    def test_scan_produces_results(self):
        self._clean()
        BLEManager.activate()
        BLEManager.register_irq(lambda e, d: None)
        self.assertTrue(BLEManager.is_active())

        BLEManager.start_scan(duration_ms=0)
        results = BLEManager.get_scan_results()
        self.assertTrue(len(results) > 0)
        self.assertIsInstance(results[0].parsed_ad, dict)

        self._clean()

    def test_scan_with_callback(self):
        self._clean()
        received = []

        def handler(event, data):
            received.append(event)

        BLEManager.activate()
        BLEManager.register_irq(handler)
        BLEManager.start_scan(duration_ms=0)

        self.assertTrue(len(received) > 0)
        self.assertIn(BLEManager.IRQ_SCAN_DONE, received)

        self._clean()

    def test_clear_scan_results(self):
        self._clean()
        BLEManager.activate()
        BLEManager.register_irq(lambda e, d: None)
        BLEManager.start_scan(duration_ms=0)
        self.assertTrue(len(BLEManager.get_scan_results()) > 0)
        BLEManager.clear_scan_results()
        self.assertEqual(len(BLEManager.get_scan_results()), 0)
        self._clean()

    def test_scan_filter_filters_by_name(self):
        self._clean()
        BLEManager.activate()
        BLEManager.register_irq(lambda e, d: None)
        BLEManager.add_scan_filter(name="Phone")
        BLEManager.start_scan(duration_ms=0)
        results = BLEManager.get_scan_results()
        for r in results:
            ad_name = r.parsed_ad.get(9)
            self.assertIsNotNone(ad_name)
            self.assertIn(b"Phone", ad_name)
        self._clean()

    def test_scan_filter_no_results_when_none_match(self):
        self._clean()
        BLEManager.activate()
        BLEManager.register_irq(lambda e, d: None)
        BLEManager.add_scan_filter(name="ZzZzZzZzNoMatch")
        BLEManager.start_scan(duration_ms=0)
        results = BLEManager.get_scan_results()
        self.assertEqual(len(results), 0)
        self._clean()


class TestGattServer(unittest.TestCase):

    def _clean(self):
        BLEManager.deactivate()
        BLEManager.clear_scan_results()
        BLEManager.clear_scan_filters()

    def test_create_gatt_server(self):
        self._clean()
        BLEManager.activate()
        server = BLEManager.create_gatt_server()
        self.assertIsNotNone(server)
        self.assertIs(BLEManager.get_gatt_server(), server)
        self._clean()

    def test_add_service_registers(self):
        self._clean()
        BLEManager.activate()
        server = BLEManager.create_gatt_server()
        server.add_service(0xB2E4, ((0xB2E5, 0x0008),))
        server.register()
        self._clean()

    def test_on_write_callback(self):
        self._clean()
        BLEManager.activate()
        BLEManager.register_irq(lambda e, d: None)
        BLEManager.create_gatt_server()
        received = []

        def on_write(conn_handle, value_handle, value):
            received.append(value)

        BLEManager.get_gatt_server().on_write(on_write)
        ble = BLEManager.get_ble()
        ble._simulate_incoming_message(b"hello")
        self.assertTrue(len(received) > 0)
        self.assertEqual(received[0], b"hello")
        self._clean()


class TestGattClient(unittest.TestCase):

    def _clean(self):
        BLEManager.deactivate()
        BLEManager.clear_scan_results()
        BLEManager.clear_scan_filters()

    def test_create_gatt_client(self):
        self._clean()
        BLEManager.activate()
        client = BLEManager.create_gatt_client()
        self.assertIsNotNone(client)
        self.assertFalse(client.is_connected)
        self._clean()

    def test_connect_and_disconnect(self):
        self._clean()
        BLEManager.activate()
        BLEManager.register_irq(lambda e, d: None)
        client = BLEManager.create_gatt_client()
        client.connect(0, b"\xaa\xbb\xcc\xdd\xee\xff")
        self.assertTrue(client.is_connected)
        client.disconnect()
        self.assertFalse(client.is_connected)
        self._clean()

    def test_is_busy_watchdog(self):
        self._clean()
        BLEManager.activate()
        BLEManager.register_irq(lambda e, d: None)
        client = BLEManager.create_gatt_client()
        self.assertFalse(client.is_busy)
        client.connect(0, b"\xaa\xbb\xcc\xdd\xee\xff")
        self.assertFalse(client.is_busy)
        self._clean()

    def test_simulated_write_notify(self):
        self._clean()
        BLEManager.activate()
        BLEManager.register_irq(lambda e, d: None)
        client = BLEManager.create_gatt_client()
        client.connect(0, b"\xaa\xbb\xcc\xdd\xee\xff")
        client.write(0xB2E5, b"ping", response=False)
        self._clean()


class TestReAdvertise(unittest.TestCase):

    def _clean(self):
        BLEManager.deactivate()
        BLEManager.clear_scan_results()
        BLEManager.clear_scan_filters()

    def test_start_stop_advertising(self):
        self._clean()
        BLEManager.activate()
        self.assertFalse(BLEManager.is_advertising())
        BLEManager.start_advertising(name="Test", connectable=True)
        self.assertTrue(BLEManager.is_advertising())
        BLEManager.stop_advertising()
        self.assertFalse(BLEManager.is_advertising())
        self._clean()
