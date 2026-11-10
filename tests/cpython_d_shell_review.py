import ast
import contextlib
import io
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


class ImuRegistrationTests(unittest.TestCase):
    def register_board_imu(self, read_error=None):
        source = (ROOT / "internal_filesystem/lib/mpos/board/d_shell.py").read_text()
        tree = ast.parse(source)
        start = next(i for i, node in enumerate(tree.body)
                     if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                     and node.targets[0].id == "imu_i2c")
        end = next(i for i, node in enumerate(tree.body[start:], start)
                   if isinstance(node, ast.Try) and "LightsManager.init" in ast.unparse(node))
        bus = Mock()
        bus.readfrom_mem.side_effect = read_error
        bus.readfrom_mem.return_value = b"\x05"
        manager = Mock(FACING_SKY=1)
        namespace = {"I2C": Mock(return_value=bus), "Pin": lambda pin: pin,
                     "SensorManager": manager, "logger": Mock()}
        exec(compile(ast.Module(body=tree.body[start:end], type_ignores=[]), source, "exec"), namespace)
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
        namespace = runpy.run_path(str(ROOT / "internal_filesystem/lib/mpos/imu/constants.py"))
        now = [0]
        namespace.update(logger=Mock(), time=types.SimpleNamespace(
            ticks_ms=lambda: now[0], ticks_diff=lambda a, b: a - b, ticks_add=lambda a, b: a + b))
        exec(compile(ast.Module(body=[cls], type_ignores=[]), "imu_manager", "exec"), namespace)
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


class HardwareRunnerResultsTests(unittest.TestCase):
    names = ["test_board_and_display", "test_gt911_identity", "test_buttons_idle", "test_qmi8658",
             "test_aht20", "test_veml7700", "test_ds1307", "test_registered_outputs"]

    def run_hardware_runner(self, results):
        controller = Mock()
        controller.__enter__ = Mock(return_value=controller)
        controller.__exit__ = Mock(return_value=False)
        controller.exec_multiline.return_value = b""
        controller.eval.return_value = results
        module = types.ModuleType("scripts.mpos_controller")
        module.MPOSController = Mock(return_value=controller)
        output = io.StringIO()
        status = 0
        with patch.dict(sys.modules, {"scripts.mpos_controller": module}), \
                patch("time.sleep"), patch.object(Path, "mkdir"), \
                patch.object(Path, "write_bytes"), contextlib.redirect_stdout(output), \
                patch.object(sys, "path", list(sys.path)):
            try:
                runpy.run_path(str(ROOT / "scripts/d_shell/run_hardware_tests.py"))
            except SystemExit as error:
                status = error.code
        return status, output.getvalue()

    def test_all_eight_pass(self):
        status, output = self.run_hardware_runner(dict.fromkeys(self.names, "passed"))
        self.assertEqual(status, 0)
        self.assertIn("HARDWARE_TESTS_PASSED True", output)

    def test_empty_results_fail(self):
        status, output = self.run_hardware_runner({})
        self.assertEqual(status, 1)
        self.assertIn("HARDWARE_TESTS_PASSED False", output)

    def test_each_missing_check_fails(self):
        for missing in self.names:
            with self.subTest(missing=missing):
                results = dict.fromkeys(self.names, "passed")
                del results[missing]
                status, output = self.run_hardware_runner(results)
                self.assertEqual(status, 1)
                self.assertIn("HARDWARE_TESTS_PASSED False", output)

    def test_failed_check_fails(self):
        results = dict.fromkeys(self.names, "passed")
        results[self.names[0]] = "OSError('I2C error')"
        status, output = self.run_hardware_runner(results)
        self.assertEqual(status, 1)
        self.assertIn("HARDWARE_TESTS_PASSED False", output)


if __name__ == "__main__":
    unittest.main()
