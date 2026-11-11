import ast
import contextlib
import importlib.util
import io
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


class DetectionTests(unittest.TestCase):
    def detect(self, devices, needs_pullups=False):
        probes = []
        released = []

        class Pin:
            IN = 0
            PULL_UP = 1

            def __init__(self, number, *args, **kwargs):
                self.number = number
                self.pull = args[1] if len(args) > 1 else kwargs.get("pull")
                if args and "pull" in kwargs and kwargs["pull"] is None:
                    released.append(number)

        class Bus:
            def __init__(self, scl, sda, **kwargs):
                self.pins = (scl.number, sda.number)
                self.pullups = (scl.pull, sda.pull)

            def readfrom_mem(self, address, register, count, **kwargs):
                key = (self.pins, address, register)
                probes.append(key)
                if needs_pullups and self.pullups != (Pin.PULL_UP, Pin.PULL_UP):
                    raise OSError(116)
                if key not in devices:
                    raise OSError("not present")
                return devices[key][:count]

        machine = types.SimpleNamespace(Pin=Pin, SoftI2C=Bus)
        with patch.dict(sys.modules, {"machine": machine}):
            tree = ast.parse(
                (ROOT / "internal_filesystem/lib/mpos/main.py").read_text()
            )
            function = next(
                node
                for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "detect_d_shell"
            )
            namespace = {}
            exec(
                compile(
                    ast.Module(body=[function], type_ignores=[]), "detection", "exec"
                ),
                namespace,
            )
            result = namespace["detect_d_shell"]()
        return result, probes, released

    def test_factory_touch_address(self):
        found, _, released = self.detect(
            {
                ((41, 42), 0x5D, 0x8140): b"911\x00",
                ((7, 6), 0x6A, 0): b"\x05",
            }
        )
        self.assertTrue(found)
        self.assertEqual(set(released), {41, 42, 7, 6})

    def test_cold_start_without_external_pullups(self):
        found, _, released = self.detect(
            {
                ((41, 42), 0x5D, 0x8140): b"911\x00",
                ((7, 6), 0x6A, 0): b"\x05",
            },
            needs_pullups=True,
        )
        self.assertTrue(found)
        self.assertEqual(set(released), {41, 42, 7, 6})

    def test_touch_address_after_driver_reset(self):
        found, _, _ = self.detect(
            {
                ((41, 42), 0x14, 0x8140): b"911\x00",
                ((7, 6), 0x6A, 0): b"\x05",
            }
        )
        self.assertTrue(found)

    def test_another_gt911_board_is_not_d_shell(self):
        found, _, _ = self.detect({((41, 42), 0x5D, 0x8140): b"911\x00"})
        self.assertFalse(found)

    def test_wrong_sensor_identity_is_rejected(self):
        found, _, _ = self.detect(
            {
                ((41, 42), 0x5D, 0x8140): b"911\x00",
                ((7, 6), 0x6A, 0): b"\x00",
            }
        )
        self.assertFalse(found)

    def test_missing_touch_does_not_probe_imu(self):
        found, probes, released = self.detect({})
        self.assertFalse(found)
        self.assertTrue(all(p[0] == (41, 42) for p in probes))
        self.assertEqual(set(released), {41, 42})


class HardwareTestGuardTests(unittest.TestCase):
    def load_tests(self, hardware_id, unittest_module=unittest):
        device = types.SimpleNamespace(get_hardware_id=lambda: hardware_id)
        mpos = types.ModuleType("mpos")
        mpos.DeviceInfo = device
        mpos.AudioManager = None
        mpos.LightsManager = None
        mpos.SensorManager = None
        path = ROOT / "tests/test_graphical_d_shell_hardware.py"
        spec = importlib.util.spec_from_file_location(
            "hardware_tests_under_review", path
        )
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"mpos": mpos, "unittest": unittest_module}):
            spec.loader.exec_module(module)
        return module

    def test_other_boards_skip_without_importing_hardware(self):
        module = self.load_tests("linux")
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(
            module.DShellHardwareTests
        )
        result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
        self.assertEqual(result.testsRun, 8)
        self.assertEqual(len(result.skipped), 8)
        self.assertTrue(result.wasSuccessful())

    def test_d_shell_hardware_tests_are_enabled(self):
        module = self.load_tests("d_shell")
        board_package = types.ModuleType("mpos.board")
        board_package.d_shell = object()
        with patch.dict(sys.modules, {"mpos.board": board_package}):
            case = module.DShellHardwareTests()
            case.setUp()
        self.assertIs(case.board, board_package.d_shell)

    def test_micropython_unittest_reports_all_hardware_checks_skipped(self):
        path = ROOT / "internal_filesystem/lib/unittest/__init__.py"
        spec = importlib.util.spec_from_file_location(
            "mpos_unittest_under_review", path
        )
        implementation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(implementation)
        module = self.load_tests("linux", implementation)
        with contextlib.redirect_stdout(io.StringIO()):
            result = implementation.main(module=module)
        self.assertEqual(result.testsRun, 8)
        self.assertEqual(len(result.skipped), 8)
        self.assertTrue(result.wasSuccessful())


class ImuRegistrationTests(unittest.TestCase):
    def register_board_imu(self, read_error=None):
        source = (ROOT / "internal_filesystem/lib/mpos/board/d_shell.py").read_text()
        tree = ast.parse(source)
        start = next(
            i
            for i, node in enumerate(tree.body)
            if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "imu_i2c"
        )
        end = next(
            i
            for i, node in enumerate(tree.body[start:], start)
            if isinstance(node, ast.Try) and "LightsManager.init" in ast.unparse(node)
        )
        bus = Mock()
        bus.readfrom_mem.side_effect = read_error
        bus.readfrom_mem.return_value = b"\x05"
        manager = Mock(FACING_SKY=1)
        namespace = {
            "I2C": Mock(return_value=bus),
            "Pin": lambda pin: pin,
            "SensorManager": manager,
            "logger": Mock(),
        }
        exec(
            compile(
                ast.Module(body=tree.body[start:end], type_ignores=[]), source, "exec"
            ),
            namespace,
        )
        return bus, manager

    def test_bus_registered_when_first_identity_read_would_fail(self):
        bus, manager = self.register_board_imu(OSError("temporary I2C error"))
        manager.init.assert_called_once_with(bus, address=0x6A, mounted_position=1)
        bus.readfrom_mem.assert_not_called()

    def test_identity_probe_is_deferred_to_sensor_manager(self):
        bus, manager = self.register_board_imu()
        manager.init.assert_called_once_with(bus, address=0x6A, mounted_position=1)
        bus.readfrom_mem.assert_not_called()

    def test_registered_bus_recovers_after_failed_probe(self):
        source = (ROOT / "internal_filesystem/lib/mpos/imu/manager.py").read_text()
        cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef))
        namespace = runpy.run_path(
            str(ROOT / "internal_filesystem/lib/mpos/imu/constants.py")
        )
        now = [0]
        namespace.update(
            logger=Mock(),
            time=types.SimpleNamespace(
                ticks_ms=lambda: now[0],
                ticks_diff=lambda a, b: a - b,
                ticks_add=lambda a, b: a + b,
            ),
        )
        exec(
            compile(ast.Module(body=[cls], type_ignores=[]), "imu_manager", "exec"),
            namespace,
        )
        imu = namespace["ImuManager"]()
        bus, registration = self.register_board_imu()
        args, kwargs = registration.init.call_args
        imu.init(*args, **kwargs)
        bus.readfrom_mem.side_effect = OSError("temporary I2C error")
        self.assertFalse(imu._ensure_imu_initialized())
        self.assertIs(imu._i2c_bus, bus)
        bus.readfrom_mem.side_effect = None
        bus.readfrom_mem.return_value = b"\x05"
        driver = types.ModuleType("mpos.imu.drivers.qmi8658")
        driver.QMI8658Driver = Mock()
        imu._register_qmi8658_sensors = Mock()
        imu._load_calibration = Mock()
        now[0] = namespace["IMU_PROBE_RETRY_MS"]
        with patch.dict(sys.modules, {"mpos.imu.drivers.qmi8658": driver}):
            self.assertTrue(imu._ensure_imu_initialized())
        driver.QMI8658Driver.assert_called_once_with(bus, 0x6A)


if __name__ == "__main__":
    unittest.main()
