import importlib.util
import contextlib
import io
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class HardwareTestGuardTests(unittest.TestCase):
    def load_tests(self, hardware_id, unittest_module=unittest):
        device = types.SimpleNamespace(get_hardware_id=lambda: hardware_id)
        mpos = types.ModuleType("mpos")
        mpos.DeviceInfo = device
        mpos.AudioManager = None
        mpos.LightsManager = None
        mpos.SensorManager = None
        path = ROOT / "tests/test_graphical_d_shell_hardware.py"
        spec = importlib.util.spec_from_file_location("hardware_tests_under_review", path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"mpos": mpos, "unittest": unittest_module}):
            spec.loader.exec_module(module)
        return module

    def test_other_boards_skip_without_importing_hardware(self):
        module = self.load_tests("linux")
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(module.DShellHardwareTests)
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
        spec = importlib.util.spec_from_file_location("mpos_unittest_under_review", path)
        implementation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(implementation)
        module = self.load_tests("linux", implementation)
        with contextlib.redirect_stdout(io.StringIO()):
            result = implementation.main(module=module)
        self.assertEqual(result.testsRun, 8)
        self.assertEqual(len(result.skipped), 8)
        self.assertTrue(result.wasSuccessful())


if __name__ == "__main__":
    unittest.main()
